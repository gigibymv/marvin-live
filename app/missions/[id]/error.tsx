"use client";

import Link from "next/link";
import { useEffect } from "react";

function isChunkLoadError(error: Error): boolean {
  return (
    error.name === "ChunkLoadError" ||
    /loading chunk/i.test(error.message) ||
    /loading css chunk/i.test(error.message) ||
    /failed to fetch dynamically imported module/i.test(error.message)
  );
}

export default function MissionError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Mission page error:", error);
    if (isChunkLoadError(error)) {
      window.location.reload();
    }
  }, [error]);

  return (
    <div
      style={{
        minHeight: "100vh",
        display: "grid",
        placeItems: "center",
        background: "#f4f0ea",
        padding: "24px",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <div style={{ maxWidth: "420px", textAlign: "center" }}>
        <h1 style={{ margin: "0 0 12px", fontSize: "28px" }}>Something went wrong</h1>
        <p style={{ margin: "0 0 8px", lineHeight: 1.6, color: "#666" }}>
          The mission page encountered an error. This may be a temporary issue.
        </p>
        {error?.message && (
          <p style={{ margin: "0 0 24px", fontSize: "12px", color: "#999", fontFamily: "monospace", wordBreak: "break-word" }}>
            {error.message}
          </p>
        )}
        <div style={{ display: "flex", gap: "12px", justifyContent: "center" }}>
          <button
            onClick={reset}
            style={{
              padding: "10px 20px",
              background: "#1a1814",
              color: "#fff",
              border: "none",
              borderRadius: "6px",
              cursor: "pointer",
              fontSize: "14px",
            }}
          >
            Try again
          </button>
          <Link
            href="/missions"
            style={{
              padding: "10px 20px",
              background: "transparent",
              color: "#1a1814",
              border: "1px solid rgba(26,24,20,.2)",
              borderRadius: "6px",
              fontSize: "14px",
              textDecoration: "none",
            }}
          >
            Back to missions
          </Link>
        </div>
      </div>
    </div>
  );
}
