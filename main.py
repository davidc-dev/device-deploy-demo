import os
import shutil
import tempfile
import subprocess
import textwrap

from fastapi import FastAPI, Form
from fastapi.middleware.cors import CORSMiddleware
import requests


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# GLOBAL CONFIG
# -----------------------------
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_USERNAME = "davidc-dev"
TEMPLATE_REPO = "https://github.com/davidc-dev/deploy-template-bgdk-yaml.git"

ARGO_NAMESPACE = "openshift-gitops"
ARGO_DEST_NAMESPACE = "device-apps"
ARGO_DEST_SERVER = "https://kubernetes.default.svc"  # Given by you

# If true, will run oc/kubectl to apply the ArgoCD Application
AUTO_APPLY_ARGO = os.getenv("APPLY_ARGO", "false").lower() in ("1", "true", "yes")


# =====================================================================
#  ENDPOINT 1: CREATE GITHUB DEVICE REPOSITORY
# =====================================================================
@app.post("/create-device-repo")
def create_device_repo(
    device_id: str = Form(...),
    device_name: str = Form(...),
    cluster_fqdn: str = Form(...)  
):
    """Step 1: Clone template → modify file → create GitHub repo → push."""

    if not GITHUB_TOKEN:
        return {"error": "GITHUB_TOKEN environment variable not set"}

    # 1. Working directory
    temp_dir = tempfile.mkdtemp()

    try:
        # ---------------------------------------------------
        # 2. Clone template repo
        # ---------------------------------------------------
        clone_proc = subprocess.run(
            ["git", "clone", TEMPLATE_REPO, temp_dir],
            capture_output=True,
            text=True
        )
        if clone_proc.returncode != 0:
            shutil.rmtree(temp_dir)
            return {
                "error": "git clone failed",
                "details": clone_proc.stderr
            }

       # ---------------------------------------------------
        # 3. Modify all template files
        # ---------------------------------------------------
        files_to_update = [
            "bgd-configmaps.yaml",
            "bgd-deployment.yaml",
            "bgd-route.yaml",
            "bgd-svc.yaml"
        ]

        for filename in files_to_update:
            filepath = os.path.join(temp_dir, filename)

            if not os.path.isfile(filepath):
                shutil.rmtree(temp_dir)
                return {"error": f"Template file not found: {filename}"}

            with open(filepath, "r") as f:
                content = f.read()

            # Verify DEVICE placeholders
            if "{{DEVICE_ID}}" not in content or "{{DEVICE_NAME}}" not in content:
                shutil.rmtree(temp_dir)
                return {
                    "error": f"Missing DEVICE placeholders in {filename}"
                }

            # Replace DEVICE placeholders
            updated_content = (
                content
                .replace("{{DEVICE_ID}}", device_id)
                .replace("{{DEVICE_NAME}}", device_name)
            )

            # Special handling: bgd-route.yaml also needs CLUSTER_FQDN
            if filename == "bgd-route.yaml":
                if "{{CLUSTER_FQDN}}" not in updated_content:
                    shutil.rmtree(temp_dir)
                    return {
                        "error": "Missing {{CLUSTER_FQDN}} in bgd-route.yaml"
                    }

                updated_content = updated_content.replace("{{CLUSTER_FQDN}}", cluster_fqdn)

            with open(filepath, "w") as f:
                f.write(updated_content)

        # ---------------------------------------------------
        # 4. Create GitHub repo
        # ---------------------------------------------------
        new_repo_name = f"device-{device_id}"
        repo_payload = {
            "name": new_repo_name,
            "description": f"Auto-generated repo for device {device_id}",
            "private": False,
        }
        headers = {
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
        }

        gh_resp = requests.post(
            "https://api.github.com/user/repos",
            json=repo_payload,
            headers=headers
        )

        if gh_resp.status_code >= 300:
            shutil.rmtree(temp_dir)
            return {
                "error": "GitHub repo creation failed",
                "details": gh_resp.text
            }

        new_repo_url = gh_resp.json()["clone_url"]

        # ---------------------------------------------------
        # 5. Commit + push
        # ---------------------------------------------------
        subprocess.run(["git", "-C", temp_dir, "config", "user.email", "auto@example.com"])
        subprocess.run(["git", "-C", temp_dir, "config", "user.name", "Auto Commit"])

        subprocess.run(["git", "-C", temp_dir, "add", "."], check=True)

        commit_proc = subprocess.run(
            ["git", "-C", temp_dir, "commit", "-m", "Initial commit"],
            capture_output=True,
            text=True
        )

        if commit_proc.returncode != 0:
            # fallback empty commit
            subprocess.run(
                ["git", "-C", temp_dir, "commit", "--allow-empty", "-m", "Initial commit"],
                check=True
            )

        subprocess.run(
            ["git", "-C", temp_dir, "remote", "add", "neworigin", new_repo_url],
            check=True
        )
        push_proc = subprocess.run(
            ["git", "-C", temp_dir, "push", "neworigin", "HEAD:main"],
            capture_output=True,
            text=True
        )

        if push_proc.returncode != 0:
            shutil.rmtree(temp_dir)
            return {
                "error": "Push failed",
                "details": push_proc.stderr
            }

        return {
            "status": "success",
            "repo_url": new_repo_url,
            "device_id": device_id,
            "device_name": device_name
        }

    finally:
        shutil.rmtree(temp_dir)



