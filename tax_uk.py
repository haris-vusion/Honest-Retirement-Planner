from dataclasses import dataclass

# 2024/25 baseline (UK) — these will be indexed by CPI in the sim
BASE_PERSONAL_ALLOWANCE = 12_570
BASE_BASIC_RATE_LIMIT = 50_270
BASE_HIGHER_RATE_LIMIT = 125_140
BASE_PA_TAPER_START = 100_000

@dataclass
class TaxBands:
    pa: float
    brt: float
    hrt: float
    taper_start: float

def bands_with_inflation_factor(factor: float) -> TaxBands:
    return TaxBands(
        pa=BASE_PERSONAL_ALLOWANCE * factor,
        brt=BASE_BASIC_RATE_LIMIT * factor,
        hrt=BASE_HIGHER_RATE_LIMIT * factor,
        taper_start=BASE_PA_TAPER_START * factor
    )

def tax_due(gross: float, bands: TaxBands) -> float:
    if gross <= 0:
        return 0.0

    pa = bands.pa
    if gross > bands.taper_start:
        pa_reduction = max(0.0, (gross - bands.taper_start) / 2.0)
        pa = max(0.0, pa - pa_reduction)

    taxable = max(0.0, gross - pa)

    basic_band      = max(0.0, min(taxable, bands.brt - pa))
    higher_band     = max(0.0, min(max(0.0, taxable - basic_band), bands.hrt - bands.brt))
    additional_band = max(0.0, taxable - basic_band - higher_band)

    return basic_band*0.20 + higher_band*0.40 + additional_band*0.45

def net_from_gross(gross: float, bands: TaxBands) -> float:
    return gross - tax_due(gross, bands)

def gross_needed_for_net(net_target: float, bands: TaxBands) -> float:
    if net_target <= 0:
        return 0.0
    lo, hi = 0.0, 2_000_000.0
    for _ in range(60):
        mid = (lo+hi)/2.0
        net_mid = net_from_gross(mid, bands)
        if net_mid < net_target:
            lo = mid
        else:
            hi = mid
    return hi
