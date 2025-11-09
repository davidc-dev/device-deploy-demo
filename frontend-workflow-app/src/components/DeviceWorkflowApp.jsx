import React, { useState } from "react";

export default function DeviceWorkflowApp() {
  const [step, setStep] = useState(1);

  const [deviceName, setDeviceName] = useState("");
  const [deviceId, setDeviceId] = useState("");
  const [clusterFqdn, setClusterFqdn] = useState("");

  const [repoUrl, setRepoUrl] = useState("");

  const [destinationServer, setDestinationServer] = useState("");
  const [destinationNamespace, setDestinationNamespace] = useState("");

  const [argocdUrl, setArgocdUrl] = useState("");        // NEW
  const [argocdToken, setArgocdToken] = useState("");    // NEW

  const [argoYaml, setArgoYaml] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const API_BASE = "http://localhost:8000";

  // --------------------------------------------------------
  // STEP 1: Create Device Repo
  // --------------------------------------------------------
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
        body: formData
      });

      const data = await res.json();
      if (data.error) throw new Error(data.error);

      setRepoUrl(data.repo_url);
      setStep(2);
    } catch (err) {
      setError(err.message);
    }

    setLoading(false);
  };

  // --------------------------------------------------------
  // STEP 2: Generate YAML or Deploy via ArgoCD API
  // --------------------------------------------------------
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
        formData.append("argocd_token", argocdToken);
        formData.append("argocd_url", argocdUrl);
      } else {
        formData.append("use_argocd_api", "false");
      }

      const res = await fetch(`${API_BASE}/deploy-argocd-app`, {
        method: "POST",
        body: formData
      });

      const data = await res.json();
      if (data.error) throw new Error(data.error);

      setArgoYaml(data.argocd_yaml);
      setStep(3);
    } catch (err) {
      setError(err.message);
    }

    setLoading(false);
  };

  // --------------------------------------------------------
  // UI RENDERING
  // --------------------------------------------------------
  return (
    <div className="p-10 max-w-xl mx-auto">

      {/* STEP 1 ------------------------------------------------------- */}
      {step === 1 && (
        <div>
          <h1 className="text-3xl font-bold mb-4">Create New Application</h1>
          <p className="mb-4 text-gray-600">Step 1: Enter device information.</p>

          <label className="block mb-2 font-medium">Device Name</label>
          <input
            className="w-full p-2 border rounded mb-4"
            value={deviceName}
            onChange={(e) => setDeviceName(e.target.value)}
          />

          <label className="block mb-2 font-medium">Device ID</label>
          <input
            className="w-full p-2 border rounded mb-4"
            value={deviceId}
            onChange={(e) => setDeviceId(e.target.value)}
          />

          <label className="block mb-2 font-medium">Cluster FQDN</label>
          <input
            className="w-full p-2 border rounded mb-6"
            value={clusterFqdn}
            onChange={(e) => setClusterFqdn(e.target.value)}
          />

          {error && <p className="text-red-600 mb-4">{error}</p>}

          <button
            onClick={handleCreateRepo}
            disabled={loading}
            className="px-4 py-2 bg-blue-600 text-white rounded"
          >
            {loading ? "Processing..." : "Next: Create Repository"}
          </button>
        </div>
      )}

      {/* STEP 2 ------------------------------------------------------- */}
      {step === 2 && (
        <div>
          <h1 className="text-3xl font-bold mb-4">Deployment Target</h1>
          <p className="mb-4 text-gray-600">
            Step 2: Enter cluster and ArgoCD details.
          </p>

          <label className="block mb-2 font-medium">Cluster API URL</label>
          <input
            className="w-full p-2 border rounded mb-4"
            value={destinationServer}
            onChange={(e) => setDestinationServer(e.target.value)}
          />

          <label className="block mb-2 font-medium">Destination Namespace</label>
          <input
            className="w-full p-2 border rounded mb-4"
            value={destinationNamespace}
            onChange={(e) => setDestinationNamespace(e.target.value)}
          />

          {/* NEW: ArgoCD URL */}
          <label className="block mb-2 font-medium">ArgoCD API URL</label>
          <input
            className="w-full p-2 border rounded mb-4"
            placeholder="https://argocd-server-openshift-gitops.apps.example.com"
            value={argocdUrl}
            onChange={(e) => setArgocdUrl(e.target.value)}
          />

          {/* NEW: ArgoCD Token */}
          <label className="block mb-2 font-medium">ArgoCD Auth Token</label>
          <input
            type="password"
            className="w-full p-2 border rounded mb-6"
            value={argocdToken}
            onChange={(e) => setArgocdToken(e.target.value)}
          />

          {error && <p className="text-red-600 mb-4">{error}</p>}

          <div className="flex gap-4">
            <button
              onClick={() => handleGenerateYaml(false)}
              disabled={loading}
              className="px-4 py-2 bg-gray-700 text-white rounded"
            >
              Create ArgoCD YAML
            </button>

            <button
              onClick={() => handleGenerateYaml(true)}
              disabled={loading}
              className="px-4 py-2 bg-green-600 text-white rounded"
            >
              {loading ? "Deploying..." : "Create and Deploy to Cluster"}
            </button>
          </div>
        </div>
      )}

      {/* STEP 3 ------------------------------------------------------- */}
      {step === 3 && (
        <div>
          <h1 className="text-3xl font-bold mb-4">ArgoCD Deployment YAML</h1>
          <textarea
            className="w-full h-80 p-3 border rounded font-mono text-sm"
            readOnly
            value={argoYaml}
          />

          <button
            onClick={() => setStep(1)}
            className="mt-6 px-4 py-2 bg-blue-600 text-white rounded"
          >
            Start Over
          </button>
        </div>
      )}
    </div>
  );
}
