"""中藥典籍辨證：規則式辨證選方（外感、脾胃）與六部典籍原文查詢。

部署：把整個資料夾推到 GitHub，再到 https://share.streamlit.io 選這個 repo，主檔填 streamlit_app.py。
"""
import sys
from pathlib import Path

import streamlit as st

st.set_page_config(page_title="中藥典籍辨證", page_icon="🌿", layout="wide")

# ── 部署檢查：缺檔時直接列出缺什麼、repo 裡實際有什麼 ──────────────────────────────
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:  # 確保 app_pages、tcm 等模組一定找得到
    sys.path.insert(0, str(ROOT))
BOOKS = ("本草備要", "神農本草經", "本草綱目", "傷寒論", "醫方集解", "溫病條辨")
REQUIRED = (["app_pages.py", "data/bianzheng/外感.json", "data/bianzheng/脾胃.json",
             "data/families/醫方集解_君臣.json"] + [f"data/texts/{b}.md" for b in BOOKS])
missing = [r for r in REQUIRED if not (ROOT / r).is_file()]
if not any((ROOT / d / "engine.py").is_file() and (ROOT / d / "lookup.py").is_file() for d in ("tcm", ".")):
    missing.append("tcm/engine.py 與 tcm/lookup.py")
if missing:
    NL = "\n"
    st.error("部署的檔案不完整，缺少：" + NL + NL
             + NL.join(f"- `{m}`" for m in missing) + NL + NL
             + "請把本機 `tcm_streamlit` 資料夾裡的所有檔案與資料夾，依原本的結構上傳到 GitHub repo 的根目錄。")
    found = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*")
                   if p.is_file() and ".git" not in p.parts)
    st.markdown("**目前 repo 裡的檔案：**")
    st.code(NL.join(found[:80]) + (NL + "…" if len(found) > 80 else ""))
    st.stop()

from app_pages import DISCLAIMER, page_bianzheng, page_lookup  # noqa: E402

# ── navigation ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**中藥典籍辨證**")
    st.caption("原文出自維基文庫公有領域版本。辨證程式是學習用的規則系統，不能取代面診。")
    st.caption(DISCLAIMER)

nav = st.navigation([st.Page(page_bianzheng, title="辨證選方", icon="🩺", default=True),
                     st.Page(page_lookup, title="典籍原文查詢", icon="📖", url_path="lookup")])
nav.run()
