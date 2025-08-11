import numpy as np
import pandas as pd

def project_category_costs(spend_today: dict, cpi: float, drifts: dict, years: int) -> pd.DataFrame:
    """
    Returns a DataFrame with nominal and real costs per category for each future year.
    CPI is headline; drifts are category-specific adjustments *added* to CPI for nominal projections.
    """
    idx = np.arange(years + 1)  # 0..years
    rows = []
    for cat, monthly_now in spend_today.items():
        drift = drifts.get(cat, 0.0)
        nominal_multiplier = (1 + (cpi + drift)) ** idx
        real_multiplier = (1 + cpi) ** idx
        monthly_nominal = monthly_now * nominal_multiplier
        monthly_real = monthly_nominal / real_multiplier  # expresses in today's money (sanity check ~flat)
        rows.append(pd.DataFrame({
            "year": idx,
            "category": cat,
            "monthly_nominal": monthly_nominal,
            "monthly_real_today£": monthly_real
        }))
    out = pd.concat(rows, ignore_index=True)
    out["annual_nominal"] = out["monthly_nominal"] * 12
    out["annual_real_today£"] = out["monthly_real_today£"] * 12
    return out

def basket_for_year(df: pd.DataFrame, year: int):
    view = df[df["year"] == year].copy()
    return {
        "monthly_nominal": float(view["monthly_nominal"].sum()),
        "monthly_real_today£": float(view["monthly_real_today£"].sum()),
        "annual_nominal": float(view["annual_nominal"].sum()),
        "annual_real_today£": float(view["annual_real_today£"].sum())
    }
