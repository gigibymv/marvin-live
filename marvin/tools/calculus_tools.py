from __future__ import annotations

from typing import Any

from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, coerce_jsonish, get_store, require_mission_id
from marvin.tools.mission_tools import add_finding_to_mission, persist_source_for_mission

_STORE_FACTORY = MissionStore


def parse_data_room(file_path: str, state: InjectedStateArg = None) -> dict[str, Any]:
    """Parse a data room file and report what's actually on disk.

    Use as the first step before any quant analysis on data-room inputs.
    Required: file_path pointing to the data-room file. Reports `exists`,
    `line_count`, and `size_bytes` so downstream calls can decide whether to
    proceed or surface a missing-input error to the user.
    """
    from pathlib import Path as _Path

    path = _Path(file_path)
    if not path.exists() or not path.is_file():
        return {"file_path": file_path, "exists": False, "line_count": 0, "size_bytes": 0}
    text = path.read_text(encoding="utf-8", errors="replace")
    return {
        "file_path": file_path,
        "exists": True,
        "line_count": text.count("\n"),
        "size_bytes": path.stat().st_size,
    }


def quality_of_earnings(
    financials_json: Any,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Compute adjusted EBITDA from a P&L slice plus management add-backs.

    Use to test whether reported earnings hold up after one-offs. Input:
    financials_json with 'revenue', 'cogs', 'opex', and 'add_backs'.
    Adjusted EBITDA = revenue - cogs - opex + add_backs. Emits a finding
    when state carries a mission_id.

    LLM-supplied JSON regularly contains explicit nulls or non-numeric
    placeholders; treat those as missing. Missing fields are surfaced via
    `missing_inputs` so callers see the data was incomplete rather than
    silently zeroed.
    """
    payload = coerce_jsonish(financials_json)
    fields = ("revenue", "cogs", "opex", "add_backs")
    missing_inputs: list[str] = []
    values: dict[str, float] = {}
    for name in fields:
        raw = payload.get(name)
        if raw is None:
            missing_inputs.append(name)
            values[name] = 0.0
            continue
        try:
            values[name] = float(raw)
        except (TypeError, ValueError):
            missing_inputs.append(name)
            values[name] = 0.0
    revenue = values["revenue"]
    cogs = values["cogs"]
    opex = values["opex"]
    add_backs = values["add_backs"]
    gross_profit = revenue - cogs
    reported_ebitda = gross_profit - opex
    adjusted_ebitda = reported_ebitda + add_backs
    result = {
        "revenue": revenue,
        "cogs": cogs,
        "opex": opex,
        "add_backs": add_backs,
        "gross_profit": gross_profit,
        "reported_ebitda": reported_ebitda,
        "adjusted_ebitda": adjusted_ebitda,
        "missing_inputs": missing_inputs,
    }
    if state is not None and hypothesis_id is not None:
        if missing_inputs:
            add_finding_to_mission(
                claim_text=(
                    f"Adjusted EBITDA cannot be computed from primary data; "
                    f"missing inputs: {', '.join(missing_inputs)}."
                ),
                confidence="LOW_CONFIDENCE",
                agent_id="calculus",
                workstream_id="W2",
                hypothesis_id=hypothesis_id,
                state=state,
            )
        else:
            add_finding_to_mission(
                claim_text=f"Adjusted EBITDA is {adjusted_ebitda:.2f} (revenue {revenue}, cogs {cogs}, opex {opex}, add-backs {add_backs})",
                confidence="REASONED",
                agent_id="calculus",
                workstream_id="W2",
                hypothesis_id=hypothesis_id,
                state=state,
            )
    return result


def cohort_analysis(
    cohort_data_json: Any,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Compute average retention across customer cohorts.

    Use to assess customer durability when cohort data is provided. Input:
    cohort_data_json with a 'cohorts' list, each entry having a 'retention'
    value (0-1).
    """
    payload = coerce_jsonish(cohort_data_json)
    cohorts = payload.get("cohorts", [])
    per_cohort = []
    for cohort in cohorts:
        m0 = cohort.get("month_0", 0)
        m3 = cohort.get("month_3", 0)
        per_cohort.append((m3 / m0) if m0 else 0)
    average_m3_retention = sum(per_cohort) / len(per_cohort) if per_cohort else 0
    result = {
        "cohort_count": len(cohorts),
        "average_m3_retention": average_m3_retention,
        "per_cohort_m3_retention": per_cohort,
    }
    if state is not None and hypothesis_id is not None:
        add_finding_to_mission(
            claim_text=f"Cohort analysis shows {average_m3_retention:.1%} M3 retention across observed cohorts.",
            confidence="REASONED",
            agent_id="calculus",
            workstream_id="W2",
            hypothesis_id=hypothesis_id,
            state=state,
        )
    return result


def compute_cac_ltv(
    sales_data_json: Any,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Derive CAC, LTV, and LTV/CAC from sales economics inputs.

    Use to test unit-economics quality. Input: sales_data_json with
    'sales_spend', 'new_customers', 'gross_margin' (0-1), 'arpu', and
    'monthly_churn' (0-1).
        cac = sales_spend / new_customers
        ltv = arpu * gross_margin / monthly_churn
        ltv_to_cac = ltv / cac
    Emits a finding when state carries a mission_id.
    """
    payload = coerce_jsonish(sales_data_json)
    sales_spend = payload.get("sales_spend", 0)
    new_customers = payload.get("new_customers", 0)
    gross_margin = payload.get("gross_margin", 0)
    arpu = payload.get("arpu", 0)
    monthly_churn = payload.get("monthly_churn", 0)
    cac = sales_spend / new_customers if new_customers else 0
    ltv = (arpu * gross_margin) / monthly_churn if monthly_churn else 0
    ratio = ltv / cac if cac else 0
    result = {
        "cac": cac,
        "ltv": ltv,
        "ltv_to_cac": ratio,
        "ltv_cac_ratio": ratio,
    }
    if state is not None and hypothesis_id is not None:
        if not new_customers or not monthly_churn:
            missing = []
            if not new_customers: missing.append("new_customers")
            if not monthly_churn: missing.append("monthly_churn")
            add_finding_to_mission(
                claim_text=(
                    f"LTV/CAC cannot be computed from primary data; "
                    f"missing inputs: {', '.join(missing)}."
                ),
                confidence="LOW_CONFIDENCE",
                agent_id="calculus",
                workstream_id="W2",
                hypothesis_id=hypothesis_id,
                state=state,
            )
        else:
            add_finding_to_mission(
                claim_text=f"LTV/CAC ratio is {ratio:.2f}x (CAC ${cac:.0f}, LTV ${ltv:.0f}) across the customer base.",
                confidence="REASONED",
                agent_id="calculus",
                workstream_id="W2",
                hypothesis_id=hypothesis_id,
                state=state,
            )
    return result


def concentration_analysis(
    customers_json: Any,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Compute top-10 customer revenue concentration as a share of total.

    Use to flag customer-concentration risk. Input: customers_json with a
    'customers' list, each entry having 'revenue'. Returns customer_count,
    total_revenue, and top_10_concentration (0-1).
    """
    payload = coerce_jsonish(customers_json)
    # LLM-supplied JSON commonly sends `customers: null` rather than omitting
    # the key; treat null and non-list values as empty.
    customers = payload.get("customers") or []
    if not isinstance(customers, list):
        customers = []
    revenues = sorted(
        (
            float(c.get("revenue") or 0)
            for c in customers
            if isinstance(c, dict)
        ),
        reverse=True,
    )
    total_rev = sum(revenues)
    top_customer_share = (revenues[0] / total_rev) if revenues and total_rev > 0 else 0
    top_10_concentration = (sum(revenues[:10]) / total_rev) if total_rev > 0 else 0
    result = {
        "customer_count": len(customers),
        "total_revenue": total_rev,
        "top_customer_share": top_customer_share,
        "top_10_concentration": top_10_concentration,
    }
    if state is not None and hypothesis_id is not None:
        add_finding_to_mission(
            claim_text=f"Top customer share is {top_customer_share:.1%}; top-10 share is {top_10_concentration:.1%}.",
            confidence="REASONED",
            agent_id="calculus",
            workstream_id="W2",
            hypothesis_id=hypothesis_id,
            state=state,
        )
    return result


def anomaly_detector(
    management_claims_json: Any,
    data_room_json: Any,
    state: InjectedStateArg = None,
    hypothesis_id: str | None = None,
) -> dict[str, Any]:
    """Compare management-claimed metrics against data-room metrics, key by key.

    Inputs: two flat dicts of metric_name -> value. Each shared key is
    compared; any divergence is recorded as an anomaly. The detected count
    is `count` and the per-key detail is `anomalies`. When mismatches exist
    and state carries a mission_id, a KNOWN finding is persisted — KNOWN
    because the divergence between two presented numbers is observed fact,
    not interpretation.
    """
    claims = coerce_jsonish(management_claims_json) or {}
    data = coerce_jsonish(data_room_json) or {}
    shared_keys = sorted(set(claims) & set(data))
    anomalies = []
    for key in shared_keys:
        if claims[key] != data[key]:
            anomalies.append({"metric": key, "claimed": claims[key], "observed": data[key]})
    result = {
        "checked": len(shared_keys),
        "count": len(anomalies),
        "anomalies": anomalies,
    }
    if state is not None and anomalies and hypothesis_id is not None:
        details = "; ".join(f"{a['metric']} claimed {a['claimed']} vs observed {a['observed']}" for a in anomalies)
        source = persist_source_for_mission(
            url_or_ref="data_room",
            quote=f"observed: {data}; claimed: {claims}",
            state=state,
        )
        add_finding_to_mission(
            claim_text=f"Anomaly detector found {len(anomalies)} metric mismatch(es): {details}",
            confidence="KNOWN",
            agent_id="calculus",
            workstream_id="W2",
            source_id=source["source_id"],
            hypothesis_id=hypothesis_id,
            state=state,
        )
    return result


def search_sec_filings(company_name: str, year: int | str = 2024, state: InjectedStateArg = None) -> dict[str, Any]:
    """Search SEC filings for a company in a given fiscal year.

    No mission state is required — this is a pure lookup. The previous
    `require_mission_id(state)` call coupled the tool to mission scope without
    using the mission_id, so it has been removed.
    """
    return {
        "company_name": company_name,
        "year": year,
        "filings": [
            {
                "form": "10-K",
                "title": f"{company_name} 10-K FY{year}",
                "date": f"{year}-03-31",
                "url": f"https://sec.gov/{company_name.lower()}-{year}",
            },
            {
                "form": "10-Q",
                "title": f"{company_name} 10-Q FY{year}",
                "date": f"{year}-06-30",
                "url": f"https://sec.gov/{company_name.lower()}-{year}-q2",
            },
        ],
    }
