import React, { useCallback, useEffect, useMemo, useState } from "react";
import DeviceTable from "./DeviceTable";

const cardBase = "shadow-md rounded-xl p-6 border transition-colors";

const parseDeviceFields = (appName) => {
  if (!appName) return { deviceName: "", deviceId: "" };
  const trimmed = appName.startsWith("device-") ? appName.slice("device-".length) : appName;
  const lastDash = trimmed.lastIndexOf("-");
  if (lastDash === -1) return { deviceName: trimmed, deviceId: "" };
  const rawName = trimmed.slice(0, lastDash);
  const rawId = trimmed.slice(lastDash + 1);
  return {
    deviceName: rawName.replace(/-/g, " "),
    deviceId: rawId,
  };
};

export default function DeviceDashboard({
  darkMode,
  argocdUrl,
  argocdToken,
  disableTlsVerify = false,
  defaultClusterFqdn = "",
}) {
  const [devices, setDevices] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState("All");
  const [sortBy, setSortBy] = useState({ key: "deviceName", dir: "asc" });
  const [page, setPage] = useState(1);
  const pageSize = 8;

  const [formValues, setFormValues] = useState({
    url: argocdUrl || "",
    token: argocdToken || "",
    disableTls: disableTlsVerify,
    clusterFqdn: defaultClusterFqdn || "",
  });
  const [connection, setConnection] = useState({
    url: argocdUrl || "",
    token: argocdToken || "",
    disableTls: disableTlsVerify,
    clusterFqdn: defaultClusterFqdn || "",
  });

  useEffect(() => {
    setFormValues({
      url: argocdUrl || "",
      token: argocdToken || "",
      disableTls: disableTlsVerify,
      clusterFqdn: defaultClusterFqdn || "",
    });
    setConnection({
      url: argocdUrl || "",
      token: argocdToken || "",
      disableTls: disableTlsVerify,
      clusterFqdn: defaultClusterFqdn || "",
    });
  }, [argocdUrl, argocdToken, disableTlsVerify, defaultClusterFqdn]);

  const fetchDevices = useCallback(async (creds) => {
    if (!creds.url || !creds.token) return;
    setLoading(true);
    setError("");
    try {
      console.debug("Connecting with", creds);
      const form = new FormData();
      form.append("argocd_url", creds.url);
      form.append("argocd_token", creds.token);
      form.append("disable_tls", creds.disableTls ? "true" : "false");

      const res = await fetch("http://localhost:8000/argocd/apps", {
        method: "POST",
        body: form,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (data.error) throw new Error(data.error);

      const normalized = (data.apps || []).map((app) => {
        const applicationName = app.appName || app.name;
        const { deviceName, deviceId } = parseDeviceFields(applicationName);
        return {
          deviceName,
          deviceId,
          namespace: app.namespace,
          cluster: app.cluster,
          health: app.health,
          syncStatus: app.sync,
          lastSync: app.lastSync,
          repoUrl: app.repoUrl || "#",
          clusterFqdn: app.clusterFqdn || creds.clusterFqdn || "",
          appName: applicationName,
          name: applicationName,
        };
      });

      setDevices(normalized);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDevices(connection);
  }, [connection, fetchDevices]);

  const filtered = useMemo(() => {
    let data = devices;
    if (query) {
      const q = query.toLowerCase();
      data = data.filter(
        (d) =>
          d.deviceName?.toLowerCase().includes(q) ||
          d.deviceId?.toLowerCase().includes(q) ||
          d.namespace?.toLowerCase().includes(q)
      );
    }
    if (statusFilter !== "All") data = data.filter((d) => d.health === statusFilter);
    data = data.slice().sort((a, b) => {
      const A = (a[sortBy.key] || "").toString().toLowerCase();
      const B = (b[sortBy.key] || "").toString().toLowerCase();
      if (A < B) return sortBy.dir === "asc" ? -1 : 1;
      if (A > B) return sortBy.dir === "asc" ? 1 : -1;
      return 0;
    });
    return data;
  }, [devices, query, statusFilter, sortBy]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const pageData = filtered.slice((page - 1) * pageSize, page * pageSize);

  const tableChrome = darkMode ? "bg-gray-800 border-gray-700 text-gray-100" : "bg-white border-gray-200 text-gray-900";

  const onSort = (key) => setSortBy((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" }));
  const onPrev = () => setPage((p) => Math.max(1, p - 1));
  const onNext = () => setPage((p) => Math.min(totalPages, p + 1));

  const onSync = async (appName) => {
    try {
      console.debug("Syncing with", connection, "app:", appName);
      const form = new FormData();
      form.append("argocd_url", connection.url);
      form.append("argocd_token", connection.token);
      form.append("app_name", appName);
      form.append("disable_tls", connection.disableTls ? "true" : "false");

      await fetch("http://localhost:8000/argocd/sync", {
        method: "POST",
        body: form,
      });
    } catch (e) {
      console.error(e);
    }
  };

  const handleConnect = () => {
    setConnection({
      url: formValues.url.trim(),
      token: formValues.token.trim(),
      disableTls: formValues.disableTls,
      clusterFqdn: formValues.clusterFqdn.trim(),
    });
  };

  const connectionReady = Boolean(connection.url && connection.token);
  const controlChrome = darkMode ? "bg-gray-900 border-gray-700 text-gray-100" : "bg-gray-50 border-gray-200 text-gray-900";
  const inputChrome = darkMode
    ? "bg-gray-800 border-gray-600 text-gray-100 placeholder-gray-400"
    : "bg-white border-gray-300 text-gray-900 placeholder-gray-500";
  const devSpacesUrl = import.meta.env.VITE_DEVSPACES_URL || "";

  return (
    <div className={`${cardBase} ${tableChrome}`}>
      <h2 className="text-2xl font-semibold mb-3">Devices</h2>
      <div className={`${controlChrome} rounded-lg p-4 mb-4`}>
        <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
          <div>
            <p className="text-lg font-medium">ArgoCD connection</p>
            <p className="text-sm opacity-80">Enter credentials to load existing devices.</p>
          </div>
          {connectionReady && <span className="text-sm px-3 py-1 rounded-full bg-green-600 text-white">Connected</span>}
        </div>
        <div className="grid gap-3 md:grid-cols-2">
          <div>
            <label className="text-sm font-medium mb-1 block">ArgoCD URL</label>
            <input
              className={`w-full p-2 rounded ${inputChrome}`}
              placeholder="https://openshift-gitops.example.com"
              value={formValues.url}
              onChange={(e) => setFormValues((prev) => ({ ...prev, url: e.target.value }))}
            />
          </div>
          <div>
            <label className="text-sm font-medium mb-1 block">Token</label>
            <input
              type="password"
              className={`w-full p-2 rounded ${inputChrome}`}
              value={formValues.token}
              onChange={(e) => setFormValues((prev) => ({ ...prev, token: e.target.value }))}
            />
          </div>
          <div className="md:col-span-2">
            <label className="text-sm font-medium mb-1 block">Cluster FQDN</label>
            <input
              className={`w-full p-2 rounded ${inputChrome}`}
              placeholder="apps.cluster.example.com"
              value={formValues.clusterFqdn}
              onChange={(e) => setFormValues((prev) => ({ ...prev, clusterFqdn: e.target.value }))}
            />
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm mt-3">
          <input
            type="checkbox"
            checked={formValues.disableTls}
            onChange={(e) => setFormValues((prev) => ({ ...prev, disableTls: e.target.checked }))}
          />
          Disable TLS verification
        </label>
        <div className="flex gap-3 mt-4 flex-wrap">
          <button
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded disabled:opacity-50"
            onClick={handleConnect}
            disabled={!formValues.url || !formValues.token}
          >
            Connect
          </button>
          <button
            className="px-4 py-2 bg-gray-700 hover:bg-gray-800 text-white rounded disabled:opacity-50"
            onClick={() => fetchDevices(connection)}
            disabled={!connectionReady || loading}
          >
            Refresh
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 mb-4">
        <input
          className={`${darkMode ? "bg-gray-700 border-gray-600 text-gray-100" : "bg-gray-50 border-gray-300 text-gray-900"} w-full p-3 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 placeholder-gray-400`}
          placeholder="Search by app name or namespace…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <select
          className={`${darkMode ? "bg-gray-700 border-gray-600 text-gray-100" : "bg-gray-50 border-gray-300 text-gray-900"} w-full p-3 border rounded-lg max-w-xs`}
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
        >
          <option value="All">All Health</option>
          <option value="Healthy">Healthy</option>
          <option value="Degraded">Degraded</option>
          <option value="Error">Error</option>
          <option value="Unknown">Unknown</option>
        </select>
      </div>

      {loading ? (
        <p className="opacity-80">Loading…</p>
      ) : error ? (
        <p className="text-red-500">{error}</p>
      ) : (
        <DeviceTable
          darkMode={darkMode}
          data={pageData}
          sortBy={sortBy}
          onSort={onSort}
          page={{ current: page, totalItems: filtered.length }}
          totalPages={totalPages}
          onPrev={onPrev}
          onNext={onNext}
          argocdUrl={connection.url}
          devSpacesUrl={devSpacesUrl}
          onSync={onSync}
        />
      )}
    </div>
  );
}
