import numpy as np
from taxes import TaxBands, net_from_gross, gross_needed_for_net

def static_real_rule(portfolio: float, rule_pct: float, price_index: float, start_index: float) -> float:
    """
    Withdraw a constant *real* % of initial portfolio (3% rule). We implement as:
    initial_wd = rule_pct * initial_portfolio
    each year: withdrawal_nominal = initial_wd * (price_index / start_index)
    This function returns the *gross* withdrawal budget; taxes applied upstream.
    """
    # The function itself needs context (initial_wd). We'll compute that at sim start.
    raise NotImplementedError("Handled in simulation engine with stateful initial_wd.")

def guardrails(current_spend_gross: float, portfolio: float, start_pct: float,
               band: float, max_raise: float, max_cut: float,
               last_spend_gross: float, portfolio_start: float) -> float:
    """
    Guyton-Klinger simplified: if current withdrawal rate > start_pct*(1+band) => cut, if < start_pct*(1-band) => raise.
    Returns proposed new gross spend before tax.
    """
    wr = (last_spend_gross or 0.0) / max(portfolio, 1e-9)
    target = start_pct
    if wr > target * (1 + band):
        return max(0.0, last_spend_gross * (1 - max_cut))
    elif wr < target * (1 - band):
        return last_spend_gross * (1 + max_raise)
    else:
        return last_spend_gross  # stay the course

def tax_smart_gross_for_net(net_needed: float, bands: TaxBands) -> float:
    return gross_needed_for_net(net_needed, bands)

def apply_tax_withdrawal(gross: float, bands: TaxBands) -> float:
    return net_from_gross(gross, bands)
