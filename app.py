import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd

from config import APP_NAME, DEFAULTS
from ui import inject_css, header, help_tip, pill, download_button_bytes
from costs import project_category_costs, basket_for_year
from simulation import SimConfig, run_monte_carlo
from exporters import export_cashflows_csv, export_config_json

st.set_page_config(page_title=APP_NAME, page_icon="📈", layout="wide")
inject_css()
header(APP_NAME)

with st.expander("How this works (read me, it’s quick)"):
    st.write("""
- We forecast **your cost of living at retirement** by inflating a category basket (rent, food, energy, etc.).
- We simulate **real (after-inflation) investment returns** with Monte Carlo, including sequence risk.
- We model **UK tax bands** with personal allowance taper and index them with inflation.
- You choose whether to **preserve capital (legacy)** or **spend to zero** by a target age.
- We report everything in **today’s pounds** (plus nominal when helpful).
""")

# --- Sidebar: Inputs ---
st.sidebar.header("Your Profile & Assumptions")

colA, colB = st.sidebar.columns(2)
start_age = colA.number_input("Your age", min_value=18, max_value=80, value=DEFAULTS["start_age"])
retire_age = colB.number_input("Target retire age", min_value=start_age+1, max_value=85, value=DEFAULTS["retire_age"])
end_age = st.sidebar.number_input("Plan until age", min_value=retire_age+5, max_value=105, value=DEFAULTS["end_age"])

st.sidebar.markdown("---")
st.sidebar.subheader("Finances (today)")
current_investable = st.sidebar.number_input("Investable assets (£)", min_value=0, value=DEFAULTS["current_investable"], step=1000)
monthly_contrib = st.sidebar.number_input("Monthly contribution (£)", min_value=0, value=DEFAULTS["monthly_contribution"], step=50)
contrib_growth = st.sidebar.slider("Contribution growth (nominal, %/yr)", 0.0, 10.0, DEFAULTS["contribution_growth_pct"], 0.1)

st.sidebar.markdown("---")
st.sidebar.subheader("Asset Mix & Returns (real)")
equity_alloc = st.sidebar.slider("Equity allocation", 0.0, 1.0, DEFAULTS["equity_alloc"], 0.05)
bond_alloc = 1.0 - equity_alloc
col1, col2 = st.sidebar.columns(2)
equity_real_return = col1.number_input("Equity real return (μ)", value=DEFAULTS["equity_real_return"], step=0.001, format="%.3f")
equity_vol = col2.number_input("Equity volatility (σ)", value=DEFAULTS["equity_vol"], step=0.01, format="%.2f")
col3, col4 = st.sidebar.columns(2)
bond_real_return = col3.number_input("Bond real return (μ)", value=DEFAULTS["bond_real_return"], step=0.001, format="%.3f")
bond_vol = col4.number_input("Bond volatility (σ)", value=DEFAULTS["bond_vol"], step=0.01, format="%.2f")
corr = st.sidebar.slider("Equity/Bond correlation", -0.9, 0.9, DEFAULTS["corr_equity_bond"], 0.1)
fees_annual = st.sidebar.slider("All-in fees (%/yr)", 0.0, 2.0, DEFAULTS["fees_annual"]*100, 0.05) / 100.0

st.sidebar.markdown("---")
st.sidebar.subheader("Inflation")
cpi = st.sidebar.slider("Headline CPI (%/yr)", 0.0, 10.0, DEFAULTS["cpi"]*100, 0.1) / 100.0

st.sidebar.markdown("---")
st.sidebar.subheader("Simulation")
num_paths = st.sidebar.slider("Monte Carlo paths", 500, 15000, DEFAULTS["num_paths"], 500)
seed = st.sidebar.number_input("Random seed (−1 for random)", value=DEFAULTS["seed"])

