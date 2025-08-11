import numpy as np
import pandas as pd
from dataclasses import dataclass
from dateutil.relativedelta import relativedelta
from tax_uk import bands_with_inflation_factor, net_from_gross, gross_needed_for_net
from drawdown import guardrails

@dataclass
class SimConfig:
    start_age: int
    retire_age: int
    end_age: int
    monthly_contribution: float
    contribution_growth_pct: float # nominal
    current_investable: float
    equity_alloc: float
    bond_alloc: float
    equity_real_return: float
    equity_vol: float
    bond_real_return: float
    bond_vol: float
    corr_equity_bond: float
    fees_annual: float
    cpi: float
    category_basket_annual_today: float
    preserve_capital: bool       # True = legacy mode (keep real principal), False = spend-to-zero
    headline_rule: str           # "3% real" or "4% real" etc.
    guardrails_cfg: dict
    num_paths: int
    seed: int
    uk_tax: bool

def _mix_returns(e_mu, e_sigma, b_mu, b_sigma, corr, n, rng):
    # monthly real returns for equities & bonds (Geometric Brownian motion approximated)
    cov = np.array([[e_sigma**2, corr*e_sigma*b_sigma],
                    [corr*e_sigma*b_sigma, b_sigma**2]])
    # Convert annual to monthly: mu_m ~ mu_a/12, sigma_m ~ sigma_a/sqrt(12)
    mu_m = np.array([e_mu/12.0, b_mu/12.0])
    sigma_m = np.array([e_sigma/np.sqrt(12.0), b_sigma/np.sqrt(12.0)])
    cov_m = np.array([[sigma_m[0]**2, corr*sigma_m[0]*sigma_m[1]],
                      [corr*sigma_m[0]*sigma_m[1], sigma_m[1]**2]])
    draws = rng.multivariate_normal(mean=mu_m, cov=cov_m, size=n)
    return draws  # shape (n, 2)

