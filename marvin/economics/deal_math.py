"""Pure-Python deal-economics computations for the C10 deal-economics module.

All monetary inputs are in millions; multiples are dimensionless floats.
Functions are defensive about missing inputs: any None or zero divisor
returns None for the dependent value rather than raising. The caller
(API endpoint) decides whether to surface "missing input" in the UI.

Conventions:
  - entry_ev   = entry enterprise value = entry_ebitda * entry_multiple
  - entry_debt = leverage_x * entry_ebitda
  - entry_equity = entry_ev - entry_debt (or user-supplied)
  - exit_ev    = exit_ebitda * exit_multiple
  - exit_equity = exit_ev - residual_debt (we model debt as paid down to
    50% of entry_debt by exit unless caller overrides — a typical PE
    assumption). The model is intentionally simple; sensitivity comes
    from the bull/base/bear scenarios.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


def _none_if_zero(x: float | None) -> float | None:
    if x is None:
        return None
    return x if x != 0 else None


def entry_enterprise_value(
    entry_ebitda: float | None, entry_multiple: float | None
) -> float | None:
    if entry_ebitda is None or entry_multiple is None:
        return None
    return entry_ebitda * entry_multiple


def entry_debt(
    entry_ebitda: float | None, leverage_x: float | None
) -> float | None:
    if entry_ebitda is None or leverage_x is None:
        return None
    return entry_ebitda * leverage_x


def entry_equity_check(
    entry_ev: float | None, debt: float | None, supplied: float | None
) -> float | None:
    """Prefer caller-supplied entry_equity; otherwise derive ev - debt."""
    if supplied is not None:
        return supplied
    if entry_ev is None or debt is None:
        return None
    return entry_ev - debt


def required_exit_equity(
    entry_equity: float | None,
    target_moic: float | None,
) -> float | None:
    if entry_equity is None or target_moic is None:
        return None
    return entry_equity * target_moic


def implied_irr(
    entry_equity: float | None,
    exit_equity: float | None,
    hold_years: int | None,
) -> float | None:
    """IRR for a single in/out cashflow. (exit/entry)^(1/years) - 1."""
    if (
        entry_equity is None
        or exit_equity is None
        or hold_years is None
    ):
        return None
    if entry_equity <= 0 or hold_years <= 0:
        return None
    if exit_equity <= 0:
        return -1.0
    return (exit_equity / entry_equity) ** (1.0 / hold_years) - 1.0


def implied_moic(
    entry_equity: float | None, exit_equity: float | None
) -> float | None:
    if entry_equity is None or exit_equity is None or entry_equity <= 0:
        return None
    return exit_equity / entry_equity


@dataclass
class Scenario:
    name: str
    ebitda_growth: float        # cumulative growth over hold (e.g. 0.5 = +50%)
    exit_multiple: float        # absolute multiple, not delta
    debt_paydown_pct: float     # share of entry debt repaid (0..1)
    exit_ebitda: float | None
    exit_ev: float | None
    exit_equity: float | None
    moic: float | None
    irr: float | None


def scenario(
    name: str,
    ebitda_growth: float,
    exit_multiple: float,
    debt_paydown_pct: float,
    *,
    entry_ebitda: float | None,
    debt: float | None,
    entry_equity: float | None,
    hold_years: int | None,
) -> Scenario:
    if entry_ebitda is None:
        return Scenario(name, ebitda_growth, exit_multiple, debt_paydown_pct,
                        None, None, None, None, None)
    exit_ebitda = entry_ebitda * (1.0 + ebitda_growth)
    exit_ev = exit_ebitda * exit_multiple
    residual_debt = (debt or 0.0) * (1.0 - debt_paydown_pct)
    exit_equity = exit_ev - residual_debt
    moic = implied_moic(entry_equity, exit_equity)
    irr = implied_irr(entry_equity, exit_equity, hold_years)
    return Scenario(name, ebitda_growth, exit_multiple, debt_paydown_pct,
                    exit_ebitda, exit_ev, exit_equity, moic, irr)


def compute_deal_math(terms: dict[str, Any]) -> dict[str, Any]:
    """Compute deal-math view from a DealTerms dict.

    Returns:
      {
        "entry": {ev, debt, equity},
        "required_exit_equity": float | None,   # to hit target_moic
        "scenarios": {bear, base, bull},        # each with ebitda/ev/equity/moic/irr
        "missing_inputs": [field, ...],
      }
    """
    needed = ("entry_ebitda", "entry_multiple", "leverage_x", "hold_years",
              "target_moic", "sector_multiple_low", "sector_multiple_high")
    missing = [k for k in needed if terms.get(k) is None]

    eb = terms.get("entry_ebitda")
    em = terms.get("entry_multiple")
    lev = terms.get("leverage_x")
    hold = terms.get("hold_years")
    target_moic = terms.get("target_moic")
    sec_lo = terms.get("sector_multiple_low")
    sec_hi = terms.get("sector_multiple_high")

    ev = entry_enterprise_value(eb, em)
    debt = entry_debt(eb, lev)
    equity = entry_equity_check(ev, debt, terms.get("entry_equity"))
    required_exit_eq = required_exit_equity(equity, target_moic)

    base_mult = em if em is not None else None
    bear_mult = sec_lo if sec_lo is not None else (em * 0.85 if em else None)
    bull_mult = sec_hi if sec_hi is not None else (em * 1.15 if em else None)

    scenarios: dict[str, dict[str, Any]] = {}
    for name, growth, mult, paydown in (
        ("bear", 0.10, bear_mult, 0.30),
        ("base", 0.40, base_mult, 0.50),
        ("bull", 0.80, bull_mult, 0.70),
    ):
        if mult is None:
            scenarios[name] = {
                "ebitda_growth": growth, "exit_multiple": None,
                "debt_paydown_pct": paydown,
                "exit_ebitda": None, "exit_ev": None, "exit_equity": None,
                "moic": None, "irr": None,
            }
            continue
        s = scenario(name, growth, mult, paydown,
                     entry_ebitda=eb, debt=debt,
                     entry_equity=equity, hold_years=hold)
        scenarios[name] = {
            "ebitda_growth": s.ebitda_growth,
            "exit_multiple": s.exit_multiple,
            "debt_paydown_pct": s.debt_paydown_pct,
            "exit_ebitda": s.exit_ebitda,
            "exit_ev": s.exit_ev,
            "exit_equity": s.exit_equity,
            "moic": s.moic,
            "irr": s.irr,
        }
    return {
        "entry": {"ev": ev, "debt": debt, "equity": equity},
        "required_exit_equity": required_exit_eq,
        "scenarios": scenarios,
        "missing_inputs": missing,
    }
