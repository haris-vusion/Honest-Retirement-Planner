# exporters.py
import json
import numpy as np
import pandas as pd

def export_median_series(summary: dict) -> tuple[str, bytes]:
    df = pd.DataFrame({
        "age": summary["ages"],
        "wealth_median_real": summary["wealth_p50"],
        "income_median_real_annual": summary["wd_p50"],
    })
    return "median_series.csv", df.to_csv(index=False).encode()

def _json_default(o):
    # Handle numpy arrays & scalars cleanly for JSON
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (np.float32, np.float64, np.int32, np.int64)):
        return o.item()
    # Let json raise for anything else unexpected
    raise TypeError(f"Object of type {o.__class__.__name__} is not JSON serializable")

def export_config(cfg_dict: dict) -> tuple[str, bytes]:
    """
    Safely export the current configuration to JSON.
    Handles numpy arrays/scalars (e.g., target_monthly_real_by_month).
    """
    blob = json.dumps(cfg_dict, indent=2, default=_json_default)
    return "config.json", blob.encode()
