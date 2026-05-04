import streamlit as st

st.set_page_config(
    page_title="TWIN-RBI Mongstad",
    page_icon="🔧",
    layout="wide"
)

st.title("TWIN-RBI Mongstad")
st.subheader("Digital Twin de Integridad Mecánica — Refinería Equinor")

st.markdown("---")

col1, col2, col3, col4 = st.columns(4)
col1.metric("Activos monitorizados", "12")
col2.metric("Accuracy Random Forest", "88.4%")
col3.metric("Activo crítico", "L-10", "RUL 6.2 años")
col4.metric("V-101 boquilla F", "2.13×", "ratio falla WRC-107")

st.markdown("---")
st.info("Dashboard en construcción — módulos disponibles próximamente")