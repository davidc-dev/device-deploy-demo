import React, { useState } from "react";

// Utility styles (Tailwind-like class names without installing Tailwind)
const cardBase = "shadow-md rounded-xl p-6 border transition-colors";
const header = "text-2xl font-semibold mb-3"; // inherits color for dark mode
const subheader = "mb-6 opacity-80"; // inherits color
const inputBase = "w-full p-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 mb-4 transition-colors placeholder-opacity-90";
const btnPrimary = "px-5 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition";
const btnSecondary = "px-5 py-3 bg-gray-700 hover:bg-gray-800 text-white rounded-lg transition";
const btnSuccess = "px-5 py-3 bg-green-600 hover:bg-green-700 text-white rounded-lg transition";

export default function DeviceWorkflowApp() {
  const [step, setStep] = useState(1);

  const [deviceName, setDeviceName] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [clusterFqdn, setClusterFqdn] = useState("");

  const [repoUrl, setRepoUrl] = useState("");

  const [destinationServer, setDestinationServer] = useState("https://kubernetes.default.svc");
  const [destinationNamespace, setDestinationNamespace] = useState("device-apps");

  const [argocdUrl, setArgocdUrl] = useState("");("https://openshift-gitops-server-openshift-gitops.apps.{{CLUSTER_DOMAIN}}");
  const [argocdToken, setArgocdToken] = useState("");
  const [disableTlsVerify, setDisableTlsVerify] = useState(true);

  const [argoYaml, setArgoYaml] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const API_BASE = "http://localhost:8000";

  // Dark mode toggle
  const [darkMode, setDarkMode] = useState(false);
  const pageBg = darkMode ? "bg-gray-900 text-gray-100" : "bg-gray-100 text-gray-900";
  const cardBg = darkMode ? "bg-gray-800 border-gray-700" : "bg-white border-gray-200";
  const inputTheme = darkMode
    ? "bg-gray-700 border-gray-600 text-gray-100 placeholder-gray-300"
    : "bg-gray-50 border-gray-300 text-gray-900 placeholder-gray-500";

  // Auto-update ArgoCD URL when cluster FQDN changes
  React.useEffect(() => {
    // Only auto-fill if user hasn't manually overridden
    if (clusterFqdn && (argocdUrl === "" || argocdUrl.includes("openshift-gitops-server-openshift-gitops.apps"))) {
      setArgocdUrl(`https://openshift-gitops-server-openshift-gitops.apps.${clusterFqdn}`);
    }
  }, [clusterFqdn]);

  // STEP 1 --------------------------------------------------------
  const handleCreateRepo = async () => {
    setLoading(true);
    setError("");

    try {
      const formData = new FormData();
      formData.append("device_id", deviceId);
      formData.append("device_name", deviceName);
      formData.append("cluster_fqdn", clusterFqdn);

      const res = await fetch(`${API_BASE}/create-device-repo`, {
        method: "POST",
        body: formData,
      });

      const data = await res.json();
      if (data.error) throw new Error(data.error);

      setRepoUrl(data.repo_url);
      setStep(2);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    setLoading(false);
  };

  // STEP 2 --------------------------------------------------------
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
        formData.append("argocd_url", argocdUrl);
        formData.append("argocd_token", argocdToken);
        formData.append("disable_tls", disableTlsVerify ? "true" : "false");
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
      setStep(3);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }

    setLoading(false);
  };

  return (
    <div className={`min-h-screen w-full p-10 transition ${pageBg}`}>
      <div className="max-w-2xl mx-auto">
        {/* Dark Mode Toggle */}
        <div className="flex justify-end mb-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={darkMode}
              onChange={(e) => setDarkMode(e.target.checked)}
            />
            <span className="text-sm">Dark Mode</span>
          </label>
        </div>

        {/* STEP 1 ------------------------------------------------------- */}
        {step === 1 && (
          <div className={`${cardBase} ${cardBg}`}>
            <h1 className={header}>Create New Application</h1>
            <p className={subheader}>Step 1: Enter device information.</p>

            <label className="font-medium">Device Name</label>
            <input
              className={`${inputBase} ${inputTheme}`}
              value={deviceName}
              onChange={(e) => setDeviceName(e.target.value)}
            />

            <label className="font-medium">Device ID</label>
            <input
              className={`${inputBase} ${inputTheme}`}
              value={deviceId}
              onChange={(e) => setDeviceId(e.target.value)}
            />

            <label className="font-medium">Cluster FQDN</label>
            <input
              className={`${inputBase} ${inputTheme}`}
              value={clusterFqdn}
              onChange={(e) => setClusterFqdn(e.target.value)}
            />

            {error && <p className="text-red-500 mb-4">{error}</p>}

            <button onClick={handleCreateRepo} className={btnPrimary} disabled={loading}>
              {loading ? "Processing..." : "Next: Create Repository"}
            </button>
          </div>
        )}

        {/* STEP 2 ------------------------------------------------------- */}
        {step === 2 && (
          <div className={`${cardBase} ${cardBg}`}>
            <h1 className={header}>Deployment Target</h1>
            <p className={subheader}>Step 2: Enter cluster and ArgoCD details.</p>

            <label className="font-medium">Cluster API URL</label>
            <input
              className={`${inputBase} ${inputTheme}`}
              value={destinationServer}
              onChange={(e) => setDestinationServer(e.target.value)}
            />

            <label className="font-medium">Destination Namespace</label>
            <input
              className={`${inputBase} ${inputTheme}`}
              value={destinationNamespace}
              onChange={(e) => setDestinationNamespace(e.target.value)}
            />

            <label className="font-medium">ArgoCD API URL</label>
            <input
              className={`${inputBase} ${inputTheme}`}
              value={argocdUrl}
              onChange={(e) => setArgocdUrl(e.target.value)}
            />

            <label className="font-medium">ArgoCD Token</label>
            <input
              type="password"
              className={`${inputBase} ${inputTheme}`}
              value={argocdToken}
              onChange={(e) => setArgocdToken(e.target.value)}
            />

            <label className="flex items-center gap-2 mb-4">
              <input
                type="checkbox"
                checked={disableTlsVerify}
                onChange={(e) => setDisableTlsVerify(e.target.checked)}
              />
              <span>Disable TLS verification (insecure)</span>
            </label>

            {error && <p className="text-red-500 mb-4">{error}</p>}

            <div className="flex gap-4">
              <button onClick={() => handleGenerateYaml(false)} className={btnSecondary}>
                Create ArgoCD YAML
              </button>
              <button onClick={() => handleGenerateYaml(true)} className={btnSuccess}>
                {loading ? "Deploying..." : "Create & Deploy"}
              </button>
            </div>
          </div>
        )}

        {/* STEP 3 ------------------------------------------------------- */}
        {step === 3 && (
          <div className={`${cardBase} ${cardBg}`}>
            <h1 className={header}>ArgoCD Deployment YAML</h1>
            <textarea
              className={`w-full h-80 p-3 border rounded-lg font-mono text-sm ${inputTheme}`}
              readOnly
              value={argoYaml}
            />

            <button onClick={() => setStep(1)} className={`${btnPrimary} mt-6`}>
              Start Over
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
