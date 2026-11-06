"""兩個頁面的內容：辨證選方、典籍原文查詢。由 streamlit_app.py 匯入並放進導覽。"""
import html
import json
import re
from pathlib import Path

import streamlit as st

try:
    from tcm import engine, lookup
except ModuleNotFoundError:  # engine.py、lookup.py 直接放在 repo 根目錄時
    import engine
    import lookup

ROOT = Path(__file__).resolve().parent
KB_DIR = ROOT / "data" / "bianzheng"
DISCLAIMER = "以上僅供學習參考，實際用藥請由中醫師面診後處方。"



# ── data ──────────────────────────────────────────────────────────────────────
@st.cache_data
def kb_names():
    order = {"外感": 0, "脾胃": 1, "皮膚": 2, "咳嗽": 3, "失眠": 4, "月經": 5, "免疫": 6}
    return sorted([p.stem for p in KB_DIR.glob("*.json")], key=lambda n: order.get(n, 9))


@st.cache_data
def load_kb(name):
    return json.loads((KB_DIR / f"{name}.json").read_text(encoding="utf-8"))


@st.cache_resource
def texts():
    return {b: (lookup.TEXTS / f"{b}.md").read_text(encoding="utf-8") for b in lookup.BOOKS}


@st.cache_resource
def book_segments(b):
    return lookup.segments(b, texts()[b])


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
    st.session_state[f"parsed_{kbname}"] = None
    st.session_state[f"unknown_{kbname}"] = []
    st.session_state[f"probe_{kbname}"] = []


def answer_probe(kbname, kb, i, ids):
    """追問的回答：把選項對應的症狀加進點選區，並記下這題已答。"""
    where = {it[0]: gi for gi, g in enumerate(kb["groups"]) for it in g["items"]}
    L = engine.labels(kb)
    for sid in ids:
        k = group_key(kbname, where[sid])
        cur = list(st.session_state.get(k) or [])
        if L[sid] not in cur:
            st.session_state[k] = cur + [L[sid]]
    st.session_state[f"probe_{kbname}"] = list(st.session_state.get(f"probe_{kbname}") or []) + [i]


def render_probes(kbname, kb, d):
    pq = engine.pending_probes(kb, d, st.session_state.get(f"probe_{kbname}") or [])
    if not pq:
        return
    with st.container(border=True):
        st.markdown("**線索還不夠，先回答幾個問題（點一下就會重算）：**")
        for i, p in pq:
            st.markdown(p["q"])
            # 依文字長度排成一列、放不下就換行（不再平均切欄，以免長選項被擠成一字一行）
            with st.container(horizontal=True, gap="small"):
                for j, (text, ids) in enumerate(p["opts"]):
                    st.button(text, key=f"pb_{kbname}_{i}_{j}", on_click=answer_probe,
                              args=(kbname, kb, i, ids), width="content")


def add_free_text(kbname, kb):
    r = engine.parse_text(kb, st.session_state.get(f"free_{kbname}", ""))
    ids, temp, unknown = r["ids"], r["temp"], r["unknown"]
    where = {it[0]: i for i, g in enumerate(kb["groups"]) for it in g["items"]}
    L = engine.labels(kb)
    st.session_state[f"parsed_{kbname}"] = {"ok": [L[x] for x in ids], "neg": [L[x] for x in r["negated"]], "hints": r["hints"],
                                             "referrals": r.get("referrals", [])}
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


def render_referrals(kbname, kb, selected):
    """轉介建議（如免疫風濕科）：獨立欄位，不計分，和本科辨證結果分開顯示。"""
    parsed = st.session_state.get(f"parsed_{kbname}") or {}
    msgs = [kb["referrals"][x] for x in selected if x in kb.get("referrals", {})]
    msgs += [m for m in parsed.get("referrals", []) if m not in msgs]
    if not msgs:
        return False
    with st.container(border=True):
        st.markdown(f"#### 🏥 {kb.get('referralTitle', '轉介建議')}")
        st.caption("只做就醫轉介，不做中醫辨證。" if kb.get("referralOnly")
                   else "這一欄與下方的中醫辨證分開，不計分；請先就醫確認，中藥只作輔助。")
        for m in msgs:
            st.warning(m, icon="🏥")
    return True


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

    later = [r for r in d.get("later", []) if r["mainHit"]][:2]
    if later:
        st.markdown("#### 後世醫家用法（另列，非原文主治）")
        st.caption("以下不是典籍原文的方證，而是後世醫家在醫案中的推廣用法，與上方原文證型分開排名，僅供參考。")
        for r in later:
            lt = r["later"]
            with st.container(border=True):
                st.markdown(f"**{r['name']} → {r['formula']}**　｜　{lt['physician']}《{lt['book'].strip('《》')}》")
                hits = [L[x] + "（主）" for x in r["mainHit"]] + [L[x] for x in r["minorHit"]]
                st.markdown("命中：" + "、".join(hits))
                st.caption(lt["note"])
                st.caption("醫案出處：" + r["source"])

    if d["questions"]:
        st.markdown("**還需要確認：**")
        for q in d["questions"]:
            st.markdown(f"- {L[q['id']]}（關係到{q['for']}）")