st.sidebar.markdown("---")
st.sidebar.subheader("Retirement Style")
colX, colY = st.sidebar.columns(2)
headline_rule = colX.selectbox("Rule of thumb", ["3% real", "3.5% real", "4% real"], index=0)
preserve_capital = colY.selectbox("Legacy goal", ["Spend to zero", "Preserve capital (real)"], index=0) == "Preserve capital (real)"

st.sidebar.info("Tip: Start conservative. You can always loosen later.")

# --- Basket (Costs) ---
st.markdown("### 1) Cost-of-Living Forecaster")
help_tip("We inflate each category separately to estimate what life will actually cost when you retire.")

spend_today = DEFAULTS["spend_today"].copy()
with st.expander("Adjust your monthly spending today (in £)", expanded=False):
    grid_cols = st.columns(4)
    cats = list(spend_today.keys())
    for i, cat in enumerate(cats):
        with grid_cols[i % 4]:
            spend_today[cat] = st.number_input(f"{cat.capitalize()}", min_value=0, value=int(spend_today[cat]), step=10, key=f"sp_{cat}")

drifts = DEFAULTS["category_drifts"].copy()
with st.expander("Advanced: category inflation drifts vs CPI", expanded=False):
    grid = st.columns(4)
    for i, (cat, drift) in enumerate(drifts.items()):
        with grid[i % 4]:
            drifts[cat] = st.number_input(f"{cat.capitalize()} drift (±%/yr)", value=float(drift*100), step=0.1, format="%.1f", key=f"dr_{cat}")/100.0

years_to_retire = max(0, (retire_age - start_age))
proj_df = project_category_costs(spend_today, cpi, drifts, years_to_retire)
basket_retire = basket_for_year(proj_df, years_to_retire)
colA, colB, colC, colD = st.columns(4)
colA.metric("Monthly basket @ retirement (nominal)", f"£{basket_retire['monthly_nominal']:,.0f}")
colB.metric("Monthly basket in today's £", f"£{basket_retire['monthly_real_today£']:,.0f}")
colC.metric("Annual basket (nominal)", f"£{basket_retire['annual_nominal']:,.0f}")
colD.metric("Annual basket in today's £", f"£{basket_retire['annual_real_today£']:,.0f}")

# Simple chart of 3 big categories
topcats = ["rent", "food", "energy"]
fig = go.Figure()
for cat in topcats:
    sub = proj_df[proj_df["category"] == cat]
    fig.add_trace(go.Scatter(x=sub["year"], y=sub["annual_nominal"], mode="lines", name=f"{cat} (annual, nominal)"))
fig.update_layout(title="Selected categories — annual nominal cost to retirement", xaxis_title="Years from now", yaxis_title="£", hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30))
st.plotly_chart(fig, use_container_width=True)

# --- Monte Carlo Engine ---
st.markdown("### 2) Retirement Odds & Income Paths")
help_tip("We simulate your portfolio monthly in **real** terms, apply fees, retirement withdrawals, and UK tax. Success = retire on time **and** finish with ≥ £0.")

cfg = SimConfig(
    start_age=start_age,
    retire_age=retire_age,
    end_age=end_age,
    monthly_contribution=monthly_contrib,
    contribution_growth_pct=contrib_growth,
    current_investable=current_investable,
    equity_alloc=equity_alloc,
    bond_alloc=bond_alloc,
    equity_real_return=equity_real_return,
    equity_vol=equity_vol,
    bond_real_return=bond_real_return,
    bond_vol=bond_vol,
    corr_equity_bond=corr,
    fees_annual=fees_annual,
    cpi=cpi,
    category_basket_annual_today=basket_retire["annual_real_today£"],
    preserve_capital=preserve_capital,
    headline_rule=headline_rule,
    guardrails_cfg=DEFAULTS["guardrails"],
    num_paths=num_paths,
    seed=(None if seed == -1 else seed),
    uk_tax=True
)

with st.spinner("Running simulations…"):
    summary, series = run_monte_carlo(cfg)

