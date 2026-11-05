"""兩個頁面的內容：辨證選方、典籍原文查詢。由 streamlit_app.py 匯入並放進導覽。"""
import html
import json
import re
from pathlib import Path

import streamlit as st

from tcm import engine, lookup

ROOT = Path(__file__).resolve().parent
KB_DIR = ROOT / "data" / "bianzheng"
DISCLAIMER = "以上僅供學習參考，實際用藥請由中醫師面診後處方。"



# ── data ──────────────────────────────────────────────────────────────────────
@st.cache_data
def kb_names():
    order = {"外感": 0, "脾胃": 1}
    return sorted([p.stem for p in KB_DIR.glob("*.json")], key=lambda n: order.get(n, 9))


@st.cache_data
def load_kb(name):
    return json.loads((KB_DIR / f"{name}.json").read_text(encoding="utf-8"))


@st.cache_resource
def texts():
    return {b: (lookup.TEXTS / f"{b}.md").read_text(encoding="utf-8") for b in lookup.BOOKS}


@st.cache_data
def run_checks(name):
    kb = load_kb(name)
    F = {p["id"]: p["formula"] for p in kb["patterns"]}
    out = []
    for title, cases, note in engine.case_sets(kb):
        res = engine.check(kb, cases)
        rows = [{"": "✓" if r["ok"] else "✗", "案例": r["label"], "條文": r["text"],
                 "預期": ("出現原文禁忌" if r["expectCaution"] else
                        "或".join(F.get(i, i) for i in r["expect"]) if r["expect"] else
                        "不是" + "、".join(F.get(i, i) for i in r["expectNot"])),
                 "程式首選": F.get(r["first"], "—")} for r in res]
        out.append((title, sum(r["ok"] for r in res), len(res), note, rows))
    return out


def strip_tags(s):
    return re.sub(r"<[^>]+>", "", s)


def limit_items(kb):
    raw = kb.get("page", {}).get("limits", "")
    return [strip_tags(x).strip() for x in re.findall(r"<li>(.*?)</li>", raw, flags=re.S)]


# ── page 1: 辨證選方 ───────────────────────────────────────────────────────────
def group_key(kbname, i):
    return f"pick_{kbname}_{i}"


def clear_all(kbname, kb):
    for i, _ in enumerate(kb["groups"]):
        st.session_state[group_key(kbname, i)] = []
    st.session_state[f"temp_{kbname}"] = None
    st.session_state[f"free_{kbname}"] = ""


def add_free_text(kbname, kb):
    ids, temp, unknown = engine.parse_free_text(kb, st.session_state.get(f"free_{kbname}", ""))
    where = {it[0]: i for i, g in enumerate(kb["groups"]) for it in g["items"]}
    L = engine.labels(kb)
    for sid in ids:
        k = group_key(kbname, where[sid])
        cur = list(st.session_state.get(k, []))
        if L[sid] not in cur:
            st.session_state[k] = cur + [L[sid]]
    if temp is not None and f"temp_{kbname}" in st.session_state:
        st.session_state[f"temp_{kbname}"] = temp
    st.session_state[f"unknown_{kbname}"] = unknown
    st.session_state[f"free_{kbname}"] = ""


def load_sample(kbname, kb, case):
    clear_all(kbname, kb)
    where = {it[0]: i for i, g in enumerate(kb["groups"]) for it in g["items"]}
    L = engine.labels(kb)
    for sid in case["f"]:
        k = group_key(kbname, where[sid])
        st.session_state[k] = list(st.session_state.get(k, [])) + [L[sid]]


