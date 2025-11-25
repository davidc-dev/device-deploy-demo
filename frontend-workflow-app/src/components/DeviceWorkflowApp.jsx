import React, { useState } from "react";
import DeviceDashboard from "./DeviceDashboard";

const cardBaseWF = "shadow-md rounded-xl p-6 border transition-colors";
const headerWF = "text-2xl font-semibold mb-3";
const subheaderWF = "mb-6 opacity-80";
const inputWF = "w-full p-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4 transition-colors placeholder-gray-400";
const btnPrimaryWF = "px-5 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition";
const btnSecondaryWF = "px-5 py-3 bg-gray-700 hover:bg-gray-800 text-white rounded-lg transition";
const btnSuccessWF = "px-5 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg transition";
const tabBtnWF = (active) => `${active ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-800 hover:bg-gray-300"} px-4 py-2 rounded-lg transition`;

export default function DeviceWorkflowApp() {
  const [step, setStep] = useState(1);
  const [view, setView] = useState("workflow");

  const [deviceName, setDeviceName] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [clusterFqdn, setClusterFqdn] = useState("");
  const [helmRepoUrl, setHelmRepoUrl] = useState("");
  const [helmChartName, setHelmChartName] = useState("");
  const [helmChartVersion, setHelmChartVersion] = useState("");
  const [helmValuesYaml, setHelmValuesYaml] = useState("");

  const [repoUrl, setRepoUrl] = useState("");

  const [destinationServer, setDestinationServer] = useState("https://kubernetes.default.svc");
  const [destinationNamespace, setDestinationNamespace] = useState("");

  const [argoYaml, setArgoYaml] = useState("");
  const [deploymentStatus, setDeploymentStatus] = useState("");
  const [argoApiResponse, setArgoApiResponse] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const runtimeConfig = typeof window !== "undefined" ? window.__APP_CONFIG__ || {} : {};
  const isHttps = typeof window !== "undefined" ? window.location.protocol === "https:" : false;
  const API_BASE = "/api";
  const ARGOCD_UI_BASE = runtimeConfig.argocdUrl || "";

  const [darkMode, setDarkMode] = useState(false);
  const pageBg = darkMode ? "bg-gray-900 text-gray-100" : "bg-gray-100 text-gray-900";
  const cardBg = darkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200";
  const inputTheme = darkMode ? "bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-300" : "bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-500";

  const handleCreateRepo = async () => {
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("device_id", deviceId);
      formData.append("device_name", deviceName);
      formData.append("cluster_fqdn", clusterFqdn);
      formData.append("helm_repo_url", helmRepoUrl);
      formData.append("helm_chart_name", helmChartName);
      formData.append("helm_chart_version", helmChartVersion);
      formData.append("helm_values_yaml", helmValuesYaml);

      const res = await fetch(`${API_BASE}/create-device-repo`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (data.error) throw new Error(data.error);

      setRepoUrl(data.repo_url);
      setDeploymentStatus("");
      setArgoApiResponse("");
      setArgoYaml("");
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    setLoading(false);
  };

  const handleGenerateYaml = async (deploy) => {
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("repo_url", repoUrl);
      formData.append("device_id", deviceId);
      formData.append("device_name", deviceName);
      formData.append("destination_server", destinationServer);
      formData.append("destination_namespace", destinationNamespace);
      formData.append("cluster_fqdn", clusterFqdn);

      if (deploy) {
        formData.append("use_argocd_api", "true");
      } else {
        formData.append("use_argocd_api", "false");
      }

      const res = await fetch(`${API_BASE}/deploy-argocd-app`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (data.error) throw new Error(data.error);

      setArgoYaml(data.argocd_yaml);
      setDeploymentStatus(data.status || (deploy ? "deployed" : "yaml_only"));
      setArgoApiResponse(data.argocd_response || "");
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }

    setLoading(false);
  };

  return (
    <div className={`min-h-screen w-full p-10 transition ${pageBg}`}>
      <div className="max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-6">
          <div className="flex gap-2">
            <button className={tabBtnWF(view === "workflow")} onClick={() => setView("workflow")}>
              New Application
            </button>
            <button className={tabBtnWF(view === "dashboard")} onClick={() => setView("dashboard")}>
              Device Dashboard
            </button>
          </div>

          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={darkMode} onChange={(e) => setDarkMode(e.target.checked)} />
            <span className="text-sm">Dark Mode</span>
          </label>
        </div>

        {view === "workflow" && (
          <div className="grid grid-cols-1 gap-6">
            {step === 1 && (
              <div className={`${cardBaseWF} ${cardBg}`}>
                <h1 className={headerWF}>Create New Device</h1>
                <p className={subheaderWF}>Step 1: Enter device information.</p>

                <label className="font-medium">Device Name</label>
                <input className={`${inputWF} ${inputTheme}`} value={deviceName} onChange={(e) => setDeviceName(e.target.value)} />

                <label className="font-medium">Device ID</label>
                <input className={`${inputWF} ${inputTheme}`} value={deviceId} onChange={(e) => setDeviceId(e.target.value)} />

                <label className="font-medium">Cluster FQDN</label>
                <input className={`${inputWF} ${inputTheme}`} value={clusterFqdn} onChange={(e) => setClusterFqdn(e.target.value)} />

                <label className="font-medium">Helm Repository URL</label>
                <input className={`${inputWF} ${inputTheme}`} value={helmRepoUrl} onChange={(e) => setHelmRepoUrl(e.target.value)} placeholder="e.g., oci://registry/namespace/chart" />

                <label className="font-medium">Helm Chart Name</label>
                <input
                  className={`${inputWF} ${inputTheme}`}
                  value={helmChartName}
                  onChange={(e) => setHelmChartName(e.target.value)}
                  placeholder="e.g., workflow-chart (optional when repo URL is oci://...)"
                />

                <label className="font-medium">Chart Version</label>
                <input className={`${inputWF} ${inputTheme}`} value={helmChartVersion} onChange={(e) => setHelmChartVersion(e.target.value)} placeholder="latest" />

                <label className="font-medium">values.yaml Content</label>
                <textarea
                  className={`w-full h-48 p-3 border rounded-lg font-mono text-sm mb-4 ${inputTheme}`}
                  value={helmValuesYaml}
                  onChange={(e) => setHelmValuesYaml(e.target.value)}
                  placeholder="Paste custom values YAML here"
                />

                {error && <p className="text-red-500 mb-4">{error}</p>}

                <button onClick={handleCreateRepo} className={btnPrimaryWF} disabled={loading}>
                  {loading ? "Processing..." : "Next: Create Repository"}
                </button>
              </div>
            )}

            {step === 2 && (
              <div className={`${cardBaseWF} ${cardBg}`}>
                <h1 className={headerWF}>Deployment Target</h1>
                <p className={subheaderWF}>Step 2: Enter cluster and ArgoCD details.</p>

                <label className="font-medium">Cluster API URL</label>
                <input className={`${inputWF} ${inputTheme}`} value={destinationServer} onChange={(e) => setDestinationServer(e.target.value)} />

                <label className="font-medium">Destination Namespace</label>
                <input className={`${inputWF} ${inputTheme}`} value={destinationNamespace} onChange={(e) => setDestinationNamespace(e.target.value)} />

                {error && <p className="text-red-500 mb-4">{error}</p>}

                <div className="flex gap-4">
                  <button onClick={() => handleGenerateYaml(false)} className={btnSecondaryWF}>
                    Create ArgoCD YAML
                  </button>
                  <button onClick={() => handleGenerateYaml(true)} className={btnSuccessWF}>
                    {loading ? "Deploying..." : "Create & Deploy"}
                  </button>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className={`${cardBaseWF} ${cardBg}`}>
                <h1 className={headerWF}>ArgoCD Deployment YAML</h1>
                {deploymentStatus && (
                  <p className="mb-4 text-sm">
                    Deployment mode:{" "}
                    <span className="font-semibold">
                      {deploymentStatus === "deployed" ? "ArgoCD API (application created)" : "YAML only"}
                    </span>
                  </p>
                )}
                {argoApiResponse && (
                  <details className="mb-4">
                    <summary className="cursor-pointer text-sm text-blue-500">View ArgoCD API response</summary>
                    <pre className="mt-2 p-3 rounded bg-black/10 text-xs whitespace-pre-wrap break-all">{argoApiResponse}</pre>
                  </details>
                )}
                <textarea className={`w-full h-80 p-3 border rounded-lg font-mono text-sm ${inputTheme}`} readOnly value={argoYaml} />

                <button
                  onClick={() => {
                    setStep(1);
                    setDeploymentStatus("");
                    setArgoApiResponse("");
                    setArgoYaml("");
                  }}
                  className={`${btnPrimaryWF} mt-6`}
                >
                  Start Over
                </button>
              </div>
            )}
          </div>
        )}

        {view === "dashboard" && (
          <DeviceDashboard
            darkMode={darkMode}
            defaultClusterFqdn={clusterFqdn}
            apiBase={API_BASE}
            argocdUiUrl={ARGOCD_UI_BASE}
          />
        )}
      </div>
    </div>
  );
}
