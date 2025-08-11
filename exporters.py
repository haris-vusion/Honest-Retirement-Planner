import json
import pandas as pd
import numpy as np

def export_median_series(summary: dict) -> tuple[str, bytes]:
    df = pd.DataFrame({
        "age": summary["ages"],
        "wealth_median_real": summary["wealth_p50"],
        "income_median_real_annual": summary["wd_p50"],
    })
    return "median_series.csv", df.to_csv(index=False).encode()

def export_config(cfg_dict: dict) -> tuple[str, bytes]:
    return "config.json", json.dumps(cfg_dict, indent=2).encode()
