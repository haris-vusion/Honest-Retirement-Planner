import streamlit as st
import plotly.graph_objects as go
import pandas as pd

from config import APP_NAME, DEFAULTS, CURRENCIES
from ui import inject_css, app_header, step_header, nav_buttons, run_button, small_help
from costs import project_costs, summarize_year
from tax_models import default_tax_spec, spec_to_df, df_to_spec
from simulation import SimConfig, run_monte_carlo
from exporters import export_config, export_series_csv

st.set_page_config(page_title=APP_NAME, page_icon="🧭", layout="wide")
inject_css()
app_header(APP_NAME, "Step-by-step planner. Simple English. No fairy tales.")

# --- session state bootstrap ---
if "step" not in st.session_state:
    st.session_state.step = 1
if "inputs" not in st.session_state:
    st.session_state.inputs = DEFAULTS.copy()

def currency_symbol():
    return CURRENCIES.get(st.session_state.inputs["country"], "¤")

def next_step():
    st.session_state.step += 1

def prev_step():
    st.session_state.step = max(1, st.session_state.step - 1)

# ---------------------- STEP 1: Country & Ages ----------------------
if st.session_state.step == 1:
    step_header(1, "Where are you and when do you want to retire?",
                "We use your country to load local tax brackets. You can tweak them later.")
    cols = st.columns(2)
    country = cols[0].selectbox("Country", ["UK","USA","France","Germany","Australia","Custom"],
                                index=["UK","USA","France","Germany","Australia","Custom"].index(st.session_state.inputs["country"]))
    st.session_state.inputs["country"] = country

    age_now = cols[1].number_input("Your age today", min_value=18, max_value=80, value=st.session_state.inputs["age_now"])
    retire_age = st.number_input("Target retirement age", min_value=age_now+1, max_value=85, value=st.session_state.inputs["retire_age"])
    plan_until_age = st.number_input("Plan until age (longevity buffer)", min_value=retire_age+5, max_value=105, value=st.session_state.inputs["plan_until_age"])

    st.session_state.inputs.update({"age_now": age_now, "retire_age": retire_age, "plan_until_age": plan_until_age})
    small_help("Tip: choose a conservative 'plan until' age — outliving your money is worse than leaving extra behind.")

    b, n = nav_buttons()
    if b: prev_step()
    if n: next_step()

# ---------------------- STEP 2: Money today ----------------------
elif st.session_state.step == 2:
    step_header(2, "What do you have now, and what can you save?",
                "We use these numbers to grow your pot until retirement. All amounts are in your local currency.")
    sym = currency_symbol()
    cols = st.columns(3)
    assets_now = cols[0].number_input(f"Investable assets now ({sym})", min_value=0, value=int(st.session_state.inputs["assets_now"]), step=1000)
    contrib = cols[1].number_input(f"Monthly contribution ({sym})", min_value=0, value=int(st.session_state.inputs["monthly_contrib"]), step=50)
    contrib_growth = cols[2].slider("How fast your contributions grow each year (nominal %)", 0.0, 10.0, float(st.session_state.inputs["contrib_growth_pct"]), 0.1)
    st.session_state.inputs.update({"assets_now": assets_now, "monthly_contrib": contrib, "contrib_growth_pct": contrib_growth})

    b, n = nav_buttons()
    if b: prev_step()
    if n: next_step()

