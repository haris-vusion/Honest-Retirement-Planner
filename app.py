# app.py
import streamlit as st
import plotly.graph_objects as go
import numpy as np
import pandas as pd

from config import APP_NAME, DEFAULTS
from ui import inject_css, header, helptext
from returns_presets import PRESETS
from costs import project_costs, basket
from simulation import SimConfig, run_monte_carlo
from exporters import export_median_series, export_config
from taxes import SYSTEMS, indexed as index_tax, net_from_gross

# ------------- Page setup -------------
st.set_page_config(page_title=APP_NAME, page_icon="📈", layout="wide")
inject_css()
header(APP_NAME)

with st.expander("How this app works (30 seconds)"):
    st.write("""
**Plain English version:**
- We estimate **what your life will cost** each year by inflating every part of your budget (housing, food, energy, etc.).
- We simulate your portfolio in **today’s money** with a Monte Carlo model (thousands of futures).
- We include **income tax** for your country using simplified brackets that rise with inflation.
- Your **retirement income target** is the projected basket at each retirement year (in today’s money) — no manual sliders.
- Success = you meet that target for most of retirement **and** you don’t run out.
    """)

# ------------- Sidebar (inputs) -------------
st.sidebar.header("Your profile")
current_age = st.sidebar.number_input(
    "Your age", min_value=18, max_value=85, value=DEFAULTS["current_age"],
    help="How old you are today."
)
retire_age = st.sidebar.number_input(
    "When do you want to retire?", min_value=current_age+1, max_value=85, value=DEFAULTS["retire_age"],
    help="Pick the age you’d like to stop full-time work."
)
plan_end_age = st.sidebar.number_input(
    "Plan until age", min_value=retire_age+5, max_value=130, value=DEFAULTS["plan_end_age"],
    help="We simulate until this age. It’s your longevity buffer."
)

country = st.sidebar.selectbox(
    "Country for tax", list(SYSTEMS.keys()),
    index=list(SYSTEMS.keys()).index(DEFAULTS["country"]),
    help="We use a simplified version of your country’s tax brackets, indexed with inflation."
)

st.sidebar.header("Money today")
current_investable = st.sidebar.number_input(
    "Investable assets today", min_value=0, value=DEFAULTS["current_investable"], step=1000,
    help="Cash+investments that will fund retirement. Exclude your main home."
)
monthly_contrib = st.sidebar.number_input(
    "Monthly contribution", min_value=0, value=DEFAULTS["monthly_contrib"], step=50,
    help="How much you add each month before retirement."
)
contrib_growth = st.sidebar.slider(
    "Contribution growth (nominal, %/yr)", 0.0, 10.0, DEFAULTS["contrib_growth_nominal_pct"], 0.1,
    help="Rough annual pay rise or savings increase. Nominal = before inflation."
)

st.sidebar.header("Inflation")
cpi = st.sidebar.slider(
    "Headline inflation (%/yr)", 0.0, 10.0, DEFAULTS["headline_cpi"]*100, 0.1,
    help="We inflate prices by this rate."
)/100.0

st.sidebar.header("Expected returns")
preset_name = st.sidebar.selectbox(
    "Choose a preset (optional)", ["Custom"] + list(PRESETS.keys()),
    help="Quick-start estimates you can override."
)
if preset_name != "Custom":
    mu_default = PRESETS[preset_name]["real_mu"]
    vol_default = PRESETS[preset_name]["vol"]
else:
    mu_default, vol_default = DEFAULTS["exp_real_return"], DEFAULTS["volatility"]

exp_real_return = st.sidebar.number_input(
    "Expected real return (μ, per year)", value=float(mu_default), step=0.005, format="%.3f",
    help="Average return after inflation. Example: 0.05 = ~5% real per year."
)
volatility = st.sidebar.number_input(
    "Volatility (σ, per year)", value=float(vol_default), step=0.01, format="%.2f",
    help="How bumpy returns are. Higher = wider swings."
)
fees = st.sidebar.slider(
    "All-in fees (%/yr)", 0.0, 2.0, DEFAULTS["fees_annual"]*100, 0.05,
    help="Fund + platform + advice, combined."
)/100.0

