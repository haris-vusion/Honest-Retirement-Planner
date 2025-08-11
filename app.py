import copy
import streamlit as st
import plotly.graph_objects as go

from config import APP_NAME, DEFAULTS, CURRENCIES
from ui import inject_css, app_header, step_header, small_help, nav_row
from costs import project_costs, summarize_year
from tax_models import default_tax_spec, spec_to_df, df_to_spec
from simulation import SimConfig, run_monte_carlo
from exporters import export_config, export_series_csv

st.set_page_config(page_title=APP_NAME, page_icon="🧭", layout="wide")
inject_css()
app_header(APP_NAME, "Step-by-step retirement planner. Simple English. No fairy tales.")

# ---------- session bootstrap ----------
if "step" not in st.session_state:
    st.session_state.step = 1
if "inputs" not in st.session_state:
    st.session_state.inputs = copy.deepcopy(DEFAULTS)
if "tax_model_country" not in st.session_state:
    st.session_state.tax_model_country = st.session_state.inputs["country"]

def go(step: int):
    st.session_state.step = max(1, step)

def currency_symbol():
    return CURRENCIES.get(st.session_state.inputs["country"], "¤")

# ============ STEP 1 ============
if st.session_state.step == 1:
    step_header(1, "Where are you and when do you want to retire?",
                "We load tax rules for your country. You can edit them later.")

    with st.form("step1_form", clear_on_submit=False):
        cols = st.columns(2)
        country = cols[0].selectbox(
            "Country",
            ["UK","USA","France","Germany","Australia","Custom"],
            index=["UK","USA","France","Germany","Australia","Custom"].index(st.session_state.inputs["country"]),
            key="country_widget",
        )
        age_now = cols[1].number_input(
            "Your age today",
            min_value=18, max_value=80,
            value=st.session_state.inputs["age_now"],
            key="age_now_widget"
        )
        retire_age = st.number_input(
            "Target retirement age",
            min_value=age_now+1, max_value=85,
            value=st.session_state.inputs["retire_age"],
            key="retire_age_widget"
        )
        plan_until_age = st.number_input(
            "Plan until age (longevity buffer)",
            min_value=retire_age+5, max_value=105,
            value=st.session_state.inputs["plan_until_age"],
            key="plan_until_widget"
        )
        small_help("Pick a conservative 'plan until' age—outliving money is worse than leaving extra.")

        back, submit = nav_row(back_to=None)
        if submit:
            st.session_state.inputs.update({
                "country": country,
                "age_now": int(age_now),
                "retire_age": float(retire_age),
                "plan_until_age": int(plan_until_age),
            })
            # Reset tax editor if country changed
            st.session_state.tax_model_country = country
            go(2)

