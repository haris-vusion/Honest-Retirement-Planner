"""
Very simplified progressive income tax for withdrawals.
Goal: give realistic ballpark, not handle every edge case.

We model: taxable bands + rates; a basic allowance/standard deduction where relevant.
All amounts are *nominal*, but in the simulation we index brackets with CPI each year.
"""

from dataclasses import dataclass
from typing import List, Tuple

@dataclass
class Band:
    up_to: float  # upper threshold (inclusive) in local currency
    rate: float   # marginal rate, e.g., 0.20 for 20%

@dataclass
class TaxSystem:
    name: str
    allowance: float       # personal allowance / standard deduction (applied before bands)
    taper_start: float = None  # UK-style taper threshold (optional)
    bands: List[Band] = None   # must be sorted by up_to
    top_rate: float = 0.0      # rate above last band
    notes: str = ""

def _uk():
    # 2024/25 baseline, simplified; allowance tapers £1 per £2 over £100k
    return TaxSystem(
        name="United Kingdom",
        allowance=12_570,
        taper_start=100_000,
        bands=[
            Band(50_270, 0.20),
            Band(125_140, 0.40),
        ],
        top_rate=0.45,
        notes="Simplified UK rates with personal allowance taper."
    )

def _us():
    # US single filer 2024-ish simplified standard deduction and brackets
    return TaxSystem(
        name="United States",
        allowance=14_600,  # standard deduction (single). You can edit in UI if needed.
        bands=[
            Band(47_150, 0.12),
            Band(100_525, 0.22),
            Band(191_950, 0.24),
            Band(243_725, 0.32),
            Band(609_350, 0.35),
        ],
        top_rate=0.37,
        notes="Simplified federal brackets; no state tax modeled."
    )

def _fr():
    # France 2024 simplified scale, single, after allowance
    return TaxSystem(
        name="France",
        allowance=0.0,
        bands=[
            Band(11_294, 0.0),
            Band(28_797, 0.11),
            Band(82_341, 0.30),
            Band(177_106, 0.41),
        ],
        top_rate=0.45,
        notes="Simplified, ignoring social contributions."
    )

def _de():
    # Germany very simplified progressive steps (real system is continuous curve)
    return TaxSystem(
        name="Germany",
        allowance=11_604,  # Grundfreibetrag
        bands=[
            Band(62_810, 0.20),
            Band(277_825, 0.42),
        ],
        top_rate=0.45,
        notes="Simplified steps; solidarity surcharge/other nuances ignored."
    )

def _au():
    # Australia resident 2024/25 simplified
    return TaxSystem(
        name="Australia",
        allowance=18_200,  # tax-free threshold
        bands=[
            Band(45_000, 0.19),
            Band(120_000, 0.325),
            Band(180_000, 0.37),
        ],
        top_rate=0.45,
        notes="Simplified; Medicare levy ignored."
    )

SYSTEMS = {
    "United Kingdom": _uk(),
    "United States": _us(),
    "France": _fr(),
    "Germany": _de(),
    "Australia": _au(),
}

def indexed(system: TaxSystem, factor: float) -> TaxSystem:
    """Scale thresholds by factor (to approximate bracket indexation with CPI)."""
    return TaxSystem(
        name=system.name,
        allowance=system.allowance * factor,
        taper_start=None if system.taper_start is None else system.taper_start * factor,
        bands=[Band(b.up_to * factor, b.rate) for b in system.bands],
        top_rate=system.top_rate,
        notes=system.notes
    )

def tax_due(gross: float, sys: TaxSystem) -> float:
    if gross <= 0:
        return 0.0
    allowance = sys.allowance
    if sys.taper_start is not None and gross > sys.taper_start:
        # UK-style taper: lose £1 of allowance per £2 above threshold
        allowance = max(0.0, allowance - (gross - sys.taper_start)/2.0)

    taxable = max(0.0, gross - allowance)
    tax = 0.0
    last = 0.0
    for band in sys.bands:
        if taxable > band.up_to - last:
            tax += (band.up_to - last) * band.rate
            last = band.up_to
        else:
            tax += taxable * band.rate
            return tax
    # above last band
    tax += (taxable - last) * sys.top_rate
    return tax

def net_from_gross(gross: float, sys: TaxSystem) -> float:
    return gross - tax_due(gross, sys)

def gross_for_net(net_target: float, sys: TaxSystem) -> float:
    if net_target <= 0:
        return 0.0
    lo, hi = 0.0, 2_000_000.0
    for _ in range(60):
        mid = (lo + hi)/2.0
        if net_from_gross(mid, sys) < net_target:
            lo = mid
        else:
            hi = mid
    return hi
