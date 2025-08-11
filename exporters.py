import io, json
import pandas as pd

def export_cashflows_csv(series_list, name="cashflows.csv"):
    # Export the median series as example; or stack all
    df = series_list[0].copy()
    return name, df.to_csv(index=False).encode()

def export_config_json(cfg) -> tuple[str, bytes]:
    blob = json.dumps(cfg.__dict__, indent=2)
    return "config.json", blob.encode()
