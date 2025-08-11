import copy
from dataclasses import asdict
from simulation import SimConfig, run_monte_carlo

def clone_cfg(cfg: SimConfig, **overrides):
    base = asdict(cfg)
    base.update(overrides)
    return SimConfig(**base)

def compare(cfg_main: SimConfig, variants: list[tuple[str, dict]]):
    """
    variants: list of (name, overrides-dict)
    returns: dict name -> results
    """
    res = {}
    for name, edits in variants:
        cfg_v = clone_cfg(cfg_main, **edits)
        res[name] = run_monte_carlo(cfg_v)[0]
    return res
