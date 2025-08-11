from dataclasses import dataclass, field
from typing import List, Optional
import math
import pandas as pd

# ---------- Data structures ----------
@dataclass
class Bracket:
    upper: float  # upper limit of bracket; use math.inf for top
    rate: float   # e.g., 0.20

@dataclass
class TaxSpec:
    name: str
    allowance: float = 0.0
    brackets: List[Bracket] = field(default_factory=list)
    taper_start: Optional[float] = None  # UK PA taper start
    taper_ratio: float = 0.5             # £1 PA lost per £2 => 0.5
    medicare_levy: float = 0.0           # AU levy applied to taxable

def _apply_taper(gross: float, allowance: float, spec: TaxSpec) -> float:
    if spec.taper_start is None:
        return allowance
    if gross <= spec.taper_start:
        return allowance
    reduction = max(0.0, (gross - spec.taper_start) * spec.taper_ratio)
    return max(0.0, allowance - reduction)

def tax_due(gross: float, spec: TaxSpec) -> float:
    if gross <= 0:
        return 0.0
    eff_allow = _apply_taper(gross, spec.allowance, spec)
    taxable = max(0.0, gross - eff_allow)
    last_upper = 0.0
    tax = 0.0
    for b in spec.brackets:
        up = b.upper if math.isfinite(b.upper) else taxable + last_upper
        width = max(0.0, min(taxable, up - last_upper))
        tax += width * b.rate
        last_upper += width
        if last_upper >= taxable - 1e-9:
            break
    if spec.medicare_levy > 0:
        tax += taxable * spec.medicare_levy
    return tax

def net_from_gross(gross: float, spec: TaxSpec) -> float:
    return gross - tax_due(gross, spec)

def gross_needed_for_net(net_target: float, spec: TaxSpec) -> float:
    if net_target <= 0:
        return 0.0
    lo, hi = 0.0, 2_000_000_000.0
    for _ in range(70):
        mid = (lo + hi) / 2.0
        if net_from_gross(mid, spec) < net_target:
            lo = mid
        else:
            hi = mid
    return hi

def index_spec(spec: TaxSpec, factor: float) -> TaxSpec:
    def idx(x): return (x if math.isinf(x) else x * factor)
    return TaxSpec(
        name=spec.name,
        allowance=spec.allowance * factor,
        brackets=[Bracket(upper=idx(b.upper), rate=b.rate) for b in spec.brackets],
        taper_start=(None if spec.taper_start is None else spec.taper_start * factor),
        taper_ratio=spec.taper_ratio,
        medicare_levy=spec.medicare_levy,
    )

# ---------- Presets (baseline; user can edit) ----------
def default_tax_spec(country: str) -> TaxSpec:
    c = country.lower()
    if c == "uk":
        return TaxSpec(
            name="UK",
            allowance=12_570,
            brackets=[
                Bracket(upper=50_270, rate=0.20),
                Bracket(upper=125_140, rate=0.40),
                Bracket(upper=math.inf, rate=0.45),
            ],
            taper_start=100_000,
            taper_ratio=0.5,
        )
    if c == "usa":
        # Federal only, single filer (simplified). State taxes not included.
        return TaxSpec(
            name="USA (federal, single)",
            allowance=14_600,
            brackets=[
                Bracket(upper=11_600, rate=0.10),
                Bracket(upper=47_150, rate=0.12),
                Bracket(upper=100_525, rate=0.22),
                Bracket(upper=191_950, rate=0.24),
                Bracket(upper=243_725, rate=0.32),
                Bracket(upper=609_350, rate=0.35),
                Bracket(upper=math.inf, rate=0.37),
            ],
        )
    if c == "france":
        # Simplified IR with one "part" (no quotient familial here)
        return TaxSpec(
            name="France (simplified, 1 part)",
            allowance=0.0,
            brackets=[
                Bracket(upper=11_294, rate=0.00),
                Bracket(upper=28_797, rate=0.11),
                Bracket(upper=82_341, rate=0.30),
                Bracket(upper=177_106, rate=0.41),
                Bracket(upper=math.inf, rate=0.45),
            ],
        )
    if c == "germany":
        # Simplified stepwise approximation for singles
        return TaxSpec(
            name="Germany (simplified)",
            allowance=11_000,
            brackets=[
                Bracket(upper=62_000, rate=0.14),
                Bracket(upper=277_000, rate=0.42),
                Bracket(upper=math.inf, rate=0.45),
            ],
        )
    if c == "australia":
        return TaxSpec(
            name="Australia (resident)",
            allowance=18_200,
            brackets=[
                Bracket(upper=45_000, rate=0.19),
                Bracket(upper=120_000, rate=0.325),
                Bracket(upper=180_000, rate=0.37),
                Bracket(upper=math.inf, rate=0.45),
            ],
            medicare_levy=0.02,
        )
    return TaxSpec(
        name="Custom",
        allowance=12_000,
        brackets=[
            Bracket(upper=50_000, rate=0.20),
            Bracket(upper=150_000, rate=0.40),
            Bracket(upper=math.inf, rate=0.45),
        ],
    )

# ---------- Streamlit helpers ----------
def spec_to_df(spec: TaxSpec) -> pd.DataFrame:
    data = []
    for b in spec.brackets:
        up = (1e12 if math.isinf(b.upper) else b.upper)
        data.append({"upper_limit": float(up), "rate_percent": b.rate * 100})
    return pd.DataFrame(data)

def df_to_spec(df: pd.DataFrame, allowance: float, base_name: str, extra: dict) -> TaxSpec:
    brackets = []
    for _, row in df.sort_values("upper_limit").iterrows():
        up = float(row["upper_limit"])
        rate = float(row["rate_percent"]) / 100.0
        if up >= 9.9e11:
            up = math.inf
        brackets.append(Bracket(upper=up, rate=rate))
    return TaxSpec(
        name=base_name,
        allowance=float(allowance),
        brackets=brackets,
        taper_start=extra.get("taper_start"),
        taper_ratio=extra.get("taper_ratio", 0.5),
        medicare_levy=extra.get("medicare_levy", 0.0),
    )