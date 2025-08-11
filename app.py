import streamlit as st
import plotly.graph_objects as go
import numpy as np

from config import APP_NAME, DEFAULTS
from ui import inject_css, header, helptext
from returns_presets import PRESETS
from costs import project_costs, basket
from simulation import SimConfig, run_monte_carlo
from exporters import export_median_series, export_config
from taxes import SYSTEMS

st.set_page_config(page_title=APP_NAME, page_icon="📈", layout="wide")
inject_css()
header(APP_NAME)

with st.expander("How this app works (30 seconds)"):
    st.write("""
**Plain English version:**
- We estimate **what your life will cost** when you retire by inflating each part of your budget (housing, food, energy, etc.).
- We simulate your portfolio in **today’s money** using a Monte Carlo model (thousands of possible futures).
- We include **income tax** for your chosen country using simplified brackets that rise with inflation.
- You can choose a drawdown style: **3% rule** (or 3.5%/4%), and whether you **spend to zero** or **preserve your capital** after inflation.
- We show your **odds of success**, your **income bands**, and your **wealth bands**. No nonsense, no “£2m in 2065” without context.
    """)

# ---------------- Sidebar (inputs) ----------------
st.sidebar.header("Your profile")
current_age = st.sidebar.number_input("Your age", min_value=18, max_value=85, value=DEFAULTS["current_age"],
    help="How old you are today. We use this with your retirement age to set the timeline.")
retire_age = st.sidebar.number_input("When do you want to retire?", min_value=current_age+1, max_value=85, value=DEFAULTS["retire_age"],
    help="Pick the age you’d like to stop full-time work.")
plan_end_age = st.sidebar.number_input("Plan until age", min_value=retire_age+5, max_value=105, value=DEFAULTS["plan_end_age"],
    help="We simulate until this age. It’s your longevity buffer.")

country = st.sidebar.selectbox("Country for tax", list(SYSTEMS.keys()), index=list(SYSTEMS.keys()).index(DEFAULTS["country"]),
    help="We use a simplified version of your country’s tax brackets. Thresholds rise with inflation each year.")

st.sidebar.header("Money today")
current_investable = st.sidebar.number_input("Investable assets today", min_value=0, value=DEFAULTS["current_investable"], step=1000,
    help="Cash+investments that will fund retirement. Exclude your primary home for now.")
monthly_contrib = st.sidebar.number_input("Monthly contribution", min_value=0, value=DEFAULTS["monthly_contrib"], step=50,
    help="How much you add each month before retirement.")
contrib_growth = st.sidebar.slider("Contribution growth (nominal, %/yr)", 0.0, 10.0, DEFAULTS["contrib_growth_nominal_pct"], 0.1,
    help="Rough annual pay rise or savings increase. Nominal means before inflation.")

st.sidebar.header("Inflation")
cpi = st.sidebar.slider("Headline inflation (%/yr)", 0.0, 10.0, DEFAULTS["headline_cpi"]*100, 0.1, help="We inflate prices by this rate.")/100.0

st.sidebar.header("Expected returns")
preset_name = st.sidebar.selectbox("Choose a preset (optional)", ["Custom"] + list(PRESETS.keys()), help="Quick-start estimates you can override.")
if preset_name != "Custom":
    mu_default = PRESETS[preset_name]["real_mu"]
    vol_default = PRESETS[preset_name]["vol"]
else:
    mu_default, vol_default = DEFAULTS["exp_real_return"], DEFAULTS["volatility"]

exp_real_return = st.sidebar.number_input("Expected real return (μ, per year)", value=float(mu_default), step=0.005, format="%.3f",
    help="Average return after inflation. Example: 0.05 means ~5% above inflation per year.")
volatility = st.sidebar.number_input("Volatility (σ, per year)", value=float(vol_default), step=0.01, format="%.2f",
    help="How bumpy returns are. Higher = wider swings, bigger sequence risk.")
fees = st.sidebar.slider("All-in fees (%/yr)", 0.0, 2.0, DEFAULTS["fees_annual"]*100, 0.05,
    help="Fund + platform + advice. Lower is better!")/100.0

st.sidebar.header("Simulation")
num_paths = st.sidebar.slider("How many futures to simulate", 500, 20000, DEFAULTS["num_paths"], 500,
    help="More paths = smoother bands but slower. Start with 2,000–5,000.")
