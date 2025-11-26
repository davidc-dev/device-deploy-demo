import os
import shutil
import subprocess
import tempfile
import textwrap
from typing import Optional
from urllib.parse import urlparse, urlunparse

import logging
import requests
from fastapi import FastAPI, Form
from kubernetes import client, config
from kubernetes.client import ApiException
from kubernetes.config import ConfigException
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("device-workflow")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Config ---
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "davidc-dev")
ARGOCD_URL = os.getenv("ARGOCD_URL")
ARGOCD_TOKEN = os.getenv("ARGOCD_TOKEN")
ARGOCD_DISABLE_TLS = os.getenv("ARGOCD_DISABLE_TLS", "false")
APPS_DOMAIN = os.getenv("APPS_DOMAIN", "")


# ---------- Helpers ----------

def _git(*args, cwd: Optional[str] = None):
    subprocess.run(["git", *args], check=True, cwd=cwd)


def _build_argocd_app_yaml(app_name: str, repo_url: str, dest_server: str, dest_namespace: str):
    return f"""
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: {app_name}
  namespace: openshift-gitops
spec:
  project: default
  source:
    repoURL: {repo_url}
    targetRevision: HEAD
    path: .
  destination:
    server: {dest_server}
    namespace: {dest_namespace}
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
    syncOptions:
    - CreateNamespace=true
    """.strip()


def _write_devfile(repo_dir: str, repo_name: str, repo_url: str):
    devfile = textwrap.dedent(
        f"""
        schemaVersion: 2.2.0
        metadata:
          name: {repo_name[:63]}
        attributes:
          controller.devfile.io/editor: che-code
        components:
          - name: dev-tools
            container:
              image: quay.io/devspaces/udi-rhel8:latest
              memoryLimit: 2Gi
              mountSources: true
        commands:
          - id: git-config
            exec:
              component: dev-tools
              workingDir: /projects
              commandLine: |
                git config --global user.name "Device Workflow Bot" && \\
                git config --global user.email "auto@example.com"
              label: Configure Git
        events:
          postStart:
            - git-config
        projects:
          - name: {repo_name[:63]}
            git:
              remotes:
                origin: {repo_url}
        """
    ).strip()
    with open(os.path.join(repo_dir, "devfile.yaml"), "w", encoding="utf-8") as f:
        f.write(devfile + "\n")


def _argocd_creds():
    if not ARGOCD_URL or not ARGOCD_TOKEN:
        raise RuntimeError("ARGOCD_URL / ARGOCD_TOKEN not configured")
    return ARGOCD_URL, ARGOCD_TOKEN


def _should_verify_tls(override: Optional[str] = None):
    flag = override if override not in (None, "") else ARGOCD_DISABLE_TLS
    return False if str(flag).lower() in ("true", "1", "yes", "on") else True


def _download_helm_chart(temp_dir: str, repo_dir: str, repo_url: str, chart_version: str = "", chart_name: str = ""):
    os.makedirs(repo_dir, exist_ok=True)
    unpack_dir = tempfile.mkdtemp(prefix="helm-chart-", dir=temp_dir)
    repo_url = repo_url.strip()
    if repo_url.startswith("oci://"):
        chart_ref = repo_url.rstrip("/")
        if chart_name:
            chart_ref = f"{chart_ref}/{chart_name.lstrip('/')}"
        cmd = ["helm", "pull", chart_ref, "--untar", "--untardir", unpack_dir]
    else:
        if not chart_name:
            raise RuntimeError("helm_chart_name is required for non-OCI Helm repositories.")
        cmd = ["helm", "pull", chart_name, "--repo", repo_url, "--untar", "--untardir", unpack_dir]
    if chart_version:
        cmd.extend(["--version", chart_version])
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise RuntimeError("Helm CLI not found. Install helm or adjust PATH.")
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Helm pull failed: {exc.stderr or exc.stdout}") from exc

    chart_dirs = [d for d in os.listdir(unpack_dir) if os.path.isdir(os.path.join(unpack_dir, d))]
    if not chart_dirs:
        raise RuntimeError("Helm pull completed but no chart directory was created.")
    chart_root = None
    if chart_name:
        for d in chart_dirs:
            if d == chart_name:
                chart_root = os.path.join(unpack_dir, d)
                break
        if chart_root is None:
            raise RuntimeError(f"Helm chart '{chart_name}' not found in archive; found {chart_dirs}")
    else:
        chart_root = os.path.join(unpack_dir, chart_dirs[0])
    for entry in os.listdir(chart_root):
        shutil.move(os.path.join(chart_root, entry), repo_dir)
    shutil.rmtree(chart_root, ignore_errors=True)
    shutil.rmtree(unpack_dir, ignore_errors=True)


