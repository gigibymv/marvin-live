"use client";

import React, { useEffect, useRef, useState } from "react";

type DataRoomFile = {
  id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number | null;
  parse_error: string | null;
  parsed_chars: number;
  uploaded_at: string | null;
};

function fmtBytes(n: number | null): string {
  if (n === null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export default function DataRoomUpload({ missionId }: { missionId: string }) {
  const [files, setFiles] = useState<DataRoomFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function load() {
    try {
      const r = await fetch(`/api/v1/missions/${missionId}/data-room`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      setFiles(body.files || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    }
  }

  useEffect(() => {
    void load();
  }, [missionId]);

  async function upload(file: File) {
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      const r = await fetch(`/api/v1/missions/${missionId}/data-room/upload`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(fileId: string) {
    if (!confirm(`Delete this file?`)) return;
    try {
      await fetch(`/api/v1/missions/${missionId}/data-room/${fileId}`, {
        method: "DELETE",
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "delete failed");
    }
  }

  function onSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) void upload(f);
    e.target.value = "";
  }

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h2 style={{ marginTop: 0 }}>Data Room</h2>
      {error && <div style={{ color: "#b00", marginBottom: 8 }}>error: {error}</div>}

      <div style={{ marginBottom: 16 }}>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.xlsx,.xls,.docx,.txt,.md,.csv"
          onChange={onSelect}
          disabled={busy}
        />
        {busy && <span style={{ marginLeft: 8 }}>Uploading…</span>}
        <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
          PDF / XLSX / DOCX / TXT / CSV — max 25 MB
        </div>
      </div>

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
            <th>Filename</th>
            <th>Size</th>
            <th>Parsed chars</th>
            <th>Uploaded</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {files.map((f) => (
            <tr key={f.id} style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: "6px 0" }}>{f.filename}</td>
              <td>{fmtBytes(f.size_bytes)}</td>
              <td>
                {f.parse_error ? (
                  <span style={{ color: "#b00" }} title={f.parse_error}>
                    parse error
                  </span>
                ) : (
                  f.parsed_chars.toLocaleString()
                )}
              </td>
              <td style={{ fontSize: 12, color: "#666" }}>
                {f.uploaded_at?.replace("T", " ").slice(0, 19) || ""}
              </td>
              <td>
                <button
                  onClick={() => void remove(f.id)}
                  style={{ fontSize: 12, color: "#b00", background: "none", border: "none", cursor: "pointer" }}
                >
                  delete
                </button>
              </td>
            </tr>
          ))}
          {files.length === 0 && (
            <tr>
              <td colSpan={5} style={{ padding: 12, color: "#888" }}>
                No files uploaded yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
