"use client";

import React, { useEffect, useRef } from "react";
import type { MissionChatMessage } from "@/lib/missions/types";
import { humanizeText } from "@/lib/missions/humanize";
import { Mono, PulsingM } from "./Primitives";

// ─── Prop types ───────────────────────────────────────────────────────────────

export interface RightRailProps {
  messages: MissionChatMessage[];
  isTyping: boolean;
  currentNarration?: string | null;
  chatDraft: string;
  onChatDraftChange: (value: string) => void;
  onSendMessage: (value: string) => void;
  onOpenDeliverable?: (deliverableId: string) => void;
  onGateApprove?: (gateId: string) => void;
  onGateReject?: (gateId: string) => void;
  onGateReview?: (gateId: string) => void;
}

// ─── RightRail ────────────────────────────────────────────────────────────────

export function RightRail({
  messages,
  isTyping,
  currentNarration,
  chatDraft,
  onChatDraftChange,
  onSendMessage,
  onOpenDeliverable,
  onGateApprove,
  onGateReject,
  onGateReview,
}: RightRailProps): React.ReactElement {
  const chatRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Wave 1 transparency fix: scroll-to-bottom must track currentNarration
  // too, because the typing bubble grows when narration arrives — without
  // this dep, the latest narration line is hidden under the composer. Use
  // scrollHeight (not a magic 99999) for safety on long histories, and
  // schedule via rAF so layout has finished before we measure.
  useEffect(() => {
    const el = chatRef.current;
    if (!el) return;
    const id = requestAnimationFrame(() => {
      el.scrollTop = el.scrollHeight;
    });
    return () => cancelAnimationFrame(id);
  }, [messages, isTyping, currentNarration]);

  useEffect(() => {
    const el = inputRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = Math.min(el.scrollHeight, 120) + "px";
  }, [chatDraft]);

  function send(): void {
    const trimmed = chatDraft.trim();
    if (trimmed) onSendMessage(trimmed);
  }

  return (
    <aside style={{ borderLeft: "1px solid var(--ruleh)", display: "flex", flexDirection: "column", overflow: "hidden", flexShrink: 0 }}>

      {/* Header */}
      <div style={{ padding: 0, flexShrink: 0 }}>
        <div style={{
          padding: "14px 20px",
          background: "var(--ink)",
          color: "var(--paper)",
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{
              width: 24, height: 24, borderRadius: 6,
              background: "rgba(244,240,234,.12)",
              display: "grid", placeItems: "center",
              fontFamily: "var(--d)", fontSize: 11, fontWeight: 700,
            }}>
              M
            </div>
            <div>
              <div style={{ fontFamily: "var(--d)", fontSize: 13, fontWeight: 700, letterSpacing: ".02em" }}>MARVIN</div>
              <Mono size={9} color="rgba(244,240,234,.35)" spacing=".06em">Mission orchestrator</Mono>
            </div>
          </div>

          {/* Pulsing M + Connected label — shared primitive for consistency */}
          <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
            <PulsingM color="#4ade80" size={10} />
            <Mono size={9} weight={600} color="#4ade80" spacing=".08em">Connected</Mono>
          </div>
        </div>
      </div>

      {/* Messages */}
      <div
        ref={chatRef}
        style={{ flex: 1, overflow: "auto", padding: "16px 16px", display: "flex", flexDirection: "column", gap: 10, background: "var(--bone)" }}
      >
        {[...messages].sort((a, b) => {
          // Stable sort by seq when both messages have it; fall back to
          // array index (i.e. insertion order) otherwise. This ensures
          // deliverable bubbles always appear before their companion
          // narrations even if React batches the state updates in a
          // different order than SSE arrival (Issue C fix).
          if (a.seq != null && b.seq != null) return a.seq - b.seq;
          if (a.seq != null) return -1;
          if (b.seq != null) return 1;
          return 0;
        }).map(m => {
          const isUser = m.from === "u";
          return (
            <div key={m.id} style={{ display: "flex", flexDirection: isUser ? "row-reverse" : "row", gap: 8, alignItems: "flex-end" }}>
              {!isUser && (
                <div style={{
                  width: 20, height: 20, borderRadius: 5,
                  background: "var(--ink)",
                  display: "grid", placeItems: "center",
                  fontFamily: "var(--d)", fontSize: 8, fontWeight: 700, color: "var(--paper)", flexShrink: 0,
                }}>
                  M
                </div>
              )}
              {/* P7: body text uses system font stack, not display Geist */}
              <div style={{
                maxWidth: "82%", padding: "10px 14px",
                fontSize: 13, lineHeight: 1.55, letterSpacing: "normal",
                fontFamily: 'system-ui, -apple-system, "Segoe UI", Inter, sans-serif',
                color: isUser
                  ? "var(--paper)"
                  : m.deliverableId
                    ? "#4ade80"
                    : "var(--ink2)",
                background: isUser
                  ? "var(--ink)"
                  : m.deliverableId
                    ? "#0a0a0a"
                    : "white",
                borderRadius: isUser ? "12px 12px 3px 12px" : "12px 12px 12px 3px",
                boxShadow: isUser
                  ? "none"
                  : m.deliverableId
                    ? "0 1px 3px rgba(0,0,0,.18)"
                    : "0 1px 3px rgba(26,24,20,.06)",
                display: "flex", flexDirection: "column", gap: 8,
              }}>
                <span style={{ whiteSpace: "pre-wrap" }}>{isUser ? m.text : humanizeText(m.text)}</span>
                {!isUser && m.deliverableId && onOpenDeliverable && (
                  <button
                    type="button"
                    onClick={() => onOpenDeliverable(m.deliverableId!)}
                    style={{
                      alignSelf: "flex-start",
                      fontFamily: "var(--m)", fontSize: 9, fontWeight: 700,
                      letterSpacing: ".1em", textTransform: "uppercase",
                      color: "#4ade80", background: "transparent",
                      border: "1px solid rgba(74,222,128,.45)",
                      padding: "5px 12px", borderRadius: 4, cursor: "pointer",
                      transition: "background .15s",
                    }}
                    onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(74,222,128,.12)"; }}
                    onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                  >
                    Open {m.deliverableLabel ?? "deliverable"} →
                  </button>
                )}
                {!isUser && m.gateId && m.gateAction === "pending" && onGateApprove && onGateReject && (
                  <div style={{ display: "flex", gap: 6, marginTop: 6, flexWrap: "wrap" }}>
                    {onGateReview && (
                      <button
                        onClick={() => onGateReview(m.gateId!)}
                        style={{
                          fontSize: 9, fontFamily: "var(--m)", letterSpacing: ".08em",
                          textTransform: "uppercase", fontWeight: 700,
                          padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                          background: "var(--ink)",
                          border: "1px solid var(--ink)",
                          color: "var(--paper)",
                        }}
                        onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.opacity = "0.85"; }}
                        onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.opacity = "1"; }}
                      >Review claims →</button>
                    )}
                    <button
                      onClick={() => onGateApprove(m.gateId!)}
                      style={{
                        fontSize: 9, fontFamily: "var(--m)", letterSpacing: ".08em",
                        textTransform: "uppercase", fontWeight: 700,
                        padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                        background: "transparent",
                        border: "1px solid rgba(45,110,78,.30)",
                        color: "var(--green)",
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(45,110,78,.08)"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                    >Approve →</button>
                    <button
                      onClick={() => onGateReject(m.gateId!)}
                      style={{
                        fontSize: 9, fontFamily: "var(--m)", letterSpacing: ".08em",
                        textTransform: "uppercase", fontWeight: 700,
                        padding: "4px 10px", borderRadius: 4, cursor: "pointer",
                        background: "transparent",
                        border: "1px solid rgba(160,40,40,.25)",
                        color: "rgba(160,40,40,.8)",
                      }}
                      onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.background = "rgba(160,40,40,.06)"; }}
                      onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; }}
                    >Reject</button>
                  </div>
                )}
              </div>
            </div>
          );
        })}

        {/* Typing indicator — square dots */}
        {isTyping && (
          <div style={{ display: "flex", gap: 8, alignItems: "flex-end" }}>
            <div style={{
              width: 20, height: 20, borderRadius: 5,
              background: "var(--ink)",
              display: "grid", placeItems: "center",
              fontFamily: "var(--d)", fontSize: 8, fontWeight: 700, color: "var(--paper)", flexShrink: 0,
            }}>
              M
            </div>
            <div style={{ maxWidth: "82%", padding: "10px 14px", background: "white", borderRadius: "12px 12px 12px 3px", boxShadow: "0 1px 3px rgba(26,24,20,.06)" }}>
              {currentNarration && (
                <div style={{ fontSize: 12, lineHeight: 1.6, color: "var(--ink3)", marginBottom: 8 }}>
                  {humanizeText(currentNarration)}
                </div>
              )}
              <div style={{ display: "flex", gap: 4 }}>
                {[0, 1, 2].map(i => (
                  <div
                    key={i}
                    style={{
                      width: 5,
                      height: 5,
                      borderRadius: 1,
                      background: "var(--muted)",
                      animation: `blink 1.1s ${i * 0.25}s ease-in-out infinite`,
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Input */}
      <div style={{ background: "white", borderTop: "1px solid var(--ruleh)", flexShrink: 0 }}>
        <div style={{ padding: "12px 16px 8px" }}>
          <textarea
            ref={inputRef}
            value={chatDraft}
            placeholder="Redirect the mission, ask a question..."
            style={{
              fontFamily: "var(--g)", fontSize: 13, color: "var(--ink)",
              background: "transparent", border: "none", outline: "none",
              resize: "none", lineHeight: 1.6,
              width: "100%", minHeight: 44, maxHeight: 120, overflowY: "auto",
            }}
            onChange={e => onChatDraftChange(e.target.value)}
            onKeyDown={e => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
          />
        </div>
        <div style={{ padding: "6px 16px 12px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <Mono size={9} color="var(--muted)">⌘ ↵ to send</Mono>
          <button
            onClick={send}
            style={{
              fontFamily: "var(--m)", fontSize: 9, fontWeight: 700, letterSpacing: ".1em", textTransform: "uppercase",
              padding: "8px 18px", background: "var(--ink)", color: "var(--paper)",
              border: "none", cursor: "pointer", borderRadius: 5,
              transition: "opacity .15s",
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.opacity = ".85"; }}
            onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.opacity = "1"; }}
          >
            Send →
          </button>
        </div>
      </div>
    </aside>
  );
}