seed = st.sidebar.number_input("Random seed (-1 = random)", value=DEFAULTS["seed"], help="Set -1 for a fresh random run.")

st.sidebar.header("Drawdown style")
rule_choice = st.sidebar.selectbox("Rule of thumb", ["3% real", "3.5% real", "4% real"], index=["3% real","3.5% real","4% real"].index(DEFAULTS["withdrawal_rule"]),
    help="This sets a ‘safe-ish’ starting spend as a % of your pot, adjusted for inflation.")
legacy_mode = st.sidebar.selectbox("Legacy", ["Spend to zero", "Preserve capital (real)"], index=["Spend to zero","Preserve capital (real)"].index(DEFAULTS["legacy_mode"]),
    help="Spend to zero: aim to use up your pot by plan end. Preserve capital: keep your initial pot intact in *today’s money*.")

# ---------------- Costs (simple English) ----------------
st.markdown("### 1) Your future cost of living")
helptext("We project each part of your budget to your retirement date. You can tweak the numbers; they’re just starting points.")

spend_today = DEFAULTS["spend_today"].copy()
cols = st.columns(3)
cats = list(spend_today.keys())
for i, cat in enumerate(cats):
    with cols[i % 3]:
        spend_today[cat] = st.number_input(
            f"{cat.capitalize()} (monthly, today’s money)",
            min_value=0, value=int(spend_today[cat]), step=25,
            help=f"How much you spend on {cat} each month in today’s money.",
            key=f"sp_{cat}"
        )

drifts = DEFAULTS["category_drifts"].copy()
with st.expander("Advanced: which things outpace inflation? (optional)"):
    cols2 = st.columns(3)
    for i, (cat, drift) in enumerate(drifts.items()):
        with cols2[i % 3]:
            drifts[cat] = st.number_input(
                f"{cat.capitalize()} drift (±%/yr vs CPI)",
                value=float(drift*100), step=0.1, format="%.1f",
                help=f"If {cat} tends to rise faster than CPI, put a positive number. If it gets cheaper over time, use negative.",
                key=f"dr_{cat}"
            )/100.0

years_to_retire = max(0, retire_age - current_age)
from costs import project_costs, basket
proj = project_costs(spend_today, cpi, drifts, years_to_retire)
b = basket(proj, years_to_retire)

cols_kpi = st.columns(4)
cols_kpi[0].markdown(f"<div class='card'><div class='caption'>Monthly basket at retirement (nominal)</div><div class='kpi'>£{b['monthly_nominal']:,.0f}</div></div>", unsafe_allow_html=True)
cols_kpi[1].markdown(f"<div class='card'><div class='caption'>Monthly basket in today’s money</div><div class='kpi'>£{b['monthly_real_today']:,.0f}</div></div>", unsafe_allow_html=True)
cols_kpi[2].markdown(f"<div class='card'><div class='caption'>Annual basket (nominal)</div><div class='kpi'>£{b['annual_nominal']:,.0f}</div></div>", unsafe_allow_html=True)
cols_kpi[3].markdown(f"<div class='card'><div class='caption'>Annual basket in today’s money</div><div class='kpi'>£{b['annual_real_today']:,.0f}</div></div>", unsafe_allow_html=True)

# Mini chart of 3 categories
figC = go.Figure()
for cat in ["housing", "food", "energy"]:
    sub = proj[proj["category"] == cat]
    figC.add_trace(go.Scatter(x=sub["year"], y=sub["annual_nominal"], mode="lines", name=f"{cat} (annual, nominal)"))
figC.update_layout(title="Selected categories up to retirement (annual nominal)", xaxis_title="Years from now", yaxis_title="Per year", hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30))
st.plotly_chart(figC, use_container_width=True)

# ---------------- Run simulation (on click) ----------------
st.markdown("### 2) Retirement odds & income")
helptext("We run many futures (Monte Carlo). The shaded bands show best/worst luck ranges, in **today’s money**.")

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
    annual_spend_target_real_today=b["annual_real_today"],
    withdrawal_rule=rule_choice,
    legacy_mode=legacy_mode,
    country=country,
    num_paths=num_paths,
    seed=None if seed == -1 else seed
)

@st.cache_data(show_spinner=False)
def run_cached(cfg_dict):
    cfg_obj = SimConfig(**cfg_dict)
    return run_monte_carlo(cfg_obj)

run = st.button("Run simulation", type="primary")
if not run:
    st.info("Set your inputs, then click **Run simulation**.")
    st.stop()

