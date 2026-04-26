from __future__ import annotations

from collections import Counter
from typing import Any

from marvin.mission.store import MissionStore
from marvin.tools.common import InjectedStateArg, get_store, normalize_hypothesis_id, require_mission_id
from marvin.tools.mission_tools import add_finding_to_mission

_STORE_FACTORY = MissionStore


def attack_hypothesis(
    hypothesis_id: str,
    angle: str,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Mount a directional attack on a specific hypothesis and record a finding.

    Use as the core adversarial probe: pick a hypothesis and an attack angle
    (e.g. 'demand', 'supply', 'regulatory') and persist the resulting
    counter-claim. Required: hypothesis_id and angle. Requires a mission_id
    in state.
    """
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    hypothesis_id = normalize_hypothesis_id(hypothesis_id)
    allowed = {h.id: h for h in store.list_hypotheses(mission_id)}
    if hypothesis_id not in allowed:
        raise ValueError(
            f"hypothesis_id {hypothesis_id!r} is not a valid hypothesis for "
            f"mission {mission_id}. Allowed: {sorted(allowed)}. "
            "Pass one of these IDs verbatim."
        )
    hypothesis = allowed[hypothesis_id]
    claim = f"{angle.title()} attack on hypothesis: {hypothesis.text}"
    finding = add_finding_to_mission(
        claim_text=claim,
        confidence="REASONED",
        agent_id="adversus",
        hypothesis_id=hypothesis_id,
        workstream_id="W4",
        state=state,
    )
    return {"hypothesis_id": hypothesis_id, "angle": angle, "finding_id": finding["finding_id"]}


def generate_stress_scenarios(
    mission_id: str | None = None,
    state: InjectedStateArg = None,
) -> dict[str, Any]:
    """Generate downside stress scenarios for the mission's investment thesis.

    Use to bound the downside before recommending a verdict. Optional
    mission_id; otherwise resolved from state. Returns a list of named
    scenarios.
    """
    resolved_mission_id = mission_id or require_mission_id(state)
    return {
        "mission_id": resolved_mission_id,
        "scenarios": [
            "Consumer demand softens for 12 months",
            "Category expansion fails to convert",
            "Competitive subsidy pressure compresses take rate",
        ],
    }


def identify_weakest_link(state: InjectedStateArg = None) -> dict[str, Any]:
    """Identify the hypothesis with the least supporting evidence so far.

    Use to prioritize where additional research is needed before the verdict.
    No inputs beyond state; requires a mission_id in state. Returns the
    hypothesis_id with the lowest finding count and that count.
    """
    mission_id = require_mission_id(state)
    store = get_store(_STORE_FACTORY)
    findings = store.list_findings(mission_id)
    hypotheses = store.list_hypotheses(mission_id)
    counts = Counter(finding.hypothesis_id for finding in findings if finding.hypothesis_id)
    if not hypotheses:
        return {"mission_id": mission_id, "weakest_link": None}
    weakest = min(hypotheses, key=lambda hypothesis: counts.get(hypothesis.id, 0))
    return {"mission_id": mission_id, "weakest_link": weakest.id, "evidence_count": counts.get(weakest.id, 0)}


def run_ansoff(company: str, state: InjectedStateArg = None) -> dict[str, Any]:
    """Run an Ansoff matrix (penetration / development / diversification) for a company.

    Use to map plausible growth vectors when stress-testing a thesis.
    Required: company name. Requires a mission_id in state.
    """
    require_mission_id(state)
    return {
        "company": company,
        "matrix": {
            "market_penetration": "Increase repeat engagement in core categories",
            "market_development": "Expand into adjacent European geographies",
            "product_development": "Add logistics and authentication services",
            "diversification": "Launch adjacent resale verticals",
        },
    }
