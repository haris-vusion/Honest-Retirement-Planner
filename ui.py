import streamlit as st

def inject_css():
    try:
        with open("assets/styles.css") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass

def header(app_name: str):
    cols = st.columns([1,6,2])
    with cols[0]:
        st.image("assets/logo.svg", width=56)
    with cols[1]:
        st.markdown(f"## {app_name}")
        st.markdown("<span class='caption'>Simple English. Inflation-first. Tax-smart. No fairy tales.</span>", unsafe_allow_html=True)
    with cols[2]:
        st.markdown("<div class='badge'>Monte Carlo</div> <div class='badge'>Multi-country tax</div> <div class='badge'>ROI presets</div>", unsafe_allow_html=True)

def helptext(text: str):
    st.caption(text)
