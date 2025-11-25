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
- ArgoCD API access configured via `ARGOCD_URL` + `ARGOCD_TOKEN` environment variables (or Kubernetes Secret).
- Dev Spaces base URL (optional) in `frontend-workflow-app/.env`: `VITE_DEVSPACES_URL=https://devspaces.apps.<cluster>`.
- **Seed-data storage**: create a PersistentVolume backed by your seed data (e.g., manual NFS PV) and a `PersistentVolumeClaim` named `nfs-seed` that binds to it. The generated manifests mount this PVC.

## Quick Start

Backend:

```bash
cd backend
export GITHUB_TOKEN=<pat>
export GITHUB_USERNAME=<github-user>
export ARGOCD_URL=https://openshift-gitops-server-openshift-gitops.apps.<cluster>
export ARGOCD_TOKEN=<argo-api-token>
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
docker build -f backend/Dockerfile -t ghcr.io/<user>/device-workflow-backend backend

# Frontend (runtime API URL provided via ConfigMap)
docker build -f frontend-workflow-app/Dockerfile -t ghcr.io/<user>/device-workflow-frontend frontend-workflow-app
```

> These builds pull from `registry.redhat.io`, so authenticate first (`docker login registry.redhat.io`) using your Red Hat credentials.

Push both images to a registry that your cluster can pull from.

### Deploy with Helm (recommended)

1. Create a secret that holds GitHub + ArgoCD credentials (backend reads `GITHUB_TOKEN`/`GITHUB_USERNAME`/`ARGOCD_URL`/`ARGOCD_TOKEN`, plus optional `ARGOCD_DISABLE_TLS=true` if you need insecure connections):
   ```bash
   kubectl create secret generic device-workflow-secrets \
     --from-literal=GITHUB_TOKEN=<pat> \
     --from-literal=GITHUB_USERNAME=<github-user> \
     --from-literal=ARGOCD_URL=https://openshift-gitops-server-openshift-gitops.apps.<cluster> \
     --from-literal=ARGOCD_TOKEN=<argo-api-token>
   ```
   - Add `--from-literal=ARGOCD_DISABLE_TLS=true` if your ArgoCD endpoint uses self-signed certificates.
2. Install the provided Helm chart (defaults reference the image names above; override as needed):
   ```bash
   helm upgrade --install device-workflow charts/device-workflow \
     --set backend.image.repository=ghcr.io/<user>/device-workflow-backend \
     --set frontend.image.repository=ghcr.io/<user>/device-workflow-frontend \
     --set frontend.config.apiBaseUrl=http://device-workflow-backend.<namespace>.svc.cluster.local \
     --set frontend.config.argocdUrl=https://openshift-gitops-server-openshift-gitops.apps.<cluster>
   ```
   - Enable an OpenShift Route via `--set route.enabled=true --set route.host=device.apps.example.com`.
   - The chart injects these values into a ConfigMap-backed `env-config.js` so you can redeploy the frontend without rebuilding when the backend namespace/URL or ArgoCD host changes.
3. To uninstall: `helm uninstall device-workflow`.

> Legacy raw manifests (`k8s-backend.yaml`, `k8s-frontend.yaml`) remain for reference but the Helm chart keeps the two workloads in sync and is easier to configure on OpenShift (including Route support and runtime API base URL config).

## User Workflow

### 1. Collect Device Inputs
- In the **New Application** tab, Step 1 asks for `Device Name`, `Device ID`, `Cluster FQDN`, and Helm metadata (`Helm Repository URL`, `Helm Chart Name` (required unless you use an `oci://` reference that already includes the chart), `Chart Version`, and a `values.yaml` override).
- Click **Next: Create Repository**. Backend downloads the specified Helm chart, writes the provided `values.yaml` (or a generated default), adds a Dev Spaces-ready `devfile.yaml`, creates the GitHub repo, and pushes the chart + values file.

### 2. Configure Deployment Targets
- Step 2 collects cluster/ArgoCD details: `destination_server`, `destination_namespace`. ArgoCD URL/token/TLS settings are sourced from the backend secret.
- Choose:
  - **Create ArgoCD YAML** → returns YAML only.
  - **Create & Deploy** → sends to ArgoCD REST API; Step 3 shows status + response.

### 3. Explore / Manage Devices
- Switch to **Device Dashboard** tab.
- Enter Cluster FQDN (for route links) and click **Apply** → data is loaded using the backend's ArgoCD credentials.
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
| Create & Deploy | `/deploy-argocd-app` posts the Application payload to the configured `ARGOCD_URL` using the `ARGOCD_TOKEN` from the backend environment. On HTTP 409 it PUTs (update). Successful calls trigger `/sync` and return `status: deployed` plus raw ArgoCD response for debugging. The resulting `Deployment` includes an init container that mounts `nfs-seed`, checks for seed data, and copies it into `/data` before the main container starts. |
| Dashboard fetch | `/argocd/apps` proxies to ArgoCD using the same server-side credentials, strips each `item` to essentials (name, health, sync, repo URL, destination). Frontend parses application names into device name/ID, applies the user-provided Cluster FQDN, and surfaces Repo / ArgoCD / Dev Spaces / Route links. |
| Sync button | `/argocd/sync` posts to `<argocd_url>/api/v1/applications/<app>/sync` with `prune: true`. Errors bubble back to the dashboard console. |
