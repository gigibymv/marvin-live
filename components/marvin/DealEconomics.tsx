"use client";

import React, { useEffect, useState } from "react";

type DealTerms = {
  entry_revenue: number | null;
  entry_ebitda: number | null;
  entry_multiple: number | null;
  entry_equity: number | null;
  leverage_x: number | null;
  hold_years: number | null;
  target_irr: number | null;
  target_moic: number | null;
  sector_multiple_low: number | null;
  sector_multiple_high: number | null;
  notes: string | null;
};

type Scenario = {
  ebitda_growth: number;
  exit_multiple: number | null;
  debt_paydown_pct: number;
  exit_ebitda: number | null;
  exit_ev: number | null;
  exit_equity: number | null;
  moic: number | null;
  irr: number | null;
};

type DealMath = {
  entry: { ev: number | null; debt: number | null; equity: number | null };
  required_exit_equity: number | null;
  scenarios: { bear: Scenario; base: Scenario; bull: Scenario };
  missing_inputs: string[];
};

const EMPTY_TERMS: DealTerms = {
  entry_revenue: null,
  entry_ebitda: null,
  entry_multiple: null,
  entry_equity: null,
  leverage_x: null,
  hold_years: null,
  target_irr: null,
  target_moic: null,
  sector_multiple_low: null,
  sector_multiple_high: null,
  notes: null,
};

const FIELDS: Array<{ key: keyof DealTerms; label: string; suffix?: string }> = [
  { key: "entry_revenue", label: "Entry revenue", suffix: "$M" },
  { key: "entry_ebitda", label: "Entry EBITDA", suffix: "$M" },
  { key: "entry_multiple", label: "Entry multiple", suffix: "x" },
  { key: "leverage_x", label: "Leverage", suffix: "x EBITDA" },
  { key: "hold_years", label: "Hold period", suffix: "years" },
  { key: "target_moic", label: "Target MOIC", suffix: "x" },
  { key: "target_irr", label: "Target IRR", suffix: "(0–1)" },
  { key: "sector_multiple_low", label: "Sector multiple low", suffix: "x" },
  { key: "sector_multiple_high", label: "Sector multiple high", suffix: "x" },
];

function fmtMoney(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toFixed(1)}M`;
}

function fmtMult(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${n.toFixed(2)}x`;
}

function fmtPct(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export default function DealEconomics({ missionId }: { missionId: string }) {
  const [terms, setTerms] = useState<DealTerms>(EMPTY_TERMS);
  const [math, setMath] = useState<DealMath | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const r = await fetch(`/api/v1/missions/${missionId}/deal-math`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const body = await r.json();
      if (body.terms) setTerms({ ...EMPTY_TERMS, ...body.terms });
      setMath(body.math);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "load failed");
    }
  }

  useEffect(() => {
    void load();
  }, [missionId]);

  async function save() {
    setSaving(true);
    try {
      const r = await fetch(`/api/v1/missions/${missionId}/deal-terms`, {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(terms),
      });
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "save failed");
    } finally {
      setSaving(false);
    }
  }

  function updateField(key: keyof DealTerms, raw: string) {
    const next = raw === "" ? null : Number(raw);
    setTerms((prev) => ({ ...prev, [key]: Number.isNaN(next as number) ? null : next }));
  }

  return (
    <div style={{ padding: 16, fontFamily: "system-ui, sans-serif" }}>
      <h2 style={{ margin: "0 0 12px" }}>Deal Economics</h2>

      {error && (
        <div style={{ color: "#b00", marginBottom: 8 }}>error: {error}</div>
      )}

      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
        <section>
          <h3 style={{ marginTop: 0 }}>Inputs</h3>
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
            {FIELDS.map((f) => (
              <label key={f.key} style={{ display: "flex", flexDirection: "column" }}>
                <span style={{ fontSize: 12, color: "#555" }}>
                  {f.label} {f.suffix ? <em>({f.suffix})</em> : null}
                </span>
                <input
                  type="number"
                  step="any"
                  value={terms[f.key] === null ? "" : String(terms[f.key])}
                  onChange={(e) => updateField(f.key, e.target.value)}
                  style={{ padding: 6, fontSize: 14 }}
                />
              </label>
            ))}
          </div>
          <button
            onClick={save}
            disabled={saving}
            style={{
              marginTop: 12, padding: "8px 14px", fontSize: 14,
              cursor: saving ? "wait" : "pointer",
            }}
          >
            {saving ? "Saving…" : "Save deal terms"}
          </button>
        </section>

        <section>
          <h3 style={{ marginTop: 0 }}>Deal math</h3>
          {math && (
            <>
              <div style={{ marginBottom: 12 }}>
                <strong>Entry:</strong> EV {fmtMoney(math.entry.ev)} ·
                Debt {fmtMoney(math.entry.debt)} ·
                Equity {fmtMoney(math.entry.equity)}
                <br />
                <strong>Required exit equity</strong> (to hit target MOIC):{" "}
                {fmtMoney(math.required_exit_equity)}
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 14 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid #ccc", textAlign: "left" }}>
                    <th>Scenario</th>
                    <th>EBITDA growth</th>
                    <th>Exit multiple</th>
                    <th>Exit EV</th>
                    <th>Exit equity</th>
                    <th>MOIC</th>
                    <th>IRR</th>
                  </tr>
                </thead>
                <tbody>
                  {(["bear", "base", "bull"] as const).map((name) => {
                    const s = math.scenarios[name];
                    return (
                      <tr key={name} style={{ borderBottom: "1px solid #eee" }}>
                        <td style={{ textTransform: "capitalize", padding: "6px 0" }}>
                          {name}
                        </td>
                        <td>{fmtPct(s.ebitda_growth)}</td>
                        <td>{fmtMult(s.exit_multiple)}</td>
                        <td>{fmtMoney(s.exit_ev)}</td>
                        <td>{fmtMoney(s.exit_equity)}</td>
                        <td>{fmtMult(s.moic)}</td>
                        <td>{fmtPct(s.irr)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {math.missing_inputs.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12, color: "#888" }}>
                  Missing: {math.missing_inputs.join(", ")}
                </div>
              )}
            </>
          )}
        </section>
      </div>
    </div>
  );
}
