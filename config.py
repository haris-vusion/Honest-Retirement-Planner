APP_NAME = "FutureProof: Honest Retirement Planner"

# Default assumptions (UK-leaning; all "real" unless otherwise noted)
DEFAULTS = {
    "start_age": 30,
    "retire_age": 60,
    "end_age": 95,
    "location": "UK",
    "household_size": 1,

    # Finances
    "current_investable": 20_000,
    "monthly_contribution": 800,
    "contribution_growth_pct": 2.0,   # nominal per year
    "salary": 60_000,
    "salary_growth_pct": 2.5,         # nominal per year

    # Asset mix (simple two-asset for v1)
    "equity_alloc": 0.8,
    "bond_alloc": 0.2,
    "equity_real_return": 0.055,      # long run global real
    "equity_vol": 0.18,
    "bond_real_return": 0.01,
    "bond_vol": 0.06,
    "corr_equity_bond": -0.2,
    "fees_annual": 0.002,             # 0.2%

    # Inflation
    "cpi": 0.025,                     # headline CPI
    "category_drifts": {              # relative to CPI (positive = more expensive trend)
        "rent": 0.01,
        "food": 0.005,
        "energy": 0.01,
        "transport": 0.0,
        "health": 0.01,
        "entertainment": 0.0,
        "electronics": -0.01
    },

    # Spending today (monthly, in today's money)
    "spend_today": {
        "rent": 1200,
        "food": 350,
        "energy": 150,
        "transport": 250,
        "health": 100,
        "entertainment": 200,
        "electronics": 50,
        "other": 300
    },

    # Drawdown
    "headline_withdrawal_rule": "3% real",  # selectable
    "guardrails": {                         # Guyton-Klinger lite
        "initial_pct": 0.04,
        "raise_cut": 0.1,                   # 10% bands
        "max_raise": 0.10,
        "max_cut": 0.10
    },

    # Sims
    "num_paths": 3,
    "seed": 123,

    # Taxes (indexed with inflation in sim)
    "uk_tax": True
}
