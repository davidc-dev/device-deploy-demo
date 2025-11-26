import React from "react";

const btnSecondary = "px-3 py-2 bg-gray-700 hover:bg-gray-800 text-white rounded-lg transition text-sm";
const btnPrimary = "px-3 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition text-sm";
const btnSuccess = "px-3 py-2 bg-green-600 hover:bg-green-700 text-white rounded-lg transition text-sm";
const btnRoute = "px-3 py-2 bg-purple-600 hover:bg-purple-700 text-white rounded-lg transition text-sm";

function StatusBadge({ status }) {
  const map = {
    Healthy: "bg-green-100 text-green-800",
    Degraded: "bg-yellow-100 text-yellow-800",
    Error: "bg-red-100 text-red-800",
    Unknown: "bg-gray-100 text-gray-800",
  };
  const cls = map[status] || map.Unknown;
  return <span className={`inline-block text-xs px-2 py-1 rounded ${cls}`}>{status}</span>;
}

const buildDevSpacesLink = (baseUrl, repoUrl) => {
  if (!baseUrl || !repoUrl || repoUrl === "#") return null;
  try {
    const parsed = new URL(repoUrl);
    if (!parsed.hostname.includes("github.com")) return null;
    const pathParts = parsed.pathname.replace(/\.git$/, "").split("/").filter(Boolean);
    if (pathParts.length < 2) return null;
    const [owner, repo] = pathParts;
    const rawDevfile = `https://raw.githubusercontent.com/${owner}/${repo}/refs/heads/main/devfile.yaml`;
    return `${baseUrl.replace(/\/$/, "")}/#/${rawDevfile}`;
  } catch {
    return null;
  }
};

export default function DeviceRow({ d, argocdUrl, devSpacesUrl, onSync }) {
  const devSpacesLink = buildDevSpacesLink(devSpacesUrl, d.repoUrl);
  const routeUrl = d.routeHost ? `https://${d.routeHost}` : null;

  return (
    <tr className="border-t border-gray-600/20">
      <td className="px-3 py-2 font-medium">{d.deviceName}</td>
      <td className="px-3 py-2">{d.deviceId}</td>
      <td className="px-3 py-2">{d.namespace}</td>
      <td className="px-3 py-2 truncate max-w-[240px]" title={d.cluster}>
        {d.cluster}
      </td>
      <td className="px-3 py-2"><StatusBadge status={d.health} /></td>
      <td className="px-3 py-2">{d.syncStatus}</td>
      <td className="px-3 py-2">{new Date(d.lastSync).toLocaleString()}</td>
      <td className="px-3 py-2 flex flex-wrap gap-2">
        <a className={btnSecondary} href={d.repoUrl} target="_blank" rel="noreferrer">
          Repo
        </a>
        {argocdUrl && (
          <a
            className={btnPrimary}
            href={`${argocdUrl.replace(/\/$/, "")}/applications/${encodeURIComponent(d.appName)}`}
            target="_blank"
            rel="noreferrer"
          >
            Open in ArgoCD
          </a>
        )}
        {devSpacesLink && (
          <a className={btnSuccess} href={devSpacesLink} target="_blank" rel="noreferrer">
            Edit
          </a>
        )}
        {routeUrl && (
          <a className={btnRoute} href={routeUrl} target="_blank" rel="noreferrer">
            Route
          </a>
        )}
        <button onClick={() => onSync(d.name)} className="px-3 py-1 bg-blue-600 hover:bg-blue-700 text-white rounded">
          Sync
        </button>
      </td>
    </tr>
  );
}