with st.spinner("Simulating futures…"):
    summary, detail = run_cached(cfg.__dict__)

# KPIs
c1,c2,c3 = st.columns(3)
c1.markdown(f"<div class='card'><div class='caption'>Success probability</div><div class='kpi'>{summary['success_rate']:.1f}%</div><div class='caption'>Meet plan & finish ≥ 0</div></div>", unsafe_allow_html=True)
rule_map = {"3% real":0.03,"3.5% real":0.035,"4% real":0.04}
c2.markdown(f"<div class='card'><div class='caption'>Rule-based starting income</div><div class='kpi'>£{current_investable*rule_map[rule_choice]:,.0f}/yr</div><div class='caption'>Real, before tax</div></div>", unsafe_allow_html=True)
c3.markdown(f"<div class='card'><div class='caption'>Basket at retirement (real)</div><div class='kpi'>£{b['annual_real_today']:,.0f}/yr</div><div class='caption'>Target net spend</div></div>", unsafe_allow_html=True)

# Wealth bands
figW = go.Figure()
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p50"], mode="lines", name="Median wealth"))
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p95"], mode="lines", name="Wealth p95", line=dict(dash="dot")))
figW.add_trace(go.Scatter(x=summary["ages"], y=summary["wealth_p5"],  mode="lines", name="Wealth p5",  line=dict(dash="dot"), fill="tonexty"))
figW.add_vline(x=retire_age, line_dash="dash", line_color="green")
figW.update_layout(title="Portfolio wealth (real)", xaxis_title="Age", yaxis_title="£ (today’s money)", hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30))
st.plotly_chart(figW, use_container_width=True)

# Income bands
figI = go.Figure()
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p50"], mode="lines", name="Median net income (annual)"))
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p95"], mode="lines", name="p95", line=dict(dash="dot")))
figI.add_trace(go.Scatter(x=summary["ages"], y=summary["wd_p5"],  mode="lines", name="p5",  line=dict(dash="dot"), fill="tonexty"))
figI.add_vline(x=retire_age, line_dash="dash", line_color="green")
figI.update_layout(title="Retirement income (after tax, real)", xaxis_title="Age", yaxis_title="£ per year (today’s money)", hovermode="x unified", margin=dict(l=30,r=20,t=60,b=30))
st.plotly_chart(figI, use_container_width=True)

st.markdown("**How to read this:** If the plan only works near the top dashed line, it’s fragile. To improve odds, try: save a bit more, retire a bit later, or reduce the target basket.")

# Levers
st.markdown("### 3) Quick what-ifs")
a,b,c = st.columns(3)
more_saving = a.slider("Add to monthly saving (now)", 0, 2000, 200, 50)
retire_later = b.slider("Retire later (months)", 0, 60, 12, 6)
cut_target = c.slider("Cut target spend at retirement (%)", 0, 50, 10, 1)

if st.button("Run what-ifs"):
    from simulation import SimConfig, run_monte_carlo
    results = {}
    # a) more saving
    cfg_a = SimConfig(**{**cfg.__dict__, "monthly_contrib": cfg.monthly_contrib + more_saving})
    sA,_ = run_monte_carlo(cfg_a); results["More saving"] = sA["success_rate"]
    # b) retire later
    cfg_b = SimConfig(**{**cfg.__dict__, "retire_age": cfg.retire_age + retire_later/12.0})
    sB,_ = run_monte_carlo(cfg_b); results["Retire later"] = sB["success_rate"]
    # c) cut spend
    cfg_c = SimConfig(**{**cfg.__dict__, "annual_spend_target_real_today": cfg.annual_spend_target_real_today*(1-cut_target/100.0)})
    sC,_ = run_monte_carlo(cfg_c); results["Spend less"] = sC["success_rate"]
    st.write({k: f"{v:.1f}%" for k,v in results.items()})

# Export
st.markdown("### 4) Export")
from exporters import export_median_series, export_config
name_csv, data_csv = export_median_series(summary)
st.download_button("⬇️ Download median series (CSV)", data_csv, file_name=name_csv, mime="text/csv")
name_cfg, data_cfg = export_config(cfg.__dict__)
st.download_button("⬇️ Download your configuration (JSON)", data_cfg, file_name=name_cfg, mime="application/json")

st.markdown("---")
st.caption("This app uses simplified tax systems and long-run return estimates. It’s a planning tool, not personal advice.")
