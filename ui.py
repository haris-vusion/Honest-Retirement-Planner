import streamlit as st

def inject_css():
    try:
        with open("assets/styles.css", "r", encoding="utf-8") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass

def app_header(title: str, subtitle: str = ""):
    cols = st.columns([1,6,2])
    with cols[0]:
        st.image("assets/logo.svg", width=56)
    with cols[1]:
        st.markdown(f"## {title}")
        if subtitle:
            st.caption(subtitle)
    with cols[2]:
        st.markdown(
            "<div class='badge'>Wizard</div> "
            "<div class='badge'>Monte Carlo</div> "
            "<div class='badge'>Multi-country tax</div>",
            unsafe_allow_html=True,
        )

def step_header(step: int, title: str, explainer: str):
    st.markdown(f"### Step {step}: {title}")
    st.write(explainer)

def small_help(text: str):
    st.caption(text)

def nav_row(back_to: int = None, next_label="Save & Next →"):
    cols = st.columns([1,1,6])
    back_clicked = False
    if back_to is not None:
        back_clicked = cols[0].form_submit_button("⬅️ Back", use_container_width=True)
    submit = cols[1].form_submit_button(next_label, type="primary", use_container_width=True)
    return back_clicked, submit
