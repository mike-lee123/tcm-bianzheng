"""把 tcm/engine.py、tcm/lookup.py、app_pages.py、streamlit_app.py 合併成單一檔案，並把資料檔平放，
輸出到 ../tcm_streamlit_upload/。那個資料夾裡的檔案可以一次全選拖進 GitHub，不必建任何資料夾。

Usage: python build_single.py
"""
import re
import shutil
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
SRC = Path(__file__).resolve().parent
OUT = SRC.parent / "tcm_streamlit_upload"


def body(path, drop_docstring=True):
    t = (SRC / path).read_text(encoding="utf-8")
    if drop_docstring:
        t = re.sub(r'^"""[\s\S]*?"""\n', "", t, count=1)
    return t


def sub(t, old, new):
    assert old in t, old[:60]
    return t.replace(old, new)


# ── engine ──
eng = body("tcm/engine.py")
eng = sub(eng, "from __future__ import annotations\n", "")
eng_names = re.findall(r"^def (\w+)\(", eng, flags=re.M)

# ── lookup ──
lk = body("tcm/lookup.py")
lk = sub(lk, "import argparse, json, re, sys\nfrom pathlib import Path\n", "")
lk = re.sub(r"_HERE = Path\(__file__\)[\s\S]*?_HERE\.parent / \"data\" / \"texts\"\)\n", "", lk, count=1)
lk = sub(lk, 'ROLES_FILE = TEXTS.parent / "families" / "醫方集解_君臣.json"', 'ROLES_FILE = find_data("醫方集解_君臣.json")')
lk = sub(lk, "    if not ROLES_FILE.exists():", "    if not ROLES_FILE:")
lk = sub(lk, 'read = read or (lambda b: (TEXTS / f"{b}.md").read_text(encoding="utf-8"))',
         'read = read or (lambda b: find_data(f"{b}.md").read_text(encoding="utf-8"))')
lk = lk[:lk.index("def main():")].rstrip() + "\n"
lk_names = re.findall(r"^def (\w+)\(", lk, flags=re.M) + ["BOOKS", "RUBRICS", "DEFAULT_RUBRICS"]

# ── pages ──
pg = body("app_pages.py")
pg = re.sub(r"^import html\nimport json\nimport re\nfrom pathlib import Path\n\nimport streamlit as st\n\n", "", pg)
pg = re.sub(r"try:\n    from tcm import engine, lookup\nexcept ModuleNotFoundError:.*\n    import engine\n    import lookup\n\n", "", pg)
pg = sub(pg, 'ROOT = Path(__file__).resolve().parent\nKB_DIR = ROOT / "data" / "bianzheng"\n', "")
pg = sub(pg, '    return sorted([p.stem for p in KB_DIR.glob("*.json")], key=lambda n: order.get(n, 9))',
         '    return sorted([n for n in order if find_data(f"{n}.json")], key=lambda n: order.get(n, 9))')
pg = sub(pg, '    return json.loads((KB_DIR / f"{name}.json").read_text(encoding="utf-8"))',
         '    return json.loads(find_data(f"{name}.json").read_text(encoding="utf-8"))')
pg = sub(pg, '    return {b: (lookup.TEXTS / f"{b}.md").read_text(encoding="utf-8") for b in lookup.BOOKS}',
         '    return {b: find_data(f"{b}.md").read_text(encoding="utf-8") for b in lookup.BOOKS}')

# ── main (navigation part only) ──
mn = body("streamlit_app.py")
nav = mn[mn.index("# ── navigation"):]

single = f'''"""中藥典籍辨證（單一檔案版）：規則式辨證選方（外感、脾胃）與六部典籍原文查詢。

部署：把這個檔案、requirements.txt 和 9 個資料檔（6 個 .md、3 個 .json）上傳到 GitHub repo，
放在根目錄或任何子資料夾都可以；再到 https://share.streamlit.io 部署，主檔填 streamlit_app.py。
本檔由 build_single.py 從 tcm_streamlit/ 的原始碼自動產生，請勿手動修改。
"""
import html
import json
import re
import sys
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import streamlit as st

st.set_page_config(page_title="中藥典籍辨證", page_icon="🌿", layout="wide")

ROOT = Path(__file__).resolve().parent
DATA_FILES = (["外感.json", "脾胃.json", "醫方集解_君臣.json"]
              + [f"{{b}}.md" for b in ("本草備要", "神農本草經", "本草綱目", "傷寒論", "醫方集解", "溫病條辨")])


@lru_cache(maxsize=None)
def find_data(name):
    """在 repo 裡找資料檔：根目錄、data/ 底下或任何子資料夾都可以。找不到回傳 None。"""
    for d in (ROOT, ROOT / "data" / "texts", ROOT / "data" / "bianzheng", ROOT / "data" / "families", ROOT / "data"):
        if (d / name).is_file():
            return d / name
    return next((p for p in ROOT.rglob(name) if p.is_file() and ".git" not in p.parts), None)


# ── 部署檢查：缺檔時直接列出缺什麼、repo 裡實際有什麼 ──────────────────────────────
_missing = [n for n in DATA_FILES if not find_data(n)]
if _missing:
    NL = "\\n"
    st.error("部署的檔案不完整，找不到：" + NL + NL + NL.join(f"- `{{m}}`" for m in _missing) + NL + NL
             + "請把 tcm_streamlit_upload 資料夾裡的全部檔案上傳到 GitHub repo。")
    _found = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts)
    st.markdown("**目前 repo 裡的檔案：**")
    st.code(NL.join(_found[:80]) + (NL + "…" if len(_found) > 80 else ""))
    st.stop()


# ══ 辨證引擎（來自 tcm/engine.py）══════════════════════════════════════════════
{eng.strip()}


engine = SimpleNamespace(**{{n: globals()[n] for n in {eng_names!r}}})
engine.MAIN, engine.MINOR = MAIN, MINOR


# ══ 原文查詢（來自 tcm/lookup.py）══════════════════════════════════════════════
{lk.strip()}


lookup = SimpleNamespace(**{{n: globals()[n] for n in {lk_names!r}}})


# ══ 頁面（來自 app_pages.py）═══════════════════════════════════════════════════
{pg.strip()}


{nav.strip()}
'''

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()
(OUT / "streamlit_app.py").write_text(single, encoding="utf-8")
shutil.copy(SRC / "requirements.txt", OUT / "requirements.txt")
for p in (SRC / "data").rglob("*"):
    if p.is_file():
        shutil.copy(p, OUT / p.name)
print("written:", sorted(x.name for x in OUT.iterdir()))
