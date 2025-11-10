# Device Workflow Application

Single-page workflow (React + Vite) that:

1. Creates a GitHub repo per device (templated manifests + Dev Spaces devfile).
2. Generates or deploys an ArgoCD Application for that repo.
3. Displays an ArgoCD-backed device dashboard with Repo / ArgoCD / Dev Spaces / Route / Sync shortcuts.

Backend: FastAPI service in repo root (`main.py`) — runs at `http://localhost:8000` by default.

## Prerequisites

- Node 18+ and npm for the frontend.
- Python 3.10+, plus `pip install -r requirements.txt` (if you use a venv) for the FastAPI backend.
- GitHub PAT (`GITHUB_TOKEN`) with repo scope exported in backend env.
- Dev Spaces base URL (optional) in `frontend-workflow-app/.env`: `VITE_DEVSPACES_URL=https://devspaces.apps.<cluster>`.
- **Seed-data storage**: create a PersistentVolume backed by your seed data (e.g., manual NFS PV) and a `PersistentVolumeClaim` named `nfs-seed` that binds to it. The generated manifests mount this PVC.

## Quick Start

Backend (from repo root):

```bash
export GITHUB_TOKEN=<pat>
uvicorn main:app --reload
```

Frontend:

```bash
cd frontend-workflow-app
npm install
npm run dev
```

Visit `http://localhost:5173`.

## User Workflow

### 1. Collect Device Inputs
- In the **New Application** tab, Step 1 asks for `Device Name`, `Device ID`, and `Cluster FQDN`.
- Click **Next: Create Repository**. Backend clones the template, replaces placeholders in `bgd-*.yaml` + `bgd-pvc.yaml`, writes `devfile.yaml`, creates the GitHub repo, and pushes the content.

### 2. Configure Deployment Targets
- Step 2 collects cluster/ArgoCD details: `destination_server`, `destination_namespace`, ArgoCD URL/token, TLS toggle.
- Choose:
  - **Create ArgoCD YAML** → returns YAML only.
  - **Create & Deploy** → sends to ArgoCD REST API; Step 3 shows status + response.

### 3. Explore / Manage Devices
- Switch to **Device Dashboard** tab.
- Enter ArgoCD URL/token and Cluster FQDN in the connection panel → **Connect** to load devices.
- Table supports search/filter/sort/pagination.
- Actions per device:
  - **Repo**: opens the generated GitHub repo.
  - **Open in ArgoCD**: deep-link to the ArgoCD application.
  - **Edit**: launches OpenShift Dev Spaces using the repo’s `devfile.yaml`.
  - **Route**: opens `https://<device>-<id>.apps.<clusterFqdn>`.
  - **Sync**: hits backend `/argocd/sync`.

### 4. Iterate
- Step 3 → **Start Over** to provision another device (clears deployment status/yaml).
- Dashboard connection panel maintains settings so you can flip between creating and monitoring devices seamlessly.

## Behind the Scenes

| Step | Backend activity |
| --- | --- |
| Create repository | `/create-device-repo` clones the template repo into a temp dir, replaces all `{{DEVICE_*}}` placeholders (including `bgd-pvc.yaml`), writes a Dev Spaces-ready `devfile.yaml`, creates a new GitHub repo via REST, configures git user, injects PAT into the remote URL, commits/pushes `main`, then deletes the temp dir. |
| Generate YAML | `_build_argocd_app_yaml` creates a consistent ArgoCD `Application` manifest (`path: .`, `CreateNamespace=true`). The UI always shows this YAML regardless of deploy mode. |
| Create & Deploy | `/deploy-argocd-app` posts the Application payload to `<argocd_url>/api/v1/applications`. On HTTP 409 it PUTs (update). Successful calls trigger `/sync` and return `status: deployed` plus raw ArgoCD response for debugging. The resulting `Deployment` includes an init container that mounts `nfs-seed`, checks for seed data, and copies it into `/data` before the main container starts. |
| Dashboard fetch | `/argocd/apps` proxies to ArgoCD, strips each `item` to essentials (name, health, sync, repo URL, destination). Frontend parses application names into device name/ID, applies the user-provided Cluster FQDN, and surfaces Repo / ArgoCD / Dev Spaces / Route links. |
| Sync button | `/argocd/sync` posts to `<argocd_url>/api/v1/applications/<app>/sync` with `prune: true`. Errors bubble back to the dashboard console. |