def render_result(kb, d, L):
    F = {p["id"]: p["formula"] for p in kb["patterns"]}
    page = kb.get("page", {})
    for msg in d["redflags"]:
        st.error("⚠ " + msg)

    shown = [j for j in d["jing"] if j["score"] > 0]
    if shown:
        with st.container(border=True):
            st.markdown(f"**{page.get('layer1', '第一層')}**")
            mx = max(max(j["score"] for j in d["jing"]), 1)
            for j in shown:
                st.progress(min(j["score"] / mx, 1.0), text=f"{j['name']}　{j['score']:.1f}")
            if len(d["hebing"]) > 1:
                st.caption("合病／並病：" + "、".join(j["name"] for j in d["hebing"]))
            st.caption(d["topJing"]["source"] if d["topJing"] else page.get("layer1none", ""))

    for f in d["rules"]:
        box = st.warning if f["kind"] == "caution" else st.info
        box(f"**原文規則：{f['name']}**" + (f"　→ {f['detail']}" if f["detail"] else "")
            + f"\n\n{f['source']}" + (f"\n\n{f['note']}" if f.get("note") else ""))

    if d["plan"]:
        then = F.get(d["plan"]["then"], "（依裏證）") if d["plan"]["then"] else "（依裏證）"
        st.success(f"**治療次序：先 {F.get(d['plan']['first'])}，後 {then}。**　{d['plan']['note']}\n\n{d['plan']['source']}")

    if not d["ranked"]:
        st.info(strip_tags(page.get("nomatch", "目前的症狀對不上任何證型，請再補充。")))
        return
    st.markdown(f"### 首選：{F.get(d['first'], '—')}")

    for i, r in enumerate(d["ranked"][:3]):
        with st.container(border=True):
            st.markdown(f"**{i + 1}. {r['name']} → {r['formula']}**")
            c1, c2, c3 = st.columns(3)
            c1.metric("得分", f"{r['score']:.1f}")
            c2.metric("符合度", f"{r['fit'] * 100:.0f}%")
            c3.metric("主症", f"{len(r['mainHit'])}/{r['mainTotal']}")
            hits = [L[x] + "（主）" for x in r["mainHit"]] + [L[x] for x in r["minorHit"]]
            if hits:
                st.markdown("命中：" + "、".join(hits))
            if r["against"]:
                st.markdown("不符：" + "、".join(L[a[0]] for a in r["against"]))
            if r["rules"]:
                st.markdown("原文規則加分：" + "、".join(dict.fromkeys(r["rules"])))
            if r["cautions"]:
                st.warning("原文禁忌：" + "、".join(dict.fromkeys(r["cautions"])) + "（此方須由醫師斟酌是否可用）")
            st.caption("出處：" + r["source"])
            for m in r["mods"]:
                st.markdown(f"- 加減［{m['s']}］：{m['do']}　—— {m['why']}")

    if d["questions"]:
        st.markdown("**還需要確認：**")
        for q in d["questions"]:
            st.markdown(f"- {L[q['id']]}（關係到{q['for']}）")


def page_bianzheng():
    names = kb_names()
    kbname = st.radio("知識庫", names, horizontal=True, key="kbname")
    kb = load_kb(kbname)
    page = kb.get("page", {})
    L = engine.labels(kb)

    st.caption(page.get("eyebrow", ""))
    st.title(page.get("title", "辨證選方"))
    st.write(page.get("lede", ""))
    if kbname != "外感":
        st.warning("這個知識庫還在試做，首選命中率低。請把前三名當候選、把「還需要確認」當追問清單。", icon="⚠️")

    left, right = st.columns([5, 6], gap="large")
    with left:
        st.text_input("用口語輸入症狀（空白或逗號分隔，體溫可寫 38度）", key=f"free_{kbname}",
                      placeholder="例：拉肚子 怕冷 胃脹 打嗝", on_change=add_free_text, args=(kbname, kb))
        unknown = st.session_state.get(f"unknown_{kbname}")
        if unknown:
            st.caption("無法對應：" + "、".join(unknown) + "（請改從下方點選）")
        b1, b2 = st.columns(2)
        b1.button("清除全部", on_click=clear_all, args=(kbname, kb), width="stretch")
        sample = next((c for c in kb.get("cases", []) if c["id"] == page.get("sample")), None)
        if sample:
            b2.button("載入示例", on_click=load_sample, args=(kbname, kb, sample), width="stretch")
        if "bure" in L:  # 只有收錄「不發熱」的知識庫（外感）才用體溫
            st.number_input("體溫（℃，未量可留空）", min_value=34.0, max_value=43.0, step=0.1,
                            value=None, key=f"temp_{kbname}")
        for i, g in enumerate(kb["groups"]):
            # 選項直接用症狀名稱（各知識庫內不重複），再對回代號
            st.pills(("⚠ " if g["name"] == "警示" else "") + g["name"], [it[1] for it in g["items"]],
                     selection_mode="multi", key=group_key(kbname, i))

    by_label = {v: k for k, v in L.items()}
    selected = [by_label[x] for i, _ in enumerate(kb["groups"]) for x in st.session_state.get(group_key(kbname, i)) or []]
    temp = st.session_state.get(f"temp_{kbname}")
    with right:
        if not selected and temp is None:
            st.info(strip_tags(page.get("intro", "從左側選擇症狀後，這裡會列出最可能的證型、主方與加減。")))
        else:
            d = engine.diagnose(kb, selected, temp)
            st.caption("已選：" + "、".join(L[x] for x in d["selected"]) + (f"（體溫 {temp}）" if temp else ""))
            render_result(kb, d, L)
        st.caption(DISCLAIMER)

    st.divider()
    with st.expander("自我檢查：預先登錄的驗證題"):
        st.write(page.get("checkIntro", ""))
        for title, ok, n, note, rows in run_checks(kbname):
            st.markdown(f"**{title}：首選命中 {ok}／{n}**")
            if note:
                st.caption(note)
            st.dataframe(rows, hide_index=True, width="stretch")
    with st.expander("限度"):
        for item in limit_items(kb):
            st.markdown("- " + item)