st.sidebar.header("Simulation")
num_paths = st.sidebar.slider(
    "How many futures to simulate", 20, 1000, DEFAULTS["num_paths"], 20,
    help="More paths = smoother bands but slower. 2,000–5,000 is a good start."
)
seed = st.sidebar.number_input(
    "Random seed (-1 = random)", value=DEFAULTS["seed"],
    help="Set -1 for a fresh random run each time."
)

st.sidebar.header("Drawdown & success")
rule_choice = st.sidebar.selectbox(
    "Rule of thumb", ["3% real", "3.5% real", "4% real"], index=0,
    help="Rule-based starting spend as % of your pot (real)."
)
spending_policy = st.sidebar.selectbox(
    "How to set your retirement income",
    ["Meet target", "Rule only", "Lower of rule & target"],
    help="‘Meet target’ tries to fund your basket; ‘Rule only’ pays the % regardless; ‘Lower of’ is conservative."
)
legacy_mode = st.sidebar.selectbox(
    "Legacy", ["Spend to zero", "Preserve capital (real)"], index=0,
    help="Preserve capital keeps your initial pot intact in today’s money."
)
success_cover = st.sidebar.slider(
    "What counts as success? (% of retirement months you meet the target)",
    50, 100, 90, 5,
    help="Example: 90% means you meet your target income in at least 90% of retirement months and don’t run out."
)/100.0

# ------------- Costs & Target Path (automatic) -------------
st.markdown("### 1) Your future cost of living")
helptext("We project your basket from today all the way to your plan end age. That projection becomes your retirement income target (in today’s money).")

# Spend today (editable)
spend_today = DEFAULTS["spend_today"].copy()
cols = st.columns(3)
cats = list(spend_today.keys())
for i, cat in enumerate(cats):
    with cols[i % 3]:
        spend_today[cat] = st.number_input(
            f"{cat.capitalize()} (monthly, today’s money)",
            min_value=0, value=int(spend_today[cat]), step=25,
            help=f"How much you spend on {cat} each month today.",
            key=f"sp_{cat}"
        )

# Category drifts vs CPI
drifts = DEFAULTS["category_drifts"].copy()
with st.expander("Advanced: which things outpace inflation? (optional)"):
    cols2 = st.columns(3)
    for i, (cat, drift) in enumerate(drifts.items()):
        with cols2[i % 3]:
            drifts[cat] = st.number_input(
                f"{cat.capitalize()} drift (±%/yr vs CPI)",
                value=float(drift*100), step=0.1, format="%.1f",
                help=f"If {cat} tends to rise faster than CPI, use a positive number; if cheaper over time, negative.",
                key=f"dr_{cat}"
            )/100.0

years_to_retire = max(0, retire_age - current_age)
years_total = max(0, plan_end_age - current_age)

# Project to *plan end age* so we have a full target path
proj_full = project_costs(spend_today, cpi, drifts, years_total)
# At-retirement KPIs (year = years_to_retire)
b = basket(proj_full, years_to_retire)

# Calculate basket today (just sum the category inputs)
basket_today_monthly = sum(spend_today.values())
basket_today_annual = basket_today_monthly * 12

cols_kpi = st.columns(5)
cols_kpi[0].markdown(
    f"<div class='card'><div class='caption'>Basket today (monthly)</div>"
    f"<div class='kpi'>£{basket_today_monthly:,.0f}</div></div>", unsafe_allow_html=True)
cols_kpi[1].markdown(
    f"<div class='card'><div class='caption'>Basket today (annual)</div>"
    f"<div class='kpi'>£{basket_today_annual:,.0f}</div></div>", unsafe_allow_html=True)
cols_kpi[2].markdown(
    f"<div class='card'><div class='caption'>Monthly basket at retirement (nominal)</div>"
    f"<div class='kpi'>£{b['monthly_nominal']:,.0f}</div></div>", unsafe_allow_html=True)
cols_kpi[3].markdown(
    f"<div class='card'><div class='caption'>Monthly basket in today’s money (at retirement)</div>"
    f"<div class='kpi'>£{b['monthly_real_today']:,.0f}</div></div>", unsafe_allow_html=True)
