APP_NAME = "FutureProof — Honest Retirement Planner"

DEFAULTS = {
    # Ages
    "current_age": 30,
    "retire_age": 60,
    "plan_end_age": 95,

    # Location/tax
    "country": "United Kingdom",  # United Kingdom / United States / France / Germany / Australia

    # Portfolio & saving (today)
    "current_investable": 20000,
    "monthly_contrib": 800,
    "contrib_growth_nominal_pct": 2.0,  # per year

    # Asset returns (real, after-inflation). You can pick a preset later.
    "exp_real_return": 0.05,   # long-run real
    "volatility": 0.16,        # annualized
    "fees_annual": 0.002,      # 0.20%

    # Inflation
    "headline_cpi": 0.025,

    # Spending basket today (monthly, in today’s £/$/€)
    "spend_today": {
        "housing": 1200,
        "food": 350,
        "energy": 150,
        "transport": 250,
        "health": 100,
        "entertainment": 200,
        "other": 300
    },

    # Category drifts vs CPI (positive = tends to outpace CPI)
    "category_drifts": {
        "housing": 0.01,
        "food": 0.005,
        "energy": 0.01,
        "transport": 0.0,
        "health": 0.01,
        "entertainment": 0.0,
        "other": 0.0
    },

    # Drawdown
    "withdrawal_rule": "3% real",    # or 3.5% real / 4% real
    "legacy_mode": "Spend to zero",  # or Preserve capital (real)

    # Monte Carlo
    "num_paths": 10,
    "seed": 42
}