# ---------------------- STEP 3: Cost of living ----------------------
elif st.session_state.step == 3:
    step_header(3, "What does your life cost?",
                "Tell us your typical monthly spending today. We’ll project it to your retirement date by inflating each category separately.")

    sym = currency_symbol()
    basket = st.session_state.inputs["basket_today"].copy()
    drift = st.session_state.inputs["drifts"].copy()
    cols = st.columns(4)
    keys = list(basket.keys())
    for i, k in enumerate(keys):
        with cols[i % 4]:
            basket[k] = st.number_input(f"{k.replace('_',' ').title()} ({sym}/mo)", min_value=0, value=int(basket[k]), step=10)
    st.session_state.inputs["basket_today"] = basket

    st.markdown("**Inflation assumptions**")
    cpi = st.slider("Headline CPI (average % per year)", 0.0, 10.0, float(st.session_state.inputs["cpi"]), 0.1)
    with st.expander("Advanced: category drifts relative to CPI (e.g., rent often runs hotter than CPI)", expanded=False):
        cols2 = st.columns(4)
        for i, k in enumerate(drift.keys()):
            with cols2[i % 4]:
                drift[k] = st.number_input(f"{k.replace('_',' ').title()} drift (±%/yr)", value=float(drift[k]), step=0.5, format="%.1f")
    st.session_state.inputs["cpi"] = cpi
    st.session_state.inputs["drifts"] = drift

    years_to_retire = max(0, st.session_state.inputs["retire_age"] - st.session_state.inputs["age_now"])
    proj = project_costs(basket, cpi, drift, years_to_retire)
    at_ret = summarize_year(proj, years_to_retire)

    colA, colB, colC, colD = st.columns(4)
    colA.metric("Monthly basket at retirement (nominal)", f"{sym}{at_ret['monthly_nominal']:,.0f}")
    colB.metric("Monthly basket in today's money", f"{sym}{at_ret['monthly_real_today']:,.0f}")
    colC.metric("Annual basket at retirement (nominal)", f"{sym}{at_ret['annual_nominal']:,.0f}")
    colD.metric("Annual basket in today's money", f"{sym}{at_ret['annual_real_today']:,.0f}")

    # small chart
    import plotly.graph_objects as go
    fig = go.Figure()
    for cat in list(basket.keys())[:3]:
        sub = proj[proj["category"]==cat]
        fig.add_trace(go.Scatter(x=sub["year"], y=sub["annual_nominal"], mode="lines", name=f"{cat} (annual, nominal)"))
    fig.update_layout(title="A few categories inflated to retirement", xaxis_title="Years from now", yaxis_title=f"{sym}/yr", hovermode="x unified", margin=dict(l=20,r=20,t=50,b=20))
    st.plotly_chart(fig, use_container_width=True)

    b, n = nav_buttons()
    if b: prev_step()
    if n: next_step()

# ---------------------- STEP 4: Investments ----------------------
elif st.session_state.step == 4:
    step_header(4, "How do you invest?",
                "We model **real** (after-inflation) returns with uncertainty. Keep it simple unless you enjoy spreadsheets.")
    d = st.session_state.inputs
    col1, col2 = st.columns(2)
    equity_alloc = col1.slider("Equity allocation (stocks %)", 0.0, 1.0, float(d["equity_alloc"]), 0.05)
    bond_alloc = 1.0 - equity_alloc
    col1.caption(f"Bonds will be {bond_alloc:.0%} automatically.")

    colA, colB = st.columns(2)
    eq_mu = colA.number_input("Expected real return for stocks (μ, %/yr)", value=float(d["equity_mu"]), step=0.1, format="%.1f")
    eq_vol = colB.number_input("Volatility for stocks (σ, %/yr)", value=float(d["equity_vol"]), step=0.5, format="%.1f")
    colC, colD = st.columns(2)
    bd_mu = colC.number_input("Expected real return for bonds (μ, %/yr)", value=float(d["bond_mu"]), step=0.1, format="%.1f")
    bd_vol = colD.number_input("Volatility for bonds (σ, %/yr)", value=float(d["bond_vol"]), step=0.5, format="%.1f")
    corr = st.slider("Correlation between stocks and bonds", -0.9, 0.9, float(d["corr"]), 0.1)
    fees = st.slider("All-in fees (funds + platform, %/yr)", 0.0, 2.0, float(d["fees_annual"]), 0.05)

    st.session_state.inputs.update({
        "equity_alloc": equity_alloc,
        "bond_alloc": bond_alloc,
        "equity_mu": eq_mu,
        "equity_vol": eq_vol,
        "bond_mu": bd_mu,
        "bond_vol": bd_vol,
        "corr": corr,
        "fees_annual": fees
    })

    b, n = nav_buttons()
    if b: prev_step()
    if n: next_step()