PILLS_CSS = """<style>
[data-testid="stButtonGroup"] button { max-width: 100%; height: auto; min-height: 2rem; white-space: normal; text-align: left; }
[data-testid="stButtonGroup"] button p, [data-testid="stButtonGroup"] button div { white-space: normal !important; overflow: visible !important; text-overflow: clip !important; overflow-wrap: anywhere; }
</style>"""


def page_bianzheng():
    st.markdown(PILLS_CSS, unsafe_allow_html=True)
    names = kb_names()
    kbname = st.radio("知識庫", names, horizontal=True, key="kbname")
    kb = load_kb(kbname)
    page = kb.get("page", {})
    L = engine.labels(kb)

    st.caption(page.get("eyebrow", ""))
    st.title(page.get("title", "辨證選方"))
    st.write(page.get("lede", ""))
    if kb.get("referralOnly"):
        st.info("這一欄只做就醫轉介篩檢，不做中醫辨證、不選方。", icon="🏥")
    else:
        score = page.get("scoreLine")
        st.warning("這個知識庫還在試做。" + (f"預先登錄的醫案驗證：{score}。" if score else "")
                   + "首選不一定對，請把前三名當候選、把「還需要確認」當追問清單。", icon="⚠️")

    left, right = st.columns([5, 6], gap="large")
    with left:
        st.text_input("用口語描述症狀，可以直接打一整句（體溫可寫 38度），按 Enter 加入", key=f"free_{kbname}",
                      placeholder=page.get("freeExample", "例：最近拉肚子，很怕冷，胃脹還會打嗝，不口渴"),
                      on_change=add_free_text, args=(kbname, kb))
        parsed = st.session_state.get(f"parsed_{kbname}")
        if parsed:
            if parsed["ok"]:
                st.caption("已辨識並加入：" + "、".join(parsed["ok"]))
            if parsed["neg"]:
                st.caption("前面有「不、沒、無」，已略過：" + "、".join(parsed["neg"]))
            for h in parsed["hints"]:
                st.info(h, icon="ℹ️")
        unknown = st.session_state.get(f"unknown_{kbname}")
        if unknown:
            st.caption("認不出：" + "、".join(unknown) + "（可換個說法，或從下方點選）")
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
            st.pills({"警示": "⚠ "}.get(g["name"], "🏥 " if g["items"] and g["items"][0][0] in kb.get("referrals", {}) else "") + g["name"], [it[1] for it in g["items"]],
                     selection_mode="multi", key=group_key(kbname, i))

    by_label = {v: k for k, v in L.items()}
    selected = [by_label[x] for i, _ in enumerate(kb["groups"]) for x in st.session_state.get(group_key(kbname, i)) or []]
    temp = st.session_state.get(f"temp_{kbname}")
    with right:
        if kb.get("referralOnly"):
            for x in selected:
                if x in kb.get("redflags", {}):
                    st.error("⚠ " + kb["redflags"][x])
            shown = render_referrals(kbname, kb, selected)
            if not shown:
                st.info(strip_tags(page.get("nomatch" if selected else "intro", "")))
            st.caption(DISCLAIMER)
        else:
            render_referrals(kbname, kb, selected)
        if kb.get("referralOnly"):
            pass
        elif not selected and temp is None:
            st.info(strip_tags(page.get("intro", "從左側選擇症狀後，這裡會列出最可能的證型、主方與加減。")))
        else:
            d = engine.diagnose(kb, selected, temp)
            st.caption("已選：" + "、".join(L[x] for x in d["selected"]) + (f"（體溫 {temp}）" if temp else ""))
            if any(x in kb.get("normals", {}) for x in d["selected"]):
                st.caption("「正常」選項不計分，只用來略過相關的追問。")
            render_probes(kbname, kb, d)
            render_result(kb, d, L)
        st.caption(DISCLAIMER)

    st.divider()
    if kb.get("referralOnly"):
        with st.expander("限度"):
            for item in limit_items(kb):
                st.markdown("- " + item)
        return
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


