"use client";

/**
 * Chantier 4 CP3: inline deliverable preview modal.
 *
 * Click "Open" on a ready deliverable → fetch /deliverables/{id}/preview →
 * render markdown content + a sidebar of linked findings.
 *
 * - .md → rendered as preformatted text (no extra deps)
 * - .pdf → embed via download URL in an iframe
 * - other → falls back to plain text
 */

import { useEffect, useState } from "react";

import { API_BASE, getDeliverableDownloadUrl } from "@/lib/missions/api";

interface LinkedFinding {
  id: string;
  claim_text: string;
  agent_id: string | null;
  confidence: string | null;
  hypothesis_label: string | null;
  impact: "load_bearing" | "supporting" | "color" | null;
}

interface PreviewPayload {
  deliverable_id: string;
  deliverable_type: string;
  mission_id: string;
  file_path: string;
  content_type: "markdown" | "pdf" | "text";
  content: string;
  linked_findings: LinkedFinding[];
}

interface Props {
  deliverableId: string | null;
  onClose: () => void;
}

export function DeliverablePreview({ deliverableId, onClose }: Props) {
  const [data, setData] = useState<PreviewPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!deliverableId) {
      setData(null);
      setError(null);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetch(`${API_BASE}/deliverables/${deliverableId}/preview`)
      .then((r) => {
        if (!r.ok) throw new Error(`Preview failed: ${r.status}`);
        return r.json();
      })
      .then((payload: PreviewPayload) => {
        if (!cancelled) setData(payload);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [deliverableId]);

  if (!deliverableId) return null;

  const downloadHref = data ? getDeliverableDownloadUrl(data.file_path) : "";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Deliverable preview"
      onClick={onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(26,24,20,.55)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        zIndex: 100,
        padding: "32px",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: "var(--paper, #F4F0EA)",
          width: "min(1100px, 100%)",
          height: "min(800px, 90vh)",
          display: "grid",
          gridTemplateColumns: "1fr 320px",
          gridTemplateRows: "auto 1fr",
          border: "1px solid var(--ink, #1A1814)",
          fontFamily: "var(--g, system-ui)",
          color: "var(--ink2, #3A362F)",
        }}
      >
        <header
          style={{
            gridColumn: "1 / -1",
            padding: "14px 22px",
            borderBottom: "1px solid var(--ink, #1A1814)",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            gap: "12px",
          }}
        >
          <div style={{ display: "flex", alignItems: "baseline", gap: "12px" }}>
            <span style={{ fontFamily: "var(--m, monospace)", fontSize: "10px", fontWeight: 700, letterSpacing: ".18em", textTransform: "uppercase" }}>
              Deliverable
            </span>
            <span style={{ fontSize: "16px", fontWeight: 600 }}>
              {data?.deliverable_type ?? deliverableId}
            </span>
          </div>
          <div style={{ display: "flex", gap: "10px" }}>
            {data && (
              <a
                href={downloadHref}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  fontFamily: "var(--m, monospace)",
                  fontSize: "10px",
                  letterSpacing: ".12em",
                  textTransform: "uppercase",
                  color: "var(--ink, #1A1814)",
                  textDecoration: "underline",
                }}
              >
                Download ↓
              </a>
            )}
            <button
              type="button"
              onClick={onClose}
              style={{
                fontFamily: "var(--m, monospace)",
                fontSize: "10px",
                letterSpacing: ".12em",
                textTransform: "uppercase",
                background: "transparent",
                border: "1px solid var(--ink, #1A1814)",
                padding: "4px 10px",
                cursor: "pointer",
              }}
            >
              Close
            </button>
          </div>
        </header>

        <main style={{ overflow: "auto", padding: "22px", borderRight: "1px solid var(--rule, rgba(26,24,20,.10))" }}>
          {loading && <p style={{ fontFamily: "var(--m, monospace)", fontSize: "11px", color: "var(--muted, #78716A)" }}>Loading preview…</p>}
          {error && <p style={{ color: "var(--red, #c43)" }}>{error}</p>}
          {data && data.content_type === "pdf" && (
            <iframe
              title="PDF preview"
              src={downloadHref}
              style={{ width: "100%", height: "100%", border: "1px solid var(--rule, rgba(26,24,20,.10))" }}
            />
          )}
          {data && data.content_type !== "pdf" && (
            <pre
              style={{
                whiteSpace: "pre-wrap",
                fontFamily: data.content_type === "markdown" ? "var(--g, system-ui)" : "var(--m, monospace)",
                fontSize: "13.5px",
                lineHeight: 1.55,
                color: "var(--ink2, #3A362F)",
                margin: 0,
              }}
            >
              {data.content || "(empty file)"}
            </pre>
          )}
        </main>

        <aside style={{ overflow: "auto", padding: "18px 20px", background: "var(--bone, #EEE9DD)" }}>
          <h2
            style={{
              fontFamily: "var(--m, monospace)",
              fontSize: "9px",
              fontWeight: 700,
              letterSpacing: ".18em",
              textTransform: "uppercase",
              marginBottom: "10px",
              paddingBottom: "8px",
              borderBottom: "1px solid var(--ink, #1A1814)",
              color: "var(--ink, #1A1814)",
            }}
          >
            Linked findings ({data?.linked_findings.length ?? 0})
          </h2>
          {data?.linked_findings.length === 0 && (
            <p style={{ fontFamily: "var(--m, monospace)", fontSize: "10px", color: "var(--muted, #78716A)" }}>None linked.</p>
          )}
          {data?.linked_findings.map((f) => {
            const isLB = f.impact === "load_bearing";
            return (
              <div
                key={f.id}
                style={{
                  borderLeft: isLB ? "3px solid var(--ink, #1A1814)" : "3px solid transparent",
                  paddingLeft: "8px",
                  paddingBottom: "10px",
                  marginBottom: "10px",
                  borderBottom: "1px solid var(--rule, rgba(26,24,20,.10))",
                }}
              >
                <div style={{ display: "flex", gap: "6px", alignItems: "baseline", marginBottom: "3px" }}>
                  <span style={{ fontFamily: "var(--m, monospace)", fontSize: "9px", fontWeight: 700, letterSpacing: ".08em", textTransform: "uppercase" }}>
                    {f.agent_id ?? "?"}
                  </span>
                  {f.hypothesis_label && (
                    <span style={{ fontFamily: "var(--m, monospace)", fontSize: "9px", color: "var(--ink3, #5C564C)", fontWeight: 600 }}>
                      {f.hypothesis_label}
                    </span>
                  )}
                  <span style={{ fontFamily: "var(--m, monospace)", fontSize: "8px", color: "var(--muted, #78716A)" }}>
                    {(f.confidence || "").replace("_CONFIDENCE", "")}
                  </span>
                </div>
                <div style={{ fontSize: "12px", lineHeight: 1.4, fontWeight: isLB ? 600 : 400 }}>{f.claim_text}</div>
              </div>
            );
          })}
        </aside>
      </div>
    </div>
  );
}