# ---------------------- STEP 5: Taxes ----------------------
elif st.session_state.step == 5:
    step_header(5, "Taxes (kept simple, fully editable)",
                "We start with your country's typical income tax brackets. Everything is indexed with inflation in the simulation. You can edit numbers below.")
    ctry = st.session_state.inputs["country"]
    spec = default_tax_spec(ctry)

    # stash editable spec in session
    if "tax_df" not in st.session_state:
        st.session_state.tax_df = spec_to_df(spec)
        st.session_state.tax_allowance = spec.allowance
        st.session_state.tax_taper_start = spec.taper_start
        st.session_state.tax_taper_ratio = spec.taper_ratio
        st.session_state.tax_levy = spec.medicare_levy

    st.write(f"**{spec.name}** — progressive rates after a tax-free allowance (or standard deduction).")
    colA, colB, colC = st.columns(3)
    st.session_state.tax_allowance = colA.number_input("Tax-free allowance / standard deduction", value=float(st.session_state.tax_allowance), step=1000.0)
    st.session_state.tax_levy = colB.number_input("Extra levy (e.g., Medicare levy, as a % of taxable)", value=float(st.session_state.tax_levy*100), step=0.1, format="%.1f")/100.0
    st.session_state.tax_taper_start = colC.number_input("Allowance taper starts at (leave 0 if none)", value=float(st.session_state.tax_taper_start or 0.0), step=1000.0)
    st.session_state.tax_taper_ratio = st.slider("Allowance taper ratio (0.5 = lose £1 per £2 over the threshold)", 0.0, 1.0, float(st.session_state.tax_taper_ratio), 0.05)

    st.caption("**Brackets** — set each bracket’s upper limit and its tax rate. The last row’s upper limit can be left very large to mean “and above”.")
    st.session_state.tax_df = st.data_editor(
        st.session_state.tax_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "upper_limit": st.column_config.NumberColumn("Upper limit (currency)", help="Income at which this bracket ends"),
            "rate_percent": st.column_config.NumberColumn("Rate (%)", help="Tax rate within this bracket")
        }
    )

    b, n = nav_buttons()
    if b: prev_step()
    if n:
        extra = {
            "taper_start": (None if st.session_state.tax_taper_start == 0 else float(st.session_state.tax_taper_start)),
            "taper_ratio": float(st.session_state.tax_taper_ratio),
            "medicare_levy": float(st.session_state.tax_levy)
        }
        custom_spec = df_to_spec(st.session_state.tax_df, float(st.session_state.tax_allowance), spec.name, extra)
        st.session_state.inputs["tax_spec"] = custom_spec
        next_step()

# ---------------------- STEP 6: Withdrawal style ----------------------
elif st.session_state.step == 6:
    step_header(6, "How cautious should withdrawals be?",
                "Pick a simple rule of thumb and decide if you want to **preserve capital** (legacy) or **spend down** over retirement.")
    col1, col2 = st.columns(2)
    rule = col1.selectbox("Rule of thumb", ["3% real","3.5% real","4% real"], index=["3% real","3.5% real","4% real"].index(st.session_state.inputs["rule"]))
    legacy = col2.selectbox("Legacy preference", ["Spend to zero", "Preserve capital"], index=["Spend to zero","Preserve capital"].index(st.session_state.inputs["legacy_mode"]))

    st.session_state.inputs["rule"] = rule
    st.session_state.inputs["legacy_mode"] = legacy

    sims_col1, sims_col2, sims_col3 = st.columns(3)
    sims = sims_col1.slider("Monte Carlo paths (more = slower, but smoother)", 500, 10000, int(st.session_state.inputs["num_paths"]), 500)
    seed = sims_col2.number_input("Random seed (−1 = random each run)", value=int(st.session_state.inputs["seed"]))
    st.session_state.inputs["num_paths"] = sims
    st.session_state.inputs["seed"] = None if seed == -1 else int(seed)

    b, n = nav_buttons()
    if b: prev_step()
    if n: next_step()

# ---------------------- STEP 7: Review & Run ----------------------
elif st.session_state.step == 7:
    step_header(7, "Review your plan",
                "Quick recap. Looks good? Hit **Run my plan** to simulate thousands of futures and see the odds.")
    d = st.session_state.inputs
    sym = currency_symbol()

    col1, col2, col3 = st.columns(3)
    col1.metric("Country", d["country"])
    col2.metric("Retire age", d["retire_age"])
    col3.metric("Plan until", d["plan_until_age"])
    col1.metric("Assets now", f"{sym}{d['assets_now']:,.0f}")
    col2.metric("Monthly saving", f"{sym}{d['monthly_contrib']:,.0f}")
    col3.metric("CPI (avg)", f"{d['cpi']:.1f}%")
    col1.metric("Rule", d["rule"])
    col2.metric("Legacy", d["legacy_mode"])
    col3.metric("Paths", f"{d['num_paths']}")

    years_to_ret = max(0, d["retire_age"] - d["age_now"])
    proj = project_costs(d["basket_today"], d["cpi"], d["drifts"], years_to_ret)
    basket_ret = summarize_year(proj, years_to_ret)
    st.write(f"**Estimated core spending at retirement:** {sym}{basket_ret['annual_nominal']:,.0f} per year (nominal), which is about {sym}{basket_ret['annual_real_today']:,.0f} in today’s money.")

    if run_button():
        # Build config
        rule_pct = 0.03 if "3%" in d["rule"] else (0.035 if "3.5" in d["rule"] else 0.04)
        cfg = SimConfig(
            age_now=int(d["age_now"]),
            retire_age=float(d["retire_age"]),
            plan_until_age=int(d["plan_until_age"]),
            assets_now=float(d["assets_now"]),
            monthly_contrib=float(d["monthly_contrib"]),
            contrib_growth_pct=float(d["contrib_growth_pct"]),
            equity_alloc=float(d["equity_alloc"]),
            bond_alloc=float(d["bond_alloc"]),
            equity_mu=float(d["equity_mu"]),
            equity_vol=float(d["equity_vol"]),
            bond_mu=float(d["bond_mu"]),
            bond_vol=float(d["bond_vol"]),
            corr=float(d["corr"]),
            fees_annual=float(d["fees_annual"]),
            cpi_pct=float(d["cpi"]),
            target_annual_real=float(basket_ret["annual_real_today"]),
            rule_pct=float(rule_pct),
            preserve_capital=(d["legacy_mode"] == "Preserve capital"),
            tax_spec_baseline=d.get("tax_spec", default_tax_spec(d["country"])),
            num_paths=int(d["num_paths"]),
            seed=d["seed"],
        )

        with st.spinner("Running simulations…"):
            summary, series = run_monte_carlo(cfg)

        st.session_state.summary = summary
        st.session_state.series = series
        next_step()

    b, _ = nav_buttons()
    if b: prev_step()