def run_paths(cfg: SimConfig):
    months = (cfg.end_age - cfg.start_age) * 12
    contrib = cfg.monthly_contribution
    contrib_growth = 1 + cfg.contribution_growth_pct/100.0
    fees_m = (1 - cfg.fees_annual) ** (1/12.0)

    rng = np.random.default_rng(cfg.seed)
    rb = _mix_returns(cfg.equity_real_return, cfg.equity_vol,
                      cfg.bond_real_return, cfg.bond_vol,
                      cfg.corr_equity_bond, months, rng)
    eq_r = rb[:,0]
    bd_r = rb[:,1]

    weights = np.array([cfg.equity_alloc, cfg.bond_alloc])
    real_port = np.zeros(months+1)
    real_port[0] = cfg.current_investable
    retired = False
    first_withdrawal_month = None

    # Taxes & CPI indexing
    tax_factor = 1.0
    cpi_m = (1 + cfg.cpi) ** (1/12.0)

    # Spending target (annual) in today's money from basket:
    target_annual_real = cfg.category_basket_annual_today
    target_monthly_real = target_annual_real / 12.0

    # Headline static rule (3% real baseline) — initial real spend as % of initial portfolio OR as target?
    # We support two modes: (a) meet basket if possible (strict), (b) static rule "3% real"
    rule_pct = 0.03 if "3%" in cfg.headline_rule else 0.04
    initial_port_real = real_port[0]
    initial_rule_spend_annual_real = initial_port_real * rule_pct
    current_rule_spend_monthly_real = initial_rule_spend_annual_real / 12.0

    # If preserve_capital True: we avoid depleting real principal (we cap withdrawals accordingly)
    results = {
        "month": np.arange(months+1),
        "age": cfg.start_age + np.arange(months+1)/12.0,
        "real_portfolio": np.zeros(months+1),
        "real_withdrawal_net": np.zeros(months+1),   # after tax, real £
        "real_withdrawal_gross": np.zeros(months+1), # before tax, real £
        "retired_flag": np.zeros(months+1, dtype=bool)
    }
    results["real_portfolio"][0] = real_port[0]

    for m in range(1, months+1):
        # Grow contributions nominally, but convert to real by dividing CPI
        if not retired and (cfg.start_age + (m-1)/12.0) < cfg.retire_age:
            contrib *= (contrib_growth ** (1/12.0))
            real_contrib = contrib / (cpi_m ** m)
            real_port[m-1] += real_contrib

        # Monthly real return of portfolio
        port_r = weights[0]*eq_r[m-1] + weights[1]*bd_r[m-1]
        real_port[m] = max(0.0, (real_port[m-1]) * (1 + port_r))  # net of inflation since returns are real
        real_port[m] *= fees_m  # apply fees

        # Retire if at/after retire age
        if not retired and (cfg.start_age + m/12.0) >= cfg.retire_age:
            retired = True

        # CPI-index tax bands (annual index on yearly ticks). Approx: index monthly by cpi_m^12 each year boundary.
        if m % 12 == 0:
            tax_factor *= (1 + cfg.cpi)

        # Withdrawals in retirement
        if retired:
            # Base target: basket or rule
            target_monthly_real_now = target_monthly_real
            rule_monthly_real_now = current_rule_spend_monthly_real

            # Decide spending policy:
            if cfg.preserve_capital:
                # cap spending to not reduce real principal below start
                # naive cap: <= (real_port[m] - initial_port_real) positive part can be spent; otherwise min(target, rule)
                allowable = max(0.0, real_port[m] - initial_port_real)
                desired = min(target_monthly_real_now, rule_monthly_real_now)
                gross_real_try = min(desired, allowable)
            else:
                # spend-to-zero / sustainable: take the min of (basket vs rule), then allow guardrails
                desired = min(target_monthly_real_now, rule_monthly_real_now)
                if m % 12 == 1:  # annually apply guardrails to the *gross* budget
                    last_gross_annual = np.sum(results["real_withdrawal_gross"][max(0,m-12):m]) * 12/12.0
                    proposed_annual = guardrails(
                        current_spend_gross=desired*12,
                        portfolio=real_port[m],
                        start_pct=cfg.guardrails_cfg["initial_pct"],
                        band=cfg.guardrails_cfg["raise_cut"],
                        max_raise=cfg.guardrails_cfg["max_raise"],
                        max_cut=cfg.guardrails_cfg["max_cut"],
                        last_spend_gross=last_gross_annual if last_gross_annual>0 else desired*12,
                        portfolio_start=initial_port_real
                    )
                    desired = proposed_annual/12.0
                gross_real_try = desired

            # Tax bands (annual, real) — apply to *nominal* in reality, but we keep everything real-consistent:
            bands = bands_with_inflation_factor(tax_factor)

            # Convert desired *net* or *gross*? Our "desired" here is gross budget pre-tax in real £.
            # Now apply taxes: we need gross to net conversion; then store both in *real*.
            gross_real = gross_real_try
            net_real = gross_real - (gross_real - (gross_real - 0))  # placeholder, we'll compute properly below

            # Proper tax: compute gross nominal needed for net nominal. Keep things in annual terms.
            # Here, treat "gross_real" as our gross *target*. To be conservative, we treat it as *net target*.
            # That is: ensure after tax they get the desired real cash.
            annual_net_real_target = gross_real * 12.0
            # Convert to nominal, solve for gross nominal using bands, then transform back to real:
            # In real space, indexing cancels; we can directly call gross_needed_for_net since tax bands are indexed similarly.
            gross_annual_real = gross_needed_for_net(annual_net_real_target, bands)
            net_annual_real = annual_net_real_target  # by construction
            monthly_gross_real = gross_annual_real / 12.0
            monthly_net_real = net_annual_real / 12.0

            # Ensure we can't withdraw more than portfolio
            monthly_gross_real = min(monthly_gross_real, real_port[m])
            monthly_net_real = min(monthly_net_real, monthly_gross_real)  # net <= gross, safe bound

            real_port[m] = max(0.0, real_port[m] - monthly_gross_real)
            results["real_withdrawal_gross"][m] = monthly_gross_real
            results["real_withdrawal_net"][m] = monthly_net_real
            results["retired_flag"][m] = True
            if first_withdrawal_month is None and monthly_gross_real > 1e-9:
                first_withdrawal_month = m

    df = pd.DataFrame(results)
    meta = {
        "first_withdrawal_month": first_withdrawal_month,
        "success": (first_withdrawal_month is not None) and (df["real_portfolio"].iloc[-1] > 0)
    }
    return df, meta

def run_monte_carlo(cfg: SimConfig):
    rng = np.random.default_rng(cfg.seed)
    metas = []
    series = []
    for i in range(cfg.num_paths):
        # jitter seed per path to avoid identical paths
        path_cfg = cfg
        path_cfg.seed = int(rng.integers(0, 2**31-1))
        df, meta = run_paths(path_cfg)
        metas.append(meta)
        series.append(df)

    # Compute probability of success
    success_rate = 100.0 * (sum(m["success"] for m in metas) / cfg.num_paths)

    # Percentiles for withdrawals and wealth
    ages = series[0]["age"].values
    wealth_stack = np.vstack([s["real_portfolio"].values for s in series])
    wd_stack = np.vstack([s["real_withdrawal_net"].values for s in series])

    pct = lambda arr, q: np.percentile(arr, q, axis=0)
    wealth_p5, wealth_p50, wealth_p95 = pct(wealth_stack, 5), pct(wealth_stack, 50), pct(wealth_stack, 95)
    wd_p5, wd_p50, wd_p95 = pct(wd_stack, 5), pct(wd_stack, 50), pct(wd_stack, 95)

    return {
        "ages": ages,
        "success_rate": success_rate,
        "wealth_p5": wealth_p5, "wealth_p50": wealth_p50, "wealth_p95": wealth_p95,
        "wd_p5": wd_p5, "wd_p50": wd_p50, "wd_p95": wd_p95,
    }, series