# ============ STEP 2 ============
elif st.session_state.step == 2:
    step_header(2, "What do you have now, and what can you save?",
                "All amounts are in your local currency.")
    sym = currency_symbol()

    with st.form("step2_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)
        assets_now = c1.number_input(f"Investable assets now ({sym})", min_value=0,
                                     value=st.session_state.inputs["assets_now"], step=1000, key="assets_now_widget")
        monthly_contrib = c2.number_input(f"Monthly contribution ({sym})", min_value=0,
                                          value=st.session_state.inputs["monthly_contrib"], step=50, key="contrib_widget")
        contrib_growth = c3.slider("How fast your contributions grow (nominal %/yr)", 0.0, 10.0,
                                   value=float(st.session_state.inputs["contrib_growth_pct"]), step=0.1, key="contrib_growth_widget")

        back, submit = nav_row(back_to=1)
        if back:
            go(1)
        elif submit:
            st.session_state.inputs.update({
                "assets_now": int(assets_now),
                "monthly_contrib": int(monthly_contrib),
                "contrib_growth_pct": float(contrib_growth),
            })
            go(3)

# ============ STEP 3 ============
elif st.session_state.step == 3:
    step_header(3, "What does your life cost?",
                "Tell us your typical monthly spending today. We’ll project it to your retirement date by category.")
    sym = currency_symbol()
    basket = copy.deepcopy(st.session_state.inputs["basket_today"])
    drift = copy.deepcopy(st.session_state.inputs["drifts"])

    with st.form("step3_form", clear_on_submit=False):
        cols = st.columns(4)
        for i, k in enumerate(list(basket.keys())):
            with cols[i % 4]:
                basket[k] = st.number_input(f"{k.replace('_',' ').title()} ({sym}/mo)",
                                            min_value=0, value=int(basket[k]), step=10, key=f"basket_{k}_widget")

        st.markdown("**Inflation assumptions**")
        cpi = st.slider("Headline CPI (average % per year)", 0.0, 10.0,
                        value=float(st.session_state.inputs["cpi"]), step=0.1, key="cpi_widget")

        with st.expander("Advanced: category drifts vs CPI (e.g., rent often runs hotter than CPI)", expanded=False):
            cols2 = st.columns(4)
            for i, k in enumerate(list(drift.keys())):
                with cols2[i % 4]:
                    drift[k] = st.number_input(f"{k.replace('_',' ').title()} drift (±%/yr)",
                                               value=float(drift[k]), step=0.5, format="%.1f", key=f"drift_{k}_widget")

        years_to_retire = max(0, st.session_state.inputs["retire_age"] - st.session_state.inputs["age_now"])
        proj = project_costs(basket, cpi, drift, years_to_retire)
        at_ret = summarize_year(proj, years_to_retire)

        colA, colB, colC, colD = st.columns(4)
        colA.metric("Monthly basket at retirement (nominal)", f"{sym}{at_ret['monthly_nominal']:,.0f}")
        colB.metric("Monthly basket in today's money", f"{sym}{at_ret['monthly_real_today']:,.0f}")
        colC.metric("Annual basket at retirement (nominal)", f"{sym}{at_ret['annual_nominal']:,.0f}")
        colD.metric("Annual basket in today's money", f"{sym}{at_ret['annual_real_today']:,.0f}")

        fig = go.Figure()
        for cat in list(basket.keys())[:3]:
            sub = proj[proj["category"]==cat]
            fig.add_trace(go.Scatter(x=sub["year"], y=sub["annual_nominal"], mode="lines", name=f"{cat} (annual, nominal)"))
        fig.update_layout(title="A few categories inflated to retirement", xaxis_title="Years from now", yaxis_title=f"{sym}/yr",
                          hovermode="x unified", margin=dict(l=20,r=20,t=40,b=20))
        st.plotly_chart(fig, use_container_width=True)

        back, submit = nav_row(back_to=2)
        if back:
            go(2)
        elif submit:
            st.session_state.inputs["basket_today"] = basket
            st.session_state.inputs["cpi"] = cpi
            st.session_state.inputs["drifts"] = drift
            go(4)

# ============ STEP 4 ============
elif st.session_state.step == 4:
    step_header(4, "How do you invest?",
                "We model **real** (after-inflation) returns with uncertainty. Keep it simple unless you enjoy spreadsheets.")
    d = st.session_state.inputs

    with st.form("step4_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        equity_alloc = col1.slider("Equity allocation (stocks %)", 0.0, 1.0, float(d["equity_alloc"]), 0.05, key="equity_alloc_widget")
        bond_alloc = 1.0 - equity_alloc
        col1.caption(f"Bonds will be {bond_alloc:.0%} automatically.")

        colA, colB = st.columns(2)
        eq_mu = colA.number_input("Expected real return for stocks (μ, %/yr)", value=float(d["equity_mu"]), step=0.1, format="%.1f", key="eq_mu_widget")
        eq_vol = colB.number_input("Volatility for stocks (σ, %/yr)", value=float(d["equity_vol"]), step=0.5, format="%.1f", key="eq_vol_widget")
        colC, colD = st.columns(2)
        bd_mu = colC.number_input("Expected real return for bonds (μ, %/yr)", value=float(d["bond_mu"]), step=0.1, format="%.1f", key="bd_mu_widget")
        bd_vol = colD.number_input("Volatility for bonds (σ, %/yr)", value=float(d["bond_vol"]), step=0.5, format="%.1f", key="bd_vol_widget")
        corr = st.slider("Correlation between stocks and bonds", -0.9, 0.9, float(d["corr"]), 0.1, key="corr_widget")
        fees = st.slider("All-in fees (funds + platform, %/yr)", 0.0, 2.0, float(d["fees_annual"]), 0.05, key="fees_widget")

        back, submit = nav_row(back_to=3)
        if back:
            go(3)
        elif submit:
            st.session_state.inputs.update({
                "equity_alloc": equity_alloc,
                "bond_alloc": bond_alloc,
                "equity_mu": eq_mu,
                "equity_vol": eq_vol,
                "bond_mu": bd_mu,
                "bond_vol": bd_vol,
                "corr": corr,
                "fees_annual": fees,
            })
            go(5)

# ============ STEP 5 ============
elif st.session_state.step == 5:
    step_header(5, "Taxes (kept simple, editable)",
                "We start with your country's typical brackets. Everything indexes with inflation in the sim.")
    country = st.session_state.inputs["country"]
    preset = default_tax_spec(country)

    # Initialize editor state per country
    if "tax_state_country" not in st.session_state or st.session_state.tax_state_country != country:
        st.session_state.tax_df = spec_to_df(preset)
        st.session_state.tax_allowance = preset.allowance
        st.session_state.tax_taper_start = preset.taper_start or 0.0
        st.session_state.tax_taper_ratio = preset.taper_ratio
        st.session_state.tax_levy = preset.medicare_levy
        st.session_state.tax_state_country = country

    with st.form("step5_form", clear_on_submit=False):
        colA, colB, colC = st.columns(3)
        allowance = colA.number_input("Tax-free allowance / standard deduction", value=float(st.session_state.tax_allowance), step=1000.0, key="tax_allow_widget")
        levy = colB.number_input("Extra levy (e.g., Medicare levy, % of taxable)", value=float(st.session_state.tax_levy*100), step=0.1, format="%.1f", key="tax_levy_widget")/100.0
        taper_start = colC.number_input("Allowance taper starts at (0 = none)", value=float(st.session_state.tax_taper_start), step=1000.0, key="tax_taper_start_widget")
        taper_ratio = st.slider("Allowance taper ratio (0.5 = lose 1 per 2 above threshold)", 0.0, 1.0, float(st.session_state.tax_taper_ratio), 0.05, key="tax_taper_ratio_widget")

        st.caption("**Brackets** — set each bracket’s upper limit and rate. Last row can be huge to mean 'and above'.")
        tax_df = st.data_editor(
            st.session_state.tax_df,
            key="tax_df_widget",
            num_rows="dynamic",
            use_container_width=True,
        )

        back, submit = nav_row(back_to=4)
        if back:
            go(4)
        elif submit:
            st.session_state.tax_df = tax_df
            st.session_state.tax_allowance = allowance
            st.session_state.tax_taper_start = taper_start
            st.session_state.tax_taper_ratio = taper_ratio
            st.session_state.tax_levy = levy
            extra = {
                "taper_start": (None if taper_start == 0 else float(taper_start)),
                "taper_ratio": float(taper_ratio),
                "medicare_levy": float(levy),
            }
            st.session_state.inputs["tax_spec"] = df_to_spec(tax_df, float(allowance), preset.name, extra)
            go(6)

# ============ STEP 6 ============
elif st.session_state.step == 6:
    step_header(6, "How cautious should withdrawals be?",
                "Pick a rule of thumb and whether to **preserve capital** (legacy) or **spend down**.")
    d = st.session_state.inputs

    with st.form("step6_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        rule = col1.selectbox("Rule of thumb", ["3% real","3.5% real","4% real"],
                              index=["3% real","3.5% real","4% real"].index(d["rule"]), key="rule_widget")
        legacy = col2.selectbox("Legacy preference", ["Spend to zero", "Preserve capital"],
                                index=["Spend to zero","Preserve capital"].index(d["legacy_mode"]), key="legacy_widget")

        sims_col1, sims_col2 = st.columns(2)
        sims = sims_col1.slider("Monte Carlo paths (more = slower, but smoother)", 500, 10000, int(d["num_paths"]), 500, key="paths_widget")
        seed = sims_col2.number_input("Random seed (−1 = random each run)", value=int(d["seed"]), key="seed_widget")

        back, submit = nav_row(back_to=5)
        if back:
            go(5)
        elif submit:
            st.session_state.inputs["rule"] = rule
            st.session_state.inputs["legacy_mode"] = legacy
            st.session_state.inputs["num_paths"] = int(sims)
            st.session_state.inputs["seed"] = (None if int(seed) == -1 else int(seed))
            go(7)

# ============ STEP 7 ============
elif st.session_state.step == 7:
    step_header(7, "Review your plan",
                "Looks good? Hit **Run my plan** to simulate and see your odds.")
    d = st.session_state.inputs
    sym = currency_symbol()

    years_to_ret = max(0, d["retire_age"] - d["age_now"])
    proj = project_costs(d["basket_today"], d["cpi"], d["drifts"], years_to_ret)
    basket_ret = summarize_year(proj, years_to_ret)

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

    st.write(f"**Estimated core spending at retirement:** {sym}{basket_ret['annual_nominal']:,.0f} per year (nominal), about {sym}{basket_ret['annual_real_today']:,.0f} in today’s money.")

    with st.form("step7_form", clear_on_submit=False):
        back, submit = nav_row(back_to=6, next_label="Run my plan ▶")
        if back:
            go(6)
        elif submit:
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
            go(8)

# ============ STEP 8 ============
elif st.session_state.step == 8:
    step_header(8, "Results — what are my odds?",
                "Everything is shown in **today’s money**. Hover charts for details.")
    if "summary" not in st.session_state:
        st.warning("Run your plan first.")
    else:
        d = st.session_state.inputs
        sym = currency_symbol()
        s = st.session_state.summary
        series = st.session_state.series

        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div class='card'><div class='caption'>Success probability</div><div class='kpi'>{s['success_rate']:.1f}%</div><div class='caption'>Meet plan & finish ≥ 0</div></div>", unsafe_allow_html=True)
        idx_ret = int((d["retire_age"] - d["age_now"]) * 12)
        c2.markdown(f"<div class='card'><div class='caption'>Median net income at retirement</div><div class='kpi'>{sym}{(s['wd_p50'][idx_ret]*12):,.0f}/yr</div><div class='caption'>After tax, real</div></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='card'><div class='caption'>3% rule on assets now</div><div class='kpi'>{sym}{(d['assets_now']*0.03):,.0f}/yr</div><div class='caption'>Before tax, real</div></div>", unsafe_allow_html=True)

        figW = go.Figure()
        figW.add_trace(go.Scatter(x=s["ages"], y=s["wealth_p50"], mode="lines", name="Median wealth"))
        figW.add_trace(go.Scatter(x=s["ages"], y=s["wealth_p95"], mode="lines", name="p95", line=dict(dash="dot")))
        figW.add_trace(go.Scatter(x=s["ages"], y=s["wealth_p5"],  mode="lines", name="p5",  line=dict(dash="dot"), fill="tonexty"))
        figW.add_vline(x=d["retire_age"], line_dash="dash", line_color="green")
        figW.update_layout(title="Portfolio value (real)", xaxis_title="Age", yaxis_title=f"{sym}",
                           hovermode="x unified", margin=dict(l=20,r=20,t=40,b=20))
        st.plotly_chart(figW, use_container_width=True)

        figI = go.Figure()
        figI.add_trace(go.Scatter(x=s["ages"], y=s["wd_p50"]*12, mode="lines", name="Median net income (yr)"))
        figI.add_trace(go.Scatter(x=s["ages"], y=s["wd_p95"]*12, mode="lines", name="p95", line=dict(dash="dot")))
        figI.add_trace(go.Scatter(x=s["ages"], y=s["wd_p5"]*12,  mode="lines", name="p5",  line=dict(dash="dot"), fill="tonexty"))
        figI.add_vline(x=d["retire_age"], line_dash="dash", line_color="green")
        figI.update_layout(title="Retirement income (after tax, real)", xaxis_title="Age", yaxis_title=f"{sym}/yr",
                           hovermode="x unified", margin=dict(l=20,r=20,t=40,b=20))
        st.plotly_chart(figI, use_container_width=True)

        st.markdown("#### Download")
        colL, colR = st.columns(2)
        colL.download_button("⬇️ Cashflow (median) CSV", data=export_series_csv(series),
                             file_name="cashflows_median.csv", mime="text/csv", use_container_width=True)
        colR.download_button("⬇️ Scenario config JSON", data=export_config(st.session_state.inputs),
                             file_name="config.json", mime="application/json", use_container_width=True)

        st.markdown("---")
        st.caption("Educational tool. Taxes simplified & indexed; presets may lag current law. Tweak numbers to your reality.")
        if st.button("Start over"):
            st.session_state.clear()
            st.rerun()