# KPIs
col1, col2, col3 = st.columns(3)
col1.markdown("<div class='card'><div class='caption'>Success probability</div><div class='kpi'>{:.1f}%</div><div class='caption'>Meet plan & finish ≥ £0</div></div>".format(summary["success_rate"]), unsafe_allow_html=True)
col2.markdown("<div class='card'><div class='caption'>Median net income at 1st retirement year</div><div class='kpi'>£{:,.0f}/yr</div><div class='caption'>Real, after tax</div></div>".format(float(summary["wd_p50"][int((retire_age-start_age)*12)]*12)), unsafe_allow_html=True)
col3.markdown("<div class='card'><div class='caption'>3% rule on your pot today</div><div class='kpi'>£{:,.0f}/yr</div><div class='caption'>Real, before taxes</div></div>".format(current_investable*0.03), unsafe_allow_html=True)

# Wealth bands
figW = go.Figure()
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p50"], mode="lines", name="Median wealth"))
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p95"], mode="lines", name="Wealth p95", line=dict(dash="dot")))
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p5"],  mode="lines", name="Wealth p5",  line=dict(dash="dot"), fill="tonexty"))
figW.update_layout(title="Portfolio wealth (real £) — distribution", xaxis_title="Age", yaxis_title="£", hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30))
st.plotly_chart(figW, use_container_width=True)

# Withdrawal bands
figI = go.Figure()
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p50"]*12, mode="lines", name="Median net income (yr)"))
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p95"]*12, mode="lines", name="p95", line=dict(dash="dot")))
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p5"]*12,  mode="lines", name="p5", line=dict(dash="dot"), fill="tonexty"))
figI.add_vline(x=retire_age, line_dash="dash", line_color="green")
figI.update_layout(title="Net retirement income (after tax, real £/yr)", xaxis_title="Age", yaxis_title="£/yr", hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30))
st.plotly_chart(figI, use_container_width=True)

st.markdown("**What the bands mean:** The shaded area shows good/bad luck ranges. If your plan only works in the top slice, it’s fragile. Be smug-proof.")

# --- Action levers ---
st.markdown("### 3) What moves the needle?")
help_tip("Tweak one thing at a time and watch success % jump—or not.")

a1, a2, a3 = st.columns(3)
bump_contrib = a1.slider("Increase monthly contribution by (£)", 0, 2000, 200, 50)
delay_retire = a2.slider("Delay retirement (months)", 0, 60, 12, 6)
cut_spend = a3.slider("Reduce basket at retirement (%)", 0, 50, 10, 1)

if st.button("Recalculate quick scenarios"):
    quick_cfgs = []
    # +contrib
    quick_cfgs.append(("More saving", dict(monthly_contribution=monthly_contrib + bump_contrib)))
    # delay
    quick_cfgs.append(("Retire later", dict(retire_age=retire_age + delay_retire/12.0)))
    # cut spend
    reduced_basket = basket_retire["annual_real_today£"] * (1 - cut_spend/100.0)
    quick_cfgs.append(("Spend less", dict(category_basket_annual_today=reduced_basket)))

    res = []
    from simulation import SimConfig as SC, run_monte_carlo as rmc
    for name, edit in quick_cfgs:
        cfg2 = SC(**{**cfg.__dict__, **edit})
        s2, _ = rmc(cfg2)
        res.append((name, s2["success_rate"]))

    st.write({name: f"{sr:.1f}%" for name, sr in res})

# --- Report & export ---
st.markdown("### 4) Export")
cf_name, cf_bytes = export_cashflows_csv(series)
download_button_bytes(cf_name, cf_bytes, "text/csv", "⬇️ Download cashflows (CSV)")

cfg_name, cfg_bytes = export_config_json(cfg)
download_button_bytes(cfg_name, cfg_bytes, "application/json", "⬇️ Download configuration (JSON)")

st.markdown("---")
st.caption("No fairy tales. Everything above is in **today’s pounds**, with UK tax and category inflation built in. Change inputs on the left and rerun instantly.")
