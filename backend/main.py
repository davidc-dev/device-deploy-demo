import os
import shutil
import subprocess
import tempfile
import textwrap
from typing import Optional
from urllib.parse import urlparse, urlunparse

import requests
from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware

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
TEMPLATE_REPO = os.getenv("TEMPLATE_REPO", "https://github.com/davidc-dev/deploy-template-bgdk-yaml.git")


# ---------- Helpers ----------

def _git(*args, cwd: Optional[str] = None):
    subprocess.run(["git", *args], check=True, cwd=cwd)


def _patch_placeholders(root_dir: str, replacements: dict):
    files = [
        "bgd-configmaps.yaml",
        "bgd-deployment.yaml",
        "bgd-pvc.yaml",
        "bgd-route.yaml",
        "bgd-svc.yaml",
    ]
    for rel in files:
        path = os.path.join(root_dir, rel)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        for key, val in replacements.items():
            content = content.replace(key, val)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)


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


# ---------- Endpoints ----------
@app.post("/create-device-repo")
def create_device_repo(
    device_id: str = Form(...),
    device_name: str = Form(...),
    cluster_fqdn: str = Form(""),
):
    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN not set"}

    temp_dir = tempfile.mkdtemp(prefix="device-")
    repo_dir = os.path.join(temp_dir, "repo")
    try:
        # 1) Clone template
        _git("clone", TEMPLATE_REPO, repo_dir)

        # 2) Replace placeholders
        replacements = {
            "{{DEVICE_ID}}": device_id,
            "{{DEVICE_NAME}}": device_name,
        }
        repo_name = f"device-{device_name}-{device_id}".replace("_", "-")
        if cluster_fqdn:
            # route fqdn placeholder (if present)
            replacements["{{CLUSTER_FQDN}}"] = cluster_fqdn
        _patch_placeholders(repo_dir, replacements)

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
        # ensure human readable identity
        _git("config", "user.email", "auto@example.com", cwd=repo_dir)
        _git("config", "user.name", "Device Workflow Bot", cwd=repo_dir)
        _git("remote", "remove", "origin", cwd=repo_dir)

        parsed = urlparse(new_repo_clone_url)
        token_netloc = f"{GITHUB_USERNAME}:{GITHUB_TOKEN}@{parsed.hostname}"
        authed_url = urlunparse(
            (parsed.scheme, token_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment)
        )

        _git("remote", "add", "origin", authed_url, cwd=repo_dir)
        _git("add", ".", cwd=repo_dir)
        _git("commit", "-m", "Initial commit", cwd=repo_dir)
        _git("branch", "-M", "main", cwd=repo_dir)
        _git("push", "-u", "origin", "main", cwd=repo_dir)

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
    argocd_url: str = Form(""),
    argocd_token: str = Form(""),
    disable_tls: str = Form("false"),
):
    app_name = f"device-{device_name}-{device_id}".replace("_", "-")
    yaml = _build_argocd_app_yaml(app_name, repo_url, destination_server, destination_namespace)

    if use_argocd_api and use_argocd_api.strip().lower() in ("1", "true", "yes"):
        use_api = True
    else:
        use_api = False

    if not use_api:
        return {"status": "yaml_only", "argocd_yaml": yaml, "app_name": app_name}

    if not argocd_url:
        return {"error": "Missing argocd_url", "argocd_yaml": yaml}
    if not argocd_token:
        return {"error": "Missing argocd_token", "argocd_yaml": yaml}

    verify_tls = False if disable_tls.lower() == "true" else True

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
def argocd_list_apps(
    argocd_url: str = Form(...),
    argocd_token: str = Form(...),
    disable_tls: str = Form("false"),
):
    headers = {"Authorization": f"Bearer {argocd_token}"}
    url = argocd_url.rstrip("/") + "/api/v1/applications"
    verify = False if disable_tls.lower() == "true" else True
    resp = requests.get(url, headers=headers, verify=verify)
    if resp.status_code >= 300:
        return {"error": f"ArgoCD API error: {resp.status_code} {resp.text}"}

    data = resp.json() or {}
    items = data.get("items") if isinstance(data, dict) else data
    out = []
    for it in items or []:
        meta = it.get("metadata", {})
        spec = it.get("spec", {})
        status = it.get("status", {})
        dest = spec.get("destination", {})
        src = spec.get("source", {})
        out.append({
            "appName": meta.get("name"),
            "namespace": dest.get("namespace"),
            "cluster": dest.get("server"),
            "repoUrl": src.get("repoURL"),
            "syncStatus": (status.get("sync", {}) or {}).get("status"),
            "health": (status.get("health", {}) or {}).get("status"),
            "lastSync": (status.get("operationState", {}) or {}).get("finishedAt"),
        })
    return {"apps": out}


# ---- ArgoCD proxy: manual sync ----
@app.post("/argocd/sync")
def argocd_sync(
    argocd_url: str = Form(...),
    argocd_token: str = Form(...),
    app_name: str = Form(...),
    disable_tls: str = Form("false"),
):
    verify = False if disable_tls.lower() == "true" else True
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