FT_SHOW = 30  # 每部書最多列出的條目數


def render_fulltext(q, book):
    qs, results = lookup.fulltext(q, None if book == "全部" else book, get_segments=book_segments)
    if not results:
        hint = "「養」應為「癢」？" if "養" in q else "可以換同義詞、異體字，或縮短關鍵字。"
        st.warning(f"九部書的全文都找不到「{q}」。{hint}")
        return
    pat = re.compile("|".join(re.escape(html.escape(x)) for x in qs))
    total = sum(len(h) for _, h in results)
    st.caption(f"共 {total} 個條目提到「{'／'.join(qs)}」。依《醫方集解》《傷寒論》《溫病條辨》（方書）在前、本草在後排列；"
               "每個條目最多列 3 段上下文。點開條目可看所屬的方或藥。")
    for b, hits in results:
        st.subheader(f"《{b}》 {len(hits)} 個條目、{sum(n for _, n, _ in hits)} 處")
        for label, n, snips in hits[:FT_SHOW]:
            with st.expander(f"{label}（{n} 處）", expanded=(b != "本草綱目" and len(hits) <= 5)):
                for s in snips:
                    st.markdown("> " + pat.sub(lambda m: f"**{m.group(0)}**", html.escape(s)))
        if len(hits) > FT_SHOW:
            st.caption(f"另有 {len(hits) - FT_SHOW} 個條目未列出，可改選單一本書，或加長關鍵字。")


def page_lookup():
    st.title("典籍原文查詢")
    st.write("查《本草備要》《神農本草經》《本草綱目》《傷寒論》《金匱要略》《醫方集解》《溫病條辨》《濟生方》《外科正宗》原文。"
             "異體字與別名會自動對應（耆／芪、參／蔘、癢／痒、搔／瘙、山藥／署豫、金銀花→忍冬等）。")
    mode = st.radio("查詢方式", ["條目（藥名、方名、條號）", "全文（症狀、詞句）"], horizontal=True, key="lk_mode")
    full = mode.startswith("全文")
    c1, c2 = st.columns([3, 2])
    q = c1.text_input("症狀或詞句" if full else "藥名、方名或條號",
                      placeholder="例：癮疹、搔癢、下利清穀" if full else "例：黃耆、小柴胡湯、96")
    book = c2.selectbox("書", ["全部"] + (lookup.FULLTEXT_ORDER if full else lookup.BOOKS))
    if not full:
        c3, c4 = st.columns([3, 2])
        rubrics = c3.multiselect("《本草綱目》要看的段落", list(lookup.RUBRICS), default=list(lookup.DEFAULT_RUBRICS))
        maxlen = c4.slider("每段最多字數", 500, 20000, 2500, step=500)
    if not q.strip():
        st.info("輸入後按 Enter 查詢。" + ("" if full else "查症狀（如「癮疹」）請改選「全文」。"))
        return
    if full:
        render_fulltext(q.strip(), book)
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
    user = lookup.user_records(q)
    if not results and not roles and not user:
        st.info(f"條目裡沒有「{q.strip()}」（條目只收藥名、方名、條號），以下改用全文搜尋。")
        render_fulltext(q.strip(), "全部")
        return
    for b, hits in results:
        st.subheader(f"《{b}》 {len(hits)} 處")
        for i, h in enumerate(hits[:12]):
            first = h.strip().split("\n", 1)[0].lstrip("# ").strip()[:40]
            with st.expander(first or f"第 {i + 1} 處", expanded=(i == 0)):
                render_passage(h, maxlen)
        if len(hits) > 12:
            st.caption(f"另有 {len(hits) - 12} 處未列出，請把關鍵字打得更完整。")
    if user:
        st.subheader("使用者資料合集（非典籍原文）")
        st.caption("以下為使用者自行整理的藥材、醫方資料，已與原文庫核對；「待確認」為疑點，請以典籍原文為準。")
        for k, r in user:
            with st.expander(("藥材：" if k == "herbs" else "醫方：") + (r.get("name") or r.get("formula_name")), expanded=True):
                for line in lookup.format_user(k, r).splitlines():
                    (st.warning if line.startswith("待確認") else st.markdown)(line)
