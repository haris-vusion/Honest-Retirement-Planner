import streamlit as st
import base64

def inject_css():
    try:
        with open("assets/styles.css", "r") as f:
            st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)
    except Exception:
        pass

def header(app_name: str):
    cols = st.columns([1,6,2])
    with cols[0]:
        st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
        st.image("assets/logo.svg", width=56, caption=None, use_column_width=False)
    with cols[1]:
        st.markdown(f"## {app_name}")
        st.markdown(
            "<span class='caption'>A brutally honest, inflation-aware, tax-smart retirement planner.</span>",
            unsafe_allow_html=True
        )
    with cols[2]:
        st.markdown("<div class='badge'>Monte Carlo</div> <div class='badge'>UK Tax-aware</div> <div class='badge'>Inflation-first</div>", unsafe_allow_html=True)

def help_tip(text: str):
    st.caption(text)

def pill(label: str, value: str):
    st.markdown(f"<div class='badge'><b>{label}:</b> {value}</div>", unsafe_allow_html=True)

def download_button_bytes(filename: str, content: bytes, mime: str, label="Download"):
    b64 = base64.b64encode(content).decode()
    href = f'<a download="{filename}" href="data:{mime};base64,{b64}">{label}</a>'
    st.markdown(href, unsafe_allow_html=True)