cols_kpi[4].markdown(
    f"<div class='card'><div class='caption'>Annual basket (nominal, at retirement)</div>"
    f"<div class='kpi'>£{b['annual_nominal']:,.0f}</div></div>", unsafe_allow_html=True)

# Preview chart to *retirement*
figC = go.Figure()
for cat in ["housing", "food", "energy"]:
    sub = proj_full[(proj_full["category"] == cat) & (proj_full["year"] <= years_to_retire)]
    figC.add_trace(go.Scatter(x=sub["year"], y=sub["annual_nominal"], mode="lines", name=f"{cat} (annual, nominal)"))
figC.update_layout(
    title="Selected categories up to retirement (annual nominal)",
    xaxis_title="Years from now", yaxis_title="Per year",
    hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30)
)
st.plotly_chart(figC, use_container_width=True)

# Build the dynamic *monthly real* target series for the full sim horizon
# Step 1: compute a year-by-year series of annual real (today’s money)
annual_real_by_year = proj_full.groupby("year")["annual_real_today"].sum().reindex(range(years_total+1), fill_value=0.0).values
# Step 2: expand to months (piecewise-constant within each year)
months_total = years_total * 12
target_monthly_real_by_month = np.zeros(months_total + 1, dtype=float)
for y in range(years_total+1):
    start_m = y * 12
    end_m   = min(months_total, start_m + 12)
    target_monthly_real_by_month[start_m:end_m] = annual_real_by_year[y] / 12.0
# Step 3: zero out pre-retirement months (we only target income after retirement)
retire_m = years_to_retire * 12
target_monthly_real_by_month[:retire_m] = 0.0

# ------------- Run simulation (auto) -------------
st.markdown("### 2) Retirement odds & income")
helptext("We simulate many possible futures (Monte Carlo). All values below are in **today’s money**.")

cfg = SimConfig(
    current_age=current_age,
    retire_age=retire_age,
    plan_end_age=plan_end_age,
    current_investable=current_investable,
    monthly_contrib=monthly_contrib,
    contrib_growth_nominal_pct=contrib_growth,
    exp_real_return=exp_real_return,
    volatility=volatility,
    fees_annual=fees,
    cpi=cpi,
    target_monthly_real_by_month=target_monthly_real_by_month,
    withdrawal_rule=rule_choice,
    legacy_mode=legacy_mode,
    spending_policy=spending_policy,
    country=country,
    num_paths=num_paths,
    seed=None if seed == -1 else seed,
    success_cover_pct=success_cover
)

@st.cache_data(show_spinner=False)
def run_cached(cfg_dict):
    cfg_obj = SimConfig(**cfg_dict)
    return run_monte_carlo(cfg_obj)

with st.spinner("Simulating futures…"):
    summary, detail = run_cached(cfg.__dict__)

# ------------- KPIs (rule-based income uses wealth *at retirement*) -------------
retire_idx = int((retire_age - current_age) * 12)
rule_map = {"3% real": 0.03, "3.5% real": 0.035, "4% real": 0.04}
rule_pct = rule_map[rule_choice]
wealth_at_retire = float(summary["wealth_p50"][retire_idx])
rule_start_income_gross_real = wealth_at_retire * rule_pct

# After-tax version using retirement-year tax brackets
tax_factor = (1 + cpi) ** max(0, (retire_age - current_age))
sys_at_retire = index_tax(SYSTEMS[country], tax_factor)
rule_start_income_net_real = net_from_gross(rule_start_income_gross_real, sys_at_retire)

basket_nominal_retire = float(b["annual_nominal"])

c1, c2, c3 = st.columns(3)
c1.markdown(
    f"<div class='card'><div class='caption'>Success probability "
    f"(meets target ≥ {int(success_cover*100)}% of retirement months)</div>"
    f"<div class='kpi'>{summary['success_rate']:.1f}%</div></div>",
    unsafe_allow_html=True
)
c2.markdown(
    f"<div class='card'><div class='caption'>Rule-based starting income (at retirement)</div>"
    f"<div class='kpi'>£{rule_start_income_gross_real:,.0f}/yr</div>"
    f"<div class='caption'>Real, before tax • {rule_choice}</div></div>",
    unsafe_allow_html=True
)
c3.markdown(
    f"<div class='card'><div class='caption'>Basket at retirement (nominal)</div>"
    f"<div class='kpi'>£{basket_nominal_retire:,.0f}/yr</div>"
    f"<div class='caption'>This is the sticker price in your retirement year</div></div>",
    unsafe_allow_html=True
)

