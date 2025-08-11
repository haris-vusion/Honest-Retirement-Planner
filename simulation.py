from __future__ import annotations

import numpy as np
from dataclasses import dataclass
from taxes import SYSTEMS, indexed as index_tax, gross_for_net
from typing import Tuple

@dataclass
class SimConfig:
    # Timeline
    current_age: int
    retire_age: int
    plan_end_age: int

    # Savings & portfolio
    current_investable: float
    monthly_contrib: float
    contrib_growth_nominal_pct: float  # %/yr
    exp_real_return: float             # annual μ (real)
    volatility: float                  # annual σ
    fees_annual: float                 # proportion
    cpi: float                         # annual CPI

    # Dynamic spending target (today's money), per *month* across full timeline
    # Length = months_total + 1 (index 0..months_total). Pre-retirement entries should be 0.
    target_monthly_real_by_month: np.ndarray

    # Drawdown policy
    withdrawal_rule: str              # "3% real" / "3.5% real" / "4% real"
    legacy_mode: str                  # "Spend to zero" | "Preserve capital (real)"
    spending_policy: str              # "Meet target" | "Rule only" | "Lower of rule & target"

    # Tax
    country: str

    # Monte Carlo
    num_paths: int
    seed: int | None

    # Success definition
    success_cover_pct: float          # e.g., 0.90 means meet target ≥90% of retirement months

def _monthly_params(mu_a, sigma_a):
    return mu_a/12.0, sigma_a/np.sqrt(12.0)

def run_monte_carlo(cfg: SimConfig) -> Tuple[dict, dict]:
    months_total = int((cfg.plan_end_age - cfg.current_age) * 12)
    retire_m     = int((cfg.retire_age    - cfg.current_age) * 12)
    mu_m, sig_m  = _monthly_params(cfg.exp_real_return, cfg.volatility)
    fees_m       = (1 - cfg.fees_annual) ** (1/12.0)
    cpi_y        = cfg.cpi
    cpi_m        = (1 + cfg.cpi) ** (1/12.0)

    rng = np.random.default_rng(cfg.seed)
    # Pre-allocate (paths, time)
    wealth = np.empty((cfg.num_paths, months_total+1), dtype=np.float64)
    net_wd = np.zeros((cfg.num_paths, months_total+1), dtype=np.float64)

    # Rule percent
    rule_map = {"3% real": 0.03, "3.5% real": 0.035, "4% real": 0.04}
    rule_pct = rule_map.get(cfg.withdrawal_rule, 0.03)

    # Draw all monthly real returns for all paths up front
    draws = rng.normal(mu_m, sig_m, size=(cfg.num_paths, months_total))

    def tax_factor_for_month(m):
        return (1 + cpi_y) ** (m // 12)

    for i in range(cfg.num_paths):
        w = cfg.current_investable
        contrib = cfg.monthly_contrib
        wealth[i, 0] = w
        initial_real_principal = cfg.current_investable

        for m in range(1, months_total+1):
            # Contributions (convert nominal contrib to real by dividing CPI growth)
            if m-1 < retire_m:
                contrib *= (1 + cfg.contrib_growth_nominal_pct/100.0) ** (1/12.0)
                real_contrib = contrib / (cpi_m ** m)
                w += real_contrib

            # Real return + fees
            w = max(0.0, w * (1 + draws[i, m-1]) * fees_m)

            # Withdrawals after retirement start
            if m-1 >= retire_m:
                # Target NET income (real) for this month from the precomputed path
                target_net_monthly_real = float(cfg.target_monthly_real_by_month[m])

                # Rule-only income (before considering the basket)
                rule_monthly_real = (cfg.current_investable * rule_pct) / 12.0

                # Decide desired NET payment (real)
                if cfg.spending_policy == "Meet target":
                    desired_net_real = target_net_monthly_real
                elif cfg.spending_policy == "Rule only":
                    desired_net_real = rule_monthly_real
                else:  # "Lower of rule & target"
                    desired_net_real = min(target_net_monthly_real, rule_monthly_real)

                # Legacy mode cap (preserve initial real principal)
                if cfg.legacy_mode == "Preserve capital (real)":
                    allowable = max(0.0, w - initial_real_principal)
                    desired_net_real = min(desired_net_real, allowable)

                # Convert desired NET to required GROSS using indexed tax
                sys = index_tax(SYSTEMS[cfg.country], tax_factor_for_month(m))
                annual_net_real   = desired_net_real * 12.0
                annual_gross_real = gross_for_net(annual_net_real, sys)

                monthly_gross_real = min(w, annual_gross_real / 12.0)
                # Record delivered net (cap by gross if cash-limited)
                delivered_net = min(monthly_gross_real, annual_net_real/12.0)

                w = max(0.0, w - monthly_gross_real)
                net_wd[i, m] = delivered_net

            wealth[i, m] = w

    # Summaries
    ages = cfg.current_age + np.arange(months_total+1)/12.0
    pct = lambda X, q: np.percentile(X, q, axis=0)

    # Success: meet *basket target* for ≥ success_cover_pct of retirement months, AND finish ≥ 0.
    success_flags = np.zeros(cfg.num_paths, dtype=bool)
    cover_ratios  = np.zeros(cfg.num_paths, dtype=np.float64)
    if months_total > retire_m:
        target_slice = cfg.target_monthly_real_by_month[retire_m:]
        # If target is zero somewhere (shouldn't be), treat as covered
        target_eps = np.maximum(target_slice, 1e-12)
        check = net_wd[:, retire_m:] >= (target_slice - 1e-9)
        cover_ratios = check.mean(axis=1)
        finish_ok = wealth[:, -1] >= 0.0
        success_flags = (cover_ratios >= cfg.success_cover_pct) & finish_ok
    else:
        success_flags = wealth[:, -1] >= 0.0
        cover_ratios[:] = 1.0

    # Some reporting helpers
    retire_idx = retire_m
    target_annual_real_at_retire = float(cfg.target_monthly_real_by_month[retire_idx] * 12.0)

    summary = {
        "ages": ages,
        "success_rate": 100.0 * success_flags.mean(),
        "wealth_p5":  pct(wealth, 5),   "wealth_p50": pct(wealth, 50),   "wealth_p95": pct(wealth, 95),
        "wd_p5":      pct(net_wd, 5)*12,"wd_p50":     pct(net_wd, 50)*12,"wd_p95":     pct(net_wd, 95)*12,
        "coverage_p50": float(np.percentile(cover_ratios, 50)),
        "coverage_p5":  float(np.percentile(cover_ratios, 5)),
        "coverage_p95": float(np.percentile(cover_ratios, 95)),
        "retire_age": cfg.retire_age,
        "target_annual_real": target_annual_real_at_retire,
        "target_annual_real_series": cfg.target_monthly_real_by_month * 12.0  # shape (months+1,)
    }
    detail = {"wealth": wealth, "net_wd": net_wd}
    return summary, detail
