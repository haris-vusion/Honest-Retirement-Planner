import json

def export_config(cfg_dict: dict) -> bytes:
    return json.dumps(cfg_dict, indent=2).encode()

def export_series_csv(df) -> bytes:
    return df.to_csv(index=False).encode()
