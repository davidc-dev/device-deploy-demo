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



# =====================================================================
#  ENDPOINT 2: CREATE & APPLY ARGOCD APPLICATION
# =====================================================================
@app.post("/deploy-argocd-app")
def deploy_argocd_app(
    repo_url: str = Form(...),
    device_id: str = Form(...),
    device_name: str = Form(...),
    destination_server: str = Form(...),      # NEW INPUT
    destination_namespace: str = Form(...),   # NEW INPUT
):
    """Step 2: Create ArgoCD Application YAML and optionally apply it."""

    # Updated app name format: device-name_device-id
    app_name = f"device-{device_name}-{device_id}"

    # Build ArgoCD Application YAML with dynamic destination values
    argo_yaml = textwrap.dedent(f"""
    apiVersion: argoproj.io/v1alpha1
    kind: Application
    metadata:
      name: {app_name}
      namespace: {ARGO_NAMESPACE}
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

    applied = False
    apply_error = None

    # Optionally auto-apply to cluster
    if AUTO_APPLY_ARGO:
        try:
            bin_to_use = "oc"
            if subprocess.run(["which", "oc"], capture_output=True).returncode != 0:
                bin_to_use = "kubectl"

            proc = subprocess.run(
                [bin_to_use, "apply", "-f", "-"],
                input=argo_yaml.encode(),
                capture_output=True,
                check=True
            )
            applied = True

        except subprocess.CalledProcessError as e:
            apply_error = e.stderr.decode() if e.stderr else str(e)

    return {
        "status": "success",
        "argocd_application_name": app_name,
        "argocd_yaml": argo_yaml,
        "applied": applied,
        "apply_error": apply_error
    }
