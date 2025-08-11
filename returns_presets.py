# Simple, opinionated ROI presets. All are *real* long-run estimates (after inflation).
# Vol = annualized standard deviation.
# These are not promises—just sane defaults users can override.

PRESETS = {
    "S&P 500 (SPY)": {"real_mu": 0.055, "vol": 0.18},
    "NASDAQ-100 (QQQ)": {"real_mu": 0.065, "vol": 0.24},
    "FTSE 100": {"real_mu": 0.035, "vol": 0.16},
    "MSCI ACWI (global)": {"real_mu": 0.05, "vol": 0.17},
    "60/40 Global": {"real_mu": 0.04, "vol": 0.11},
    "Bonds (Global Agg)": {"real_mu": 0.01, "vol": 0.06},
}
