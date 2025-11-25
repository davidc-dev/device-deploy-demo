# Device Workflow Application

Single-page workflow (React + Vite) that:

1. Creates a GitHub repo per device (templated manifests + Dev Spaces devfile).
2. Generates or deploys an ArgoCD Application for that repo.
3. Displays an ArgoCD-backed device dashboard with Repo / ArgoCD / Dev Spaces / Route / Sync shortcuts.

Backend: FastAPI service in `backend/main.py` — runs at `http://localhost:8000` by default.

## Prerequisites

- Node 18+ and npm for the frontend.
- Python 3.10+, plus `pip install -r requirements.txt` (if you use a venv) for the FastAPI backend.
- [Helm](https://helm.sh/docs/intro/install/) CLI available on the backend host (used to pull charts).
- GitHub PAT (`GITHUB_TOKEN`) with repo scope exported in backend env.
- Dev Spaces base URL (optional) in `frontend-workflow-app/.env`: `VITE_DEVSPACES_URL=https://devspaces.apps.<cluster>`.
- **Seed-data storage**: create a PersistentVolume backed by your seed data (e.g., manual NFS PV) and a `PersistentVolumeClaim` named `nfs-seed` that binds to it. The generated manifests mount this PVC.

## Quick Start

Backend:

```bash
cd backend
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

## Containers & Kubernetes

### Build Images

```bash
# Backend (installs Helm in image)
docker build -f backend/Dockerfile -t ghcr.io/<user>/device-workflow-backend .

# Frontend (override API base if backend runs in-cluster)
docker build \
  -f frontend-workflow-app/Dockerfile \
  --build-arg VITE_API_BASE_URL=http://device-workflow-backend.default.svc.cluster.local \
  -t ghcr.io/<user>/device-workflow-frontend .
```

> These builds pull from `registry.redhat.io`, so authenticate first (`docker login registry.redhat.io`) using your Red Hat credentials.

Push both images to a registry that your cluster can pull from.

### Deploy to Kubernetes

1. Create a secret that holds your GitHub credentials (backend reads `GITHUB_TOKEN` + optionally `GITHUB_USERNAME`):
   ```bash
   kubectl create secret generic device-workflow-secrets \
     --from-literal=GITHUB_TOKEN=<pat> \
     --from-literal=GITHUB_USERNAME=<github-user>
   ```
2. Edit `k8s-backend.yaml` and `k8s-frontend.yaml` to point to your pushed images (and adjust namespaces if needed).
3. Apply the manifests:
   ```bash
   kubectl apply -f k8s-backend.yaml
   kubectl apply -f k8s-frontend.yaml
   ```
4. Expose the frontend service externally (e.g., via Ingress/Route or port-forward) to access the UI. The frontend image bakes the API URL via the `VITE_API_BASE_URL` build arg so it automatically speaks to the cluster backend Service.
   - The frontend container now serves on port `8080` (RHEL UBI nginx), while the Service maps cluster port 80 to the pod’s 8080.

## User Workflow

### 1. Collect Device Inputs
- In the **New Application** tab, Step 1 asks for `Device Name`, `Device ID`, `Cluster FQDN`, and Helm metadata (`Helm Repository URL`, `Helm Chart Name` (required unless you use an `oci://` reference that already includes the chart), `Chart Version`, and a `values.yaml` override).
- Click **Next: Create Repository**. Backend downloads the specified Helm chart, writes the provided `values.yaml` (or a generated default), adds a Dev Spaces-ready `devfile.yaml`, creates the GitHub repo, and pushes the chart + values file.

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
| Create repository | `/create-device-repo` pulls the requested Helm chart into a temp dir, stores the user-provided (or default) `values.yaml`, writes a Dev Spaces-ready `devfile.yaml`, creates a new GitHub repo via REST, configures git user, injects PAT into the remote URL, commits/pushes `main`, then deletes the temp dir. |
| Generate YAML | `_build_argocd_app_yaml` creates a consistent ArgoCD `Application` manifest (`path: .`, `CreateNamespace=true`). The UI always shows this YAML regardless of deploy mode. |
| Create & Deploy | `/deploy-argocd-app` posts the Application payload to `<argocd_url>/api/v1/applications`. On HTTP 409 it PUTs (update). Successful calls trigger `/sync` and return `status: deployed` plus raw ArgoCD response for debugging. The resulting `Deployment` includes an init container that mounts `nfs-seed`, checks for seed data, and copies it into `/data` before the main container starts. |
| Dashboard fetch | `/argocd/apps` proxies to ArgoCD, strips each `item` to essentials (name, health, sync, repo URL, destination). Frontend parses application names into device name/ID, applies the user-provided Cluster FQDN, and surfaces Repo / ArgoCD / Dev Spaces / Route links. |
| Sync button | `/argocd/sync` posts to `<argocd_url>/api/v1/applications/<app>/sync` with `prune: true`. Errors bubble back to the dashboard console. |
