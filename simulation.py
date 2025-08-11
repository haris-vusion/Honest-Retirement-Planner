from __future__ import annotations

from dataclasses import dataclass, replace
import numpy as np
import pandas as pd
from typing import Tuple
from tax_models import TaxSpec, index_spec, gross_needed_for_net

@dataclass
class SimConfig:
    # Ages
    age_now: int
    retire_age: float
    plan_until_age: int

    # Money now
    assets_now: float
    monthly_contrib: float
    contrib_growth_pct: float  # nominal %/yr

    # Returns (real)
    equity_alloc: float
    bond_alloc: float
    equity_mu: float        # %/yr real
    equity_vol: float       # %/yr
    bond_mu: float
    bond_vol: float
    corr: float
    fees_annual: float      # %/yr

    # Inflation
    cpi_pct: float          # %/yr

    # Spending target (annual, in today's money)
    target_annual_real: float

    # Withdrawal
    rule_pct: float         # 0.03 / 0.035 / 0.04
    preserve_capital: bool  # legacy mode

    # Tax
    tax_spec_baseline: TaxSpec

    # Sims
    num_paths: int
    seed: int | None

def _monthly_from_annual(mu: float, vol: float):
    # Convert annual real mean/vol to monthly approx
    mu_m = mu / 12.0
    vol_m = vol / np.sqrt(12.0)
    return mu_m, vol_m

def _draw_monthly_returns(cfg: SimConfig, months: int, rng: np.random.Generator):
    mu_e_m, vol_e_m = _monthly_from_annual(cfg.equity_mu/100.0, cfg.equity_vol/100.0)
    mu_b_m, vol_b_m = _monthly_from_annual(cfg.bond_mu/100.0, cfg.bond_vol/100.0)
    cov = np.array([[vol_e_m**2, cfg.corr*vol_e_m*vol_b_m],
                    [cfg.corr*vol_e_m*vol_b_m, vol_b_m**2]])
    draws = rng.multivariate_normal(mean=[mu_e_m, mu_b_m], cov=cov, size=months)
    return draws[:,0], draws[:,1]

def run_monte_carlo(cfg: SimConfig) -> Tuple[dict, pd.DataFrame]:
    months = int((cfg.plan_until_age - cfg.age_now) * 12)
    retire_m = int((cfg.retire_age - cfg.age_now) * 12)
    fees_m = (1 - cfg.fees_annual/100.0) ** (1/12.0)
    cpi_m = (1 + cfg.cpi_pct/100.0) ** (1/12.0)
    rng = np.random.default_rng(cfg.seed)

    wealth = np.empty((cfg.num_paths, months+1), dtype=float)
    wd_net = np.empty((cfg.num_paths, months+1), dtype=float)
    success = 0

    for i in range(cfg.num_paths):
        # unique seed per path
        path_seed = int(rng.integers(0, 2**31-1))
        prng = np.random.default_rng(path_seed)
        e_r, b_r = _draw_monthly_returns(cfg, months, prng)

        w = np.zeros(months+1, dtype=float)
        w[0] = cfg.assets_now
        wd = np.zeros(months+1, dtype=float)

        contrib = cfg.monthly_contrib
        tax_factor = 1.0
        rule_monthly_real = (cfg.assets_now * cfg.rule_pct) / 12.0  # initial rule amount in real terms

        for m in range(1, months+1):
            # grow contributions nominally, convert to real by dividing CPI^m
            if m <= retire_m:
                contrib *= (1 + cfg.contrib_growth_pct/100.0) ** (1/12.0)
                real_contrib = contrib / (cpi_m ** m)
            else:
                real_contrib = 0.0

            w[m-1] += real_contrib

            # apply monthly real return and fees
            port_r = cfg.equity_alloc*e_r[m-1] + cfg.bond_alloc*b_r[m-1]
            w[m] = max(0.0, w[m-1]*(1 + port_r))
            w[m] *= fees_m

            # index tax annually
            if m % 12 == 0:
                tax_factor *= (1 + cfg.cpi_pct/100.0)

            # withdrawals after retirement
            if m > retire_m:
                # choose target: minimum of basket vs rule
                basket_monthly_real = (cfg.target_annual_real / 12.0)
                desired_real_net = min(basket_monthly_real, rule_monthly_real)

                # legacy mode: do not cut into initial real principal (very conservative)
                if cfg.preserve_capital:
                    allowable = max(0.0, w[m] - w[0])
                    desired_real_net = min(desired_real_net, allowable)

                # turn net real into gross real using indexed tax spec
                spec = index_spec(cfg.tax_spec_baseline, tax_factor)
                gross_annual_real = gross_needed_for_net(desired_real_net*12.0, spec)
                gross_month_real = gross_annual_real/12.0

                # cap by portfolio
                gross_month_real = min(gross_month_real, w[m])

                w[m] = max(0.0, w[m] - gross_month_real)
                wd[m] = desired_real_net  # store net (real)

        if w[-1] > 0 and np.any(wd[retire_m+1:] > 0):
            success += 1

        wealth[i, :] = w
        wd_net[i, :] = wd

    # summarise
    ages = cfg.age_now + np.arange(months+1)/12.0
    pct = lambda a,q: np.percentile(a, q, axis=0)

    summary = {
        "ages": ages,
        "success_rate": 100.0 * success / cfg.num_paths,
        "wealth_p5": pct(wealth, 5),
        "wealth_p50": pct(wealth, 50),
        "wealth_p95": pct(wealth, 95),
        "wd_p5": pct(wd_net, 5),
        "wd_p50": pct(wd_net, 50),
        "wd_p95": pct(wd_net, 95),
    }

    # median series DataFrame for export
    series = pd.DataFrame({
        "age": ages,
        "real_portfolio_median": summary["wealth_p50"],
        "real_net_withdrawal_median": summary["wd_p50"],
    })

    return summary, series