# ===============================================================
# STEP 2:
# Generate YAML OR Deploy via ArgoCD API
# ===============================================================
@app.post("/deploy-argocd-app")
def deploy_argocd_app(
    repo_url: str = Form(...),
    device_id: str = Form(...),
    device_name: str = Form(...),
    destination_server: str = Form(...),
    destination_namespace: str = Form(...),
    cluster_fqdn: str = Form(...),

    use_argocd_api: str = Form("false"),

    argocd_url: str = Form(None),
    argocd_token: str = Form(None),
    disable_tls: str = Form("false")   # ✅ REQUIRED
):

    app_name = f"device-{device_name}-{device_id}".lower().replace("_", "-")

    # ✅ Build Argo Application YAML
    argo_yaml = textwrap.dedent(f"""
    apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: {app_name}
      namespace: openshift-gitops
    spec:
      project: default
      source:
        repoURL: {repo_url}
        targetRevision: main
        path: .
      destination:
        server: {destination_server}
        namespace: {destination_namespace}
      syncPolicy:
        automated:
          prune: true
          selfHeal: true
        syncOptions:
          - CreateNamespace=true
    """).strip()

    # =========================================================
    # OPTION 1: YAML ONLY
    # =========================================================
    if use_argocd_api.lower() != "true":
        return {
            "status": "yaml_only",
            "argocd_yaml": argo_yaml,
            "application_name": app_name
        }


    # =========================================================
    # OPTION 2: Deploy using ArgoCD REST API
    # =========================================================
    if not argocd_url:
        return {"error": "Missing argocd_url"}

    if not argocd_token:
        return {"error": "Missing argocd_token"}

    # Determine TLS behavior
    verify_tls = False if disable_tls.lower() == "true" else True

    headers = {
        "Authorization": f"Bearer {argocd_token}",
        "Content-Type": "application/json"
    }

    # ArgoCD JSON payload (same as YAML)
    app_payload = {
        "metadata": {
            "name": app_name,
            "namespace": "openshift-gitops"
        },
        "spec": {
            "project": "default",
            "source": {
                "repoURL": repo_url,
                "targetRevision": "main",
                "path": "."
            },
            "destination": {
                "server": destination_server,
                "namespace": destination_namespace
            },
            "syncPolicy": {
                "automated": {
                    "prune": True,
                    "selfHeal": True
                },
                "syncOptions": [
                    "CreateNamespace=true"
                ]
            }
        }
    }

    # Create application
    create_url = f"{argocd_url}/api/v1/applications"
    res = requests.post(
        create_url,
        headers=headers,
        json=app_payload,
        verify=verify_tls
    )

    # If exists → update it
    if res.status_code == 409:
        update_url = f"{argocd_url}/api/v1/applications/{app_name}"
        res = requests.put(
            update_url,
            headers=headers,
            json=app_payload,
            verify=verify_tls
        )

    if res.status_code >= 300:
        return {
            "error": "ArgoCD create/update failed",
            "details": res.text
        }

    # Trigger sync
    sync_url = f"{argocd_url}/api/v1/applications/{app_name}/sync"
    sync_res = requests.post(
        sync_url,
        headers=headers,
        verify=verify_tls
    )

    return {
        "status": "deployed_via_argocd_api",
        "application_name": app_name,
        "tls_verification": verify_tls,
        "argocd_yaml": argo_yaml,
        "argocd_api_response": res.text,
        "argocd_sync_response": sync_res.text
    }