# (keep this explanatory caption below if you like)
st.caption(f"After-tax rule-based starting income (real): £{rule_start_income_net_real:,.0f}/yr, using {country} tax at retirement-year brackets.")

# ------------- Charts -------------
# Wealth bands
figW = go.Figure()
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p50"], mode="lines", name="Median wealth"))
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p95"], mode="lines", name="Wealth p95", line=dict(dash="dot")))
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p5"],  mode="lines", name="Wealth p5",  line=dict(dash="dot"), fill="tonexty"))
figW.add_vline(x=retire_age, line_dash="dash", line_color="green")
figW.update_layout(
    title="Portfolio wealth (real)", xaxis_title="Age", yaxis_title="£ (today’s money)",
    hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30)
)
st.plotly_chart(figW, use_container_width=True)

# Income bands + dynamic target path
figI = go.Figure()
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p50"], mode="lines", name="Median net income (annual)"))
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p95"], mode="lines", name="p95", line=dict(dash="dot")))
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p5"],  mode="lines", name="p5",  line=dict(dash="dot"), fill="tonexty"))

# Build a visible target path (annual, real) from the series the sim used
target_annual_series = summary["target_annual_real_series"]
target_line = np.full_like(target_annual_series, fill_value=np.nan, dtype=float)
target_line[retire_idx:] = target_annual_series[retire_idx:]
figI.add_trace(go.Scatter(x=summary["ages"], y=target_line, mode="lines", name="Target income path", line=dict(dash="dash")))

figI.add_vline(x=retire_age, line_dash="dash", line_color="green")
figI.update_layout(
    title="Retirement income (after tax, real)", xaxis_title="Age", yaxis_title="£ per year (today’s money)",
    hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30)
)
st.plotly_chart(figI, use_container_width=True)

st.markdown("**How to read this:** The dashed line is your target (what life costs each year, in today’s money). If the median line sits below it for long stretches, you’ll feel a squeeze.")

# ------------- Quick what-ifs -------------
st.markdown("### 3) Quick what-ifs")
a, b2, c = st.columns(3)
more_saving = a.slider("Add to monthly saving (now)", 0, 2000, 200, 50)
retire_later = b2.slider("Retire later (months)", 0, 60, 12, 6)
cut_target = c.slider("Cut target spend at retirement (%)", 0, 50, 10, 1)

if st.button("Run what-ifs"):
    from simulation import run_monte_carlo as rmc
    results = {}
    # a) more saving
    cfg_a = SimConfig(**{**cfg.__dict__, "monthly_contrib": cfg.monthly_contrib + more_saving})
    sA,_ = rmc(cfg_a); results["More saving"] = sA["success_rate"]
    # b) retire later
    cfg_b = SimConfig(**{**cfg.__dict__, "retire_age": cfg.retire_age + retire_later/12.0})
    sB,_ = rmc(cfg_b); results["Retire later"] = sB["success_rate"]
    # c) cut spend (scale the whole target path from retirement onward)
    scaled_target = cfg.target_monthly_real_by_month.copy()
    scaled_target[retire_m:] *= (1 - cut_target/100.0)
    cfg_c = SimConfig(**{**cfg.__dict__, "target_monthly_real_by_month": scaled_target})
    sC,_ = rmc(cfg_c); results["Spend less"] = sC["success_rate"]
    st.write({k: f"{v:.1f}%" for k,v in results.items()})

# ------------- Export -------------
st.markdown("### 4) Export")
name_csv, data_csv = export_median_series(summary)
st.download_button("⬇️ Download median series (CSV)", data_csv, file_name=name_csv, mime="text/csv")
name_cfg, data_cfg = export_config(cfg.__dict__)
st.download_button("⬇️ Download your configuration (JSON)", data_cfg, file_name=name_cfg, mime="application/json")

st.markdown("---")
st.caption("This app uses simplified tax systems and long-run return estimates. It’s a planning tool, not personal advice.")