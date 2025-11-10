import React from "react";
import DeviceRow from "./DeviceRow";

export default function DeviceTable({ darkMode, data, sortBy, onSort, page, totalPages, onPrev, onNext, argocdUrl, devSpacesUrl, onSync }) {
  const th = (key, label) => (
    <th
      className="px-3 py-2 text-left text-sm font-semibold cursor-pointer select-none"
      onClick={() => onSort(key)}
      title={`Sort by ${label}`}
    >
      {label} {sortBy.key === key ? (sortBy.dir === "asc" ? "▲" : "▼") : ""}
    </th>
  );

  return (
    <>
      <div className="overflow-x-auto">
        <table className="min-w-full text-sm">
          <thead>
            <tr>
              {th("deviceName", "Device Name")}
              {th("deviceId", "Device ID")}
              <th className="px-3 py-2 text-left text-sm font-semibold">Namespace</th>
              <th className="px-3 py-2 text-left text-sm font-semibold">Cluster</th>
              <th className="px-3 py-2 text-left text-sm font-semibold">Health</th>
              <th className="px-3 py-2 text-left text-sm font-semibold">Sync</th>
              <th className="px-3 py-2 text-left text-sm font-semibold">Last Sync</th>
              <th className="px-3 py-2 text-left text-sm font-semibold">Actions</th>
            </tr>
          </thead>
          <tbody>
            {data.map((d) => (
              <DeviceRow key={`${d.deviceName}-${d.deviceId}`} d={d} argocdUrl={argocdUrl} devSpacesUrl={devSpacesUrl} onSync={onSync} />
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between mt-4">
        <span className="text-sm opacity-80">
          Page {page.current} / {totalPages} • {page.totalItems} devices
        </span>
        <div className="flex gap-2">
          <button className="px-3 py-2 bg-gray-700 hover:bg-gray-800 text-white rounded-lg" onClick={onPrev} disabled={page.current === 1}>
            Prev
          </button>
          <button className="px-3 py-2 bg-gray-700 hover:bg-gray-800 text-white rounded-lg" onClick={onNext} disabled={page.current === totalPages}>
            Next
          </button>
        </div>
      </div>
    </>
  );
}