def _write_values_yaml(repo_dir: str, values_content: str, device_name: str, device_id: str, cluster_fqdn: str):
    route_host = ""
    if cluster_fqdn:
        route_host = f"{device_name}-{device_id}.{cluster_fqdn}"
    if values_content.strip():
        content = values_content.strip() + ("\n" if not values_content.endswith("\n") else "")
    else:
        default = textwrap.dedent(
            f"""
            # Auto-generated values for {device_name} ({device_id})
            device:
              name: "{device_name}"
              id: "{device_id}"
            routeHost: "{route_host}"
            """
        ).strip("\n")
        content = default + "\n"
    with open(os.path.join(repo_dir, "values.yaml"), "w", encoding="utf-8") as f:
        f.write(content)


def _load_k8s_client():
    try:
        config.load_incluster_config()
    except ConfigException:
        try:
            config.load_kube_config()
        except ConfigException:
            return None
    return client.CustomObjectsApi()


# ---------- Endpoints ----------
@app.post("/create-device-repo")
def create_device_repo(
    device_id: str = Form(...),
    device_name: str = Form(...),
    cluster_fqdn: str = Form(""),
    helm_repo_url: str = Form(...),
    helm_chart_name: str = Form(""),
    helm_chart_version: str = Form(""),
    helm_values_yaml: str = Form(""),
):
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN not set"}
    if not helm_repo_url:
        return {"error": "helm_repo_url is required"}

    temp_dir = tempfile.mkdtemp(prefix="device-")
    repo_dir = os.path.join(temp_dir, "repo")
    try:
        try:
            os.makedirs(repo_dir, exist_ok=True)
            _download_helm_chart(temp_dir, repo_dir, helm_repo_url, helm_chart_version, helm_chart_name)
        except RuntimeError as exc:
            return {"error": str(exc)}

        try:
            _write_values_yaml(repo_dir, helm_values_yaml, device_name, device_id, cluster_fqdn)
        except Exception as exc:
            return {"error": f"Unable to write values.yaml: {exc}"}

        repo_name = f"device-{device_name}-{device_id}".replace("_", "-")

        # 3) Create the new repo
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }
        payload = {"name": repo_name, "description": f"Auto-generated for {device_name} ({device_id})", "private": False}
        r = requests.post("https://api.github.com/user/repos", json=payload, headers=headers)
        if r.status_code >= 300:
            return {"error": f"GitHub repo creation failed: {r.text}"}
        new_repo_clone_url = r.json()["clone_url"]

        # 3.5) Generate devfile referencing the remote
        _write_devfile(repo_dir, repo_name, new_repo_clone_url)

        # 4) Push content
        _git("init", cwd=repo_dir)
        # ensure human readable identity
        _git("config", "user.email", "auto@example.com", cwd=repo_dir)
        _git("config", "user.name", "Device Workflow Bot", cwd=repo_dir)

        parsed = urlparse(new_repo_clone_url)
        token_netloc = f"{GITHUB_USERNAME}:{GITHUB_TOKEN}@{parsed.hostname}"
        authed_url = urlunparse(
            (parsed.scheme, token_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )

        _git("remote", "add", "origin", authed_url, cwd=repo_dir)
        _git("add", ".", cwd=repo_dir)
        _git("commit", "-m", "Initial commit", cwd=repo_dir)
        _git("branch", "-M", "main", cwd=repo_dir)
        try:
            completed = subprocess.run(
                ["git", "push", "-u", "origin", "main"],
                check=True,
                cwd=repo_dir,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as exc:
            msg = exc.stderr or exc.stdout or str(exc)
            return {"error": f"Git push failed: {msg}"}

        return {"status": "ok", "repo_url": new_repo_clone_url, "repo_name": repo_name}
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


@app.post("/deploy-argocd-app")
def deploy_argocd_app(
    repo_url: str = Form(...),
    device_id: str = Form(...),
    device_name: str = Form(...),
    destination_server: str = Form(...),
    destination_namespace: str = Form(...),
    cluster_fqdn: str = Form(""),
    use_argocd_api: str = Form("false"),
):
    app_name = f"device-{device_name}-{device_id}".replace("_", "-")
    yaml = _build_argocd_app_yaml(app_name, repo_url, destination_server, destination_namespace)

    if use_argocd_api and use_argocd_api.strip().lower() in ("1", "true", "yes"):
        use_api = True
    else:
        use_api = False

    if not use_api:
        return {"status": "yaml_only", "argocd_yaml": yaml, "app_name": app_name}

    try:
        argocd_url, argocd_token = _argocd_creds()
    except RuntimeError as exc:
        return {"error": str(exc), "argocd_yaml": yaml}

    verify_tls = _should_verify_tls()

    # Argo CD create/update via Application API (upsert)
    # POST /api/v1/applications (create), or use PATCH if exists. We'll try create; if 409, try update.
    headers = {
        "Authorization": f"Bearer {argocd_token}",
        "Content-Type": "application/json",
    }
    create_url = argocd_url.rstrip("/") + "/api/v1/applications"
    payload = {
        "metadata": {"name": app_name, "namespace": "openshift-gitops"},
        "spec": {
            "project": "default",
            "source": {"repoURL": repo_url, "targetRevision": "HEAD", "path": "."},
            "destination": {"server": destination_server, "namespace": destination_namespace},
            "syncPolicy": {"automated": {"prune": True, "selfHeal": True}, "syncOptions": ["CreateNamespace=true"]},
        },
    }

    r = requests.post(create_url, json=payload, headers=headers, verify=verify_tls)
    if r.status_code == 409:
        # Already exists -> update
        upsert_url = argocd_url.rstrip("/") + f"/api/v1/applications/{app_name}"
        r = requests.put(upsert_url, json=payload, headers=headers, verify=verify_tls)

    if r.status_code >= 300:
        return {"error": f"ArgoCD API error: {r.status_code} {r.text}", "argocd_yaml": yaml, "app_name": app_name}

    return {
        "status": "deployed",
        "argocd_yaml": yaml,
        "app_name": app_name,
        "argocd_response": r.text,
    }


# ---- ArgoCD proxy: list apps ----
@app.post("/argocd/apps")
def argocd_list_apps():
    try:
        argocd_url, argocd_token = _argocd_creds()
    except RuntimeError as exc:
        return {"error": str(exc)}
    headers = {"Authorization": f"Bearer {argocd_token}"}
    url = argocd_url.rstrip("/") + "/api/v1/applications"
    verify = _should_verify_tls()
    resp = requests.get(url, headers=headers, verify=verify)
    if resp.status_code >= 300:
        return {"error": f"ArgoCD API error: {resp.status_code} {resp.text}"}

    data = resp.json() or {}
    items = data.get("items") if isinstance(data, dict) else data
    out = []
    kube_api = _load_k8s_client()
    for it in items or []:
        meta = it.get("metadata", {})
        spec = it.get("spec", {})
        status = it.get("status", {})
        dest = spec.get("destination", {})
        src = spec.get("source", {})
        route_host = None
        if kube_api:
            dest_namespace = dest.get("namespace") or "default"
        app_name = meta.get("name")
        base_name = meta.get("annotations", {}).get("device-workflow/name", app_name)
            try:
                routes = kube_api.list_namespaced_custom_object(
                    group="route.openshift.io",
                    version="v1",
                    namespace=dest_namespace,
                    plural="routes",
                    label_selector=f"argocd.argoproj.io/instance={app_name}"
                )
                for route in (routes.get("items") or []):
                    host = (route.get("spec") or {}).get("host")
                    if host:
                        route_host = host
                        logger.info("Route host %s found via label for %s/%s", host, dest_namespace, app_name)
                        break
            except ApiException as exc:
                logger.warning("Route lookup via label failed for %s/%s: %s", dest_namespace, app_name, exc)

            if not route_host:
                try:
                    route = kube_api.get_namespaced_custom_object(
                        group="route.openshift.io",
                        version="v1",
                        namespace=dest_namespace,
                        plural="routes",
                    name=app_name,
                )
                    route_host = (route.get("spec") or {}).get("host")
                    if route_host:
                        logger.info("Route host %s found via name for %s/%s", route_host, dest_namespace, app_name)
                except ApiException as exc:
                    logger.warning("Route lookup via name failed for %s/%s: %s", dest_namespace, app_name, exc)
        if not route_host and APPS_DOMAIN and dest.get("namespace"):
            route_host = f"{base_name}-{dest.get('namespace')}.{APPS_DOMAIN}"
            logger.info("Defaulting route host to %s for %s", route_host, meta.get('name'))
        out.append({
            "appName": meta.get("name"),
            "namespace": dest.get("namespace"),
            "cluster": dest.get("server"),
            "repoUrl": src.get("repoURL"),
            "syncStatus": (status.get("sync", {}) or {}).get("status"),
            "health": (status.get("health", {}) or {}).get("status"),
            "lastSync": (status.get("operationState", {}) or {}).get("finishedAt"),
            "clusterFqdn": APPS_DOMAIN,
            "routeHost": route_host,
        })
    return {"apps": out}


# ---- ArgoCD proxy: manual sync ----
@app.post("/argocd/sync")
def argocd_sync(
    app_name: str = Form(...),
):
    try:
        argocd_url, argocd_token = _argocd_creds()
    except RuntimeError as exc:
        return {"error": str(exc)}
    verify = _should_verify_tls()
    headers = {
        "Authorization": f"Bearer {argocd_token}",
        "Content-Type": "application/json",
    }
    url = argocd_url.rstrip("/") + f"/api/v1/applications/{app_name}/sync"
    payload = {"prune": True, "dryRun": False, "strategy": {"hook": {}}}
    r = requests.post(url, json=payload, headers=headers, verify=verify)
    if r.status_code >= 300:
        return {"error": f"ArgoCD API error: {r.status_code} {r.text}"}
    return {"status": "ok"}