# ── page 2: 典籍原文查詢 ───────────────────────────────────────────────────────
def render_passage(p, maxlen):
    body = p if len(p) <= maxlen else p[:maxlen] + " …（截斷，可調高每段字數）"
    lines = []
    for line in body.split("\n"):
        m = re.match(r"^(#{1,4})\s*(.*)$", line)
        lines.append(f"**{html.escape(m.group(2))}**" if m else html.escape(line))
    st.markdown("  \n".join(x for x in lines if x.strip()))


def page_lookup():
    st.title("典籍原文查詢")
    st.write("查《本草備要》《神農本草經》《本草綱目》《傷寒論》《醫方集解》《溫病條辨》原文。可查藥名、方名，或《傷寒論》條號（如 96）。"
             "異體字與別名會自動對應（耆／芪、參／蔘、山藥／署豫、金銀花→忍冬等）。")
    c1, c2 = st.columns([3, 2])
    q = c1.text_input("藥名、方名或條號", placeholder="例：黃耆、小柴胡湯、96")
    book = c2.selectbox("書", ["全部"] + lookup.BOOKS)
    c3, c4 = st.columns([3, 2])
    rubrics = c3.multiselect("《本草綱目》要看的段落", list(lookup.RUBRICS), default=list(lookup.DEFAULT_RUBRICS))
    maxlen = c4.slider("每段最多字數", 500, 20000, 2500, step=500)
    if not q.strip():
        st.info("輸入後按 Enter 查詢。")
        return
    T = texts()
    roles, results = lookup.search(q, None if book == "全部" else book, tuple(rubrics) or None, read=T.__getitem__)
    if roles:
        order = {"君": 0, "臣": 1, "佐": 2, "使": 3, "反佐": 4}
        groups = {}
        for herb, role in roles["roles"].items():
            groups.setdefault(role, []).append(herb)
        line = "；".join(f"{r}：{'、'.join(hs)}" for r, hs in sorted(groups.items(), key=lambda x: order.get(x[0], 9)))
        msg = f"**《醫方集解·{roles['section']}》原文君臣（已人工核對）**　{line}\n\n原文：{roles['quote']}"
        for k, label in (("alt", "異說"), ("note", "注")):
            if roles.get(k):
                msg += f"\n\n{label}：{roles[k]}"
        st.success(msg + "\n\n（未列出的藥味，原文沒有明說角色。）")
    if not results:
        st.warning("查不到。可以換別名、只輸入關鍵字，或改選「全部」。")
        return
    for b, hits in results:
        st.subheader(f"《{b}》 {len(hits)} 處")
        for i, h in enumerate(hits[:12]):
            first = h.strip().split("\n", 1)[0].lstrip("# ").strip()[:40]
            with st.expander(first or f"第 {i + 1} 處", expanded=(i == 0)):
                render_passage(h, maxlen)
        if len(hits) > 12:
            st.caption(f"另有 {len(hits) - 12} 處未列出，請把關鍵字打得更完整。")
