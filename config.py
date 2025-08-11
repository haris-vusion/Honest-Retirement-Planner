APP_NAME = "FutureProof — Retirement Wizard"

CURRENCIES = {
    "UK": "£",
    "USA": "$",
    "France": "€",
    "Germany": "€",
    "Australia": "A$",
    "Custom": "¤",
}

DEFAULTS = {
    "country": "UK",
    "age_now": 30,
    "retire_age": 60,
    "plan_until_age": 95,

    # Finances today (local currency)
    "assets_now": 20_000,
    "monthly_contrib": 800,
    "contrib_growth_pct": 2.0,   # %/yr, nominal

    # Spending today (monthly)
    "basket_today": {
        "rent_or_housing": 1200,
        "food": 350,
        "energy": 150,
        "transport": 250,
        "health_insurance": 100,
        "entertainment": 200,
        "electronics_gadgets": 50,
        "other_everyday": 300,
    },

    # Inflation assumptions
    "cpi": 2.5,   # headline CPI %/yr
    "drifts": {   # category drift relative to CPI (in %/yr)
        "rent_or_housing": 1.0,
        "food": 0.5,
        "energy": 1.0,
        "transport": 0.0,
        "health_insurance": 1.0,
        "entertainment": 0.0,
        "electronics_gadgets": -1.0,
        "other_everyday": 0.0,
    },

    # Investment assumptions (real)
    "equity_alloc": 0.8,
    "bond_alloc": 0.2,
    "equity_mu": 5.5,    # % real
    "equity_vol": 18.0,  # %
    "bond_mu": 1.0,      # %
    "bond_vol": 6.0,     # %
    "corr": -0.2,
    "fees_annual": 0.20, # %/yr

    # Withdrawal preferences
    "rule": "3% real",               # 3% / 3.5% / 4%
    "legacy_mode": "Spend to zero",  # or "Preserve capital"

    # Simulation
    "num_paths": 5,
    "seed": 123,
}
