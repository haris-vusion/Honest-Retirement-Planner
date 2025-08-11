from __future__ import annotations

import numpy as np
from dataclasses import dataclass, replace
from taxes import SYSTEMS, indexed as index_tax, gross_for_net
from typing import Tuple

@dataclass
class SimConfig:
    current_age: int
    retire_age: int
    plan_end_age: int
    current_investable: float
    monthly_contrib: float
    contrib_growth_nominal_pct: float
    exp_real_return: float
    volatility: float
    fees_annual: float
    cpi: float
    annual_spend_target_real_today: float
    withdrawal_rule: str               # "3% real" / "3.5% real" / "4% real"
    legacy_mode: str                   # "Spend to zero" or "Preserve capital (real)"
    country: str
    num_paths: int
    seed: int | None

def _monthly_params(mu_a, sigma_a):
    mu_m = mu_a/12.0
    sigma_m = sigma_a/np.sqrt(12.0)
    return mu_m, sigma_m

def run_monte_carlo(cfg: SimConfig) -> Tuple[dict, dict]:
    months = int((cfg.plan_end_age - cfg.current_age) * 12)
    retire_m = int((cfg.retire_age - cfg.current_age) * 12)
    mu_m, sig_m = _monthly_params(cfg.exp_real_return, cfg.volatility)
    fees_m = (1 - cfg.fees_annual) ** (1/12.0)
    cpi_y = cfg.cpi
    cpi_m = (1 + cfg.cpi) ** (1/12.0)

    rng = np.random.default_rng(cfg.seed)
    # Pre-allocate (num_paths, months+1)
    wealth = np.empty((cfg.num_paths, months+1), dtype=np.float64)
    net_wd = np.zeros((cfg.num_paths, months+1), dtype=np.float64)
    retired = np.zeros((cfg.num_paths, months+1), dtype=bool)

    # Tax indexing factor each year
    tax_factor = 1.0

    # Withdrawal rule percent
    rule_map = {"3% real": 0.03, "3.5% real": 0.035, "4% real": 0.04}
    rule_pct = rule_map.get(cfg.withdrawal_rule, 0.03)

    draws = rng.normal(mu_m, sig_m, size=(cfg.num_paths, months))  # real monthly returns

    for i in range(cfg.num_paths):
        w = cfg.current_investable
        contrib = cfg.monthly_contrib
        wealth[i, 0] = w
        retired[i, retire_m:] = True
        initial_real_principal = cfg.current_investable

        for m in range(1, months+1):
            # contributions until retirement (nominal -> convert to real by dividing CPI growth)
            if m-1 < retire_m:
                contrib *= (1 + cfg.contrib_growth_nominal_pct/100.0) ** (1/12.0)
                real_contrib = contrib / (cpi_m ** m)
                w += real_contrib

            # portfolio growth (real) and fees
            w = max(0.0, w * (1 + draws[i, m-1]) * fees_m)

            # bump tax brackets each *year*
            if m % 12 == 0:
                tax_factor *= (1 + cpi_y)

            # retirement withdrawals
            if m-1 >= retire_m:
                # spending target (real, net of tax)
                basket_monthly_real = cfg.annual_spend_target_real_today / 12.0
                rule_monthly_real = (cfg.current_investable * rule_pct) / 12.0

                desired_net_real = min(basket_monthly_real, rule_monthly_real)

                if cfg.legacy_mode == "Preserve capital (real)":
                    # Cap so real principal doesn't fall below starting point
                    allowable = max(0.0, w - initial_real_principal)
                    desired_net_real = min(desired_net_real, allowable)

                # Convert to gross using current country's indexed tax
                sys = index_tax(SYSTEMS[cfg.country], tax_factor)
                annual_net_real = desired_net_real * 12.0
                annual_gross_real = gross_for_net(annual_net_real, sys)
                monthly_gross_real = min(w, annual_gross_real / 12.0)
                monthly_net_real = min(monthly_gross_real, annual_net_real / 12.0)

                w = max(0.0, w - monthly_gross_real)
                net_wd[i, m] = monthly_net_real

            wealth[i, m] = w

    # Summaries
    ages = cfg.current_age + np.arange(months+1)/12.0
    pct = lambda X, q: np.percentile(X, q, axis=0)
    success = (wealth[:, -1] >= 0.0) & (np.any(net_wd > 0, axis=1))
    summary = {
        "ages": ages,
        "success_rate": 100.0 * success.mean(),
        "wealth_p5": pct(wealth, 5),  "wealth_p50": pct(wealth, 50),  "wealth_p95": pct(wealth, 95),
        "wd_p5": pct(net_wd, 5)*12,   "wd_p50": pct(net_wd, 50)*12,  "wd_p95": pct(net_wd, 95)*12,  # annualized
    }
    detail = {"wealth": wealth, "net_wd": net_wd}
    return summary, detail
