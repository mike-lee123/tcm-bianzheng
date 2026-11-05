"""中藥典籍辨證：規則式辨證選方（外感、脾胃）與六部典籍原文查詢。

部署：把整個資料夾推到 GitHub，再到 https://share.streamlit.io 選這個 repo，主檔填 streamlit_app.py。
"""
import streamlit as st

st.set_page_config(page_title="中藥典籍辨證", page_icon="🌿", layout="wide")

from app_pages import DISCLAIMER, page_bianzheng, page_lookup  # noqa: E402

# ── navigation ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**中藥典籍辨證**")
    st.caption("原文出自維基文庫公有領域版本。辨證程式是學習用的規則系統，不能取代面診。")
    st.caption(DISCLAIMER)

nav = st.navigation([st.Page(page_bianzheng, title="辨證選方", icon="🩺", default=True),
                     st.Page(page_lookup, title="典籍原文查詢", icon="📖", url_path="lookup")])
nav.run()
