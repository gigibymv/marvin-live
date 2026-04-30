"use client";

import React, { useEffect, useState } from "react";

type Transcript = {
  id: string;
  title: string | null;
  expert_name: string | null;
  expert_role: string | null;
  line_count: number | null;
  uploaded_at: string | null;
};

export default function TranscriptUpload({ missionId }: { missionId: string }) {
  const [items, setItems] = useState<Transcript[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [text, setText] = useState("");
  const [title, setTitle] = useState("");
  const [expertName, setExpertName] = useState("");
  const [expertRole, setExpertRole] = useState("");

  async function load() {
    try {
      const r = await fetch(`/api/v1/missions/${missionId}/transcripts`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      setItems(body.transcripts || []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    }
  }

  useEffect(() => {
    void load();
  }, [missionId]);

  async function submit() {
    if (!text.trim()) {
      setError("paste a transcript first");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("text", text);
      if (title) fd.append("title", title);
      if (expertName) fd.append("expert_name", expertName);
      if (expertRole) fd.append("expert_role", expertRole);
      const r = await fetch(`/api/v1/missions/${missionId}/transcripts`, {
        method: "POST",
        body: fd,
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      setText("");
      setTitle("");
      setExpertName("");
      setExpertRole("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "upload failed");
    } finally {
      setBusy(false);
    }
  }

  async function remove(id: string) {
    if (!confirm("Delete this transcript?")) return;
    await fetch(`/api/v1/missions/${missionId}/transcripts/${id}`, {
      method: "DELETE",
    });
    await load();
  }

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h2 style={{ marginTop: 0 }}>Expert Calls</h2>
      {error && <div style={{ color: "#b00", marginBottom: 8 }}>error: {error}</div>}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginBottom: 8 }}>
        <input
          placeholder="Title (e.g. 'Tegus call — former CRO')"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          style={{ padding: 6 }}
        />
        <input
          placeholder="Expert name"
          value={expertName}
          onChange={(e) => setExpertName(e.target.value)}
          style={{ padding: 6 }}
        />
        <input
          placeholder="Expert role"
          value={expertRole}
          onChange={(e) => setExpertRole(e.target.value)}
          style={{ padding: 6, gridColumn: "1 / span 2" }}
        />
      </div>
      <textarea
        rows={10}
        placeholder="Paste transcript here. Speaker formats supported: 'Q: ...' / 'A: ...', '[Name]: ...', 'Name: ...', timestamps stripped."
        value={text}
        onChange={(e) => setText(e.target.value)}
        style={{ width: "100%", padding: 8, fontFamily: "monospace" }}
      />
      <button
        onClick={submit}
        disabled={busy}
        style={{ marginTop: 8, padding: "8px 14px", cursor: busy ? "wait" : "pointer" }}
      >
        {busy ? "Saving…" : "Add transcript"}
      </button>

      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14, marginTop: 16 }}>
        <thead>
          <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
            <th>Title</th>
            <th>Expert</th>
            <th>Role</th>
            <th>Lines</th>
            <th>Uploaded</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          {items.map((t) => (
            <tr key={t.id} style={{ borderBottom: "1px solid #eee" }}>
              <td style={{ padding: "6px 0" }}>{t.title || "—"}</td>
              <td>{t.expert_name || "—"}</td>
              <td>{t.expert_role || "—"}</td>
              <td>{t.line_count ?? "—"}</td>
              <td style={{ fontSize: 12, color: "#666" }}>
                {t.uploaded_at?.replace("T", " ").slice(0, 19) || ""}
              </td>
              <td>
                <button
                  onClick={() => void remove(t.id)}
                  style={{ fontSize: 12, color: "#b00", background: "none", border: "none", cursor: "pointer" }}
                >
                  delete
                </button>
              </td>
            </tr>
          ))}
          {items.length === 0 && (
            <tr>
              <td colSpan={6} style={{ padding: 12, color: "#888" }}>
                No transcripts yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