# ---------------------- STEP 8: Results ----------------------
elif st.session_state.step == 8:
    step_header(8, "Results — what are my odds?",
                "Everything is shown in **today’s money** for honesty. Hover the charts for details.")
    if "summary" not in st.session_state:
        st.warning("Run your plan first.")
    else:
        sym = currency_symbol()
        s = st.session_state.summary
        series = st.session_state.series

        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div class='card'><div class='caption'>Success probability</div><div class='kpi'>{s['success_rate']:.1f}%</div><div class='caption'>Meet plan & finish ≥ 0</div></div>", unsafe_allow_html=True)
        idx_ret = int((st.session_state.inputs["retire_age"] - st.session_state.inputs["age_now"]) * 12)
        c2.markdown(f"<div class='card'><div class='caption'>Median net income at retirement</div><div class='kpi'>{sym}{(s['wd_p50'][idx_ret]*12):,.0f}/yr</div><div class='caption'>After tax, real</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='card'><div class='caption'>3% rule on assets now</div><div class='kpi'>{sym}{(st.session_state.inputs['assets_now']*0.03):,.0f}/yr</div><div class='caption'>Before tax, real</div></div>", unsafe_allow_html=True)

        # Wealth chart
        figW = go.Figure()
        figW.add_trace(go.Scatter(x=s["ages"], y=s["wealth_p50"], mode="lines", name="Median wealth"))
        figW.add_trace(go.Scatter(x=s["ages"], y=s["wealth_p95"], mode="lines", name="p95", line=dict(dash="dot")))
        figW.add_trace(go.Scatter(x=s["ages"], y=s["wealth_p5"],  mode="lines", name="p5", line=dict(dash="dot"), fill="tonexty"))
        figW.add_vline(x=st.session_state.inputs["retire_age"], line_dash="dash", line_color="green")
        figW.update_layout(title="Portfolio value (real)", xaxis_title="Age", yaxis_title=f"{sym}", hovermode="x unified", margin=dict(l=20,r=20,t=50,b=20))
        st.plotly_chart(figW, use_container_width=True)

        # Income chart
        figI = go.Figure()
        figI.add_trace(go.Scatter(x=s["ages"], y=s["wd_p50"]*12, mode="lines", name="Median net income (yr)"))
        figI.add_trace(go.Scatter(x=s["ages"], y=s["wd_p95"]*12, mode="lines", name="p95", line=dict(dash="dot")))
        figI.add_trace(go.Scatter(x=s["ages"], y=s["wd_p5"]*12,  mode="lines", name="p5", line=dict(dash="dot"), fill="tonexty"))
        figI.add_vline(x=st.session_state.inputs["retire_age"], line_dash="dash", line_color="green")
        figI.update_layout(title="Retirement income (after tax, real)", xaxis_title="Age", yaxis_title=f"{sym}/yr", hovermode="x unified", margin=dict(l=20,r=20,t=50,b=20))
        st.plotly_chart(figI, use_container_width=True)

        st.markdown("#### Download")
        colL, colR = st.columns(2)
        colL.download_button("⬇️ Cashflow (median) CSV", data=export_series_csv(series), file_name="cashflows_median.csv", mime="text/csv", use_container_width=True)
        colR.download_button("⬇️ Scenario config JSON", data=export_config(st.session_state.inputs), file_name="config.json", mime="application/json", use_container_width=True)

        st.markdown("---")
        st.caption("Educational tool. Taxes simplified & indexed; country presets may lag current law. Tweak numbers to your reality.")
        if st.button("Start over"):
            st.session_state.clear()
            st.rerun()