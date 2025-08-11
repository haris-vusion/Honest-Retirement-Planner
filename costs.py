import numpy as np
import pandas as pd

def project_costs(basket_today: dict, cpi_pct: float, drifts_pct: dict, years: int) -> pd.DataFrame:
    """
    Inflate each category to each future year.
    Returns columns: year, category, monthly_nominal, monthly_real_today, annual_nominal, annual_real_today
    """
    cpi = cpi_pct / 100.0
    idx = np.arange(years + 1)
    rows = []
    for cat, m_now in basket_today.items():
        drift = (drifts_pct.get(cat, 0.0) / 100.0)
        nominal_mult = (1 + cpi + drift) ** idx
        real_div = (1 + cpi) ** idx
        monthly_nominal = m_now * nominal_mult
        monthly_real = monthly_nominal / real_div
        rows.append(pd.DataFrame({
            "year": idx,
            "category": cat,
            "monthly_nominal": monthly_nominal,
            "monthly_real_today": monthly_real
        }))
    out = pd.concat(rows, ignore_index=True)
    out["annual_nominal"] = out["monthly_nominal"] * 12
    out["annual_real_today"] = out["monthly_real_today"] * 12
    return out

def summarize_year(df: pd.DataFrame, year: int) -> dict:
    sub = df[df["year"] == year]
    return {
        "monthly_nominal": float(sub["monthly_nominal"].sum()),
        "monthly_real_today": float(sub["monthly_real_today"].sum()),
        "annual_nominal": float(sub["annual_nominal"].sum()),
        "annual_real_today": float(sub["annual_real_today"].sum()),
    }