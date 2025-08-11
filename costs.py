import numpy as np
import pandas as pd

def project_costs(spend_today: dict, cpi: float, drifts: dict, years: int) -> pd.DataFrame:
    idx = np.arange(years + 1)
    rows = []
    for cat, monthly_now in spend_today.items():
        drift = drifts.get(cat, 0.0)
        nom_mult = (1 + (cpi + drift)) ** idx
        real_mult = (1 + cpi) ** idx
        monthly_nominal = monthly_now * nom_mult
        monthly_real = monthly_nominal / real_mult
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

def basket(df: pd.DataFrame, year: int) -> dict:
    v = df[df["year"] == year]
    return {
        "monthly_nominal": float(v["monthly_nominal"].sum()),
        "monthly_real_today": float(v["monthly_real_today"].sum()),
        "annual_nominal": float(v["annual_nominal"].sum()),
        "annual_real_today": float(v["annual_real_today"].sum()),
    }
