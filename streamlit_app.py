"""中藥典籍辨證（單一檔案版）：規則式辨證選方（外感、脾胃）與六部典籍原文查詢。

部署：把這個檔案、requirements.txt 和 10 個資料檔（6 個 .md、4 個 .json）上傳到 GitHub repo，
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
DATA_FILES = (["外感.json", "脾胃.json", "皮膚.json", "醫方集解_君臣.json"]
              + [f"{b}.md" for b in ("本草備要", "神農本草經", "本草綱目", "傷寒論", "醫方集解", "溫病條辨")])


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
    NL = "\n"
    st.error("部署的檔案不完整，找不到：" + NL + NL + NL.join(f"- `{m}`" for m in _missing) + NL + NL
             + "請把 tcm_streamlit_upload 資料夾裡的全部檔案上傳到 GitHub repo。")
    _found = sorted(p.relative_to(ROOT).as_posix() for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts)
    st.markdown("**目前 repo 裡的檔案：**")
    st.code(NL.join(_found[:80]) + (NL + "…" if len(_found) > 80 else ""))
    st.stop()


# ══ 辨證引擎（來自 tcm/engine.py）══════════════════════════════════════════════
MAIN, MINOR = 3, 1.5


def labels(kb):
    return {it[0]: it[1] for g in kb["groups"] for it in g["items"]}


def aliases(kb):
    out = {}
    for g in kb["groups"]:
        for it in g["items"]:
            for a in (it[2] if len(it) > 2 else []):
                out[a] = it[0]
    return out


def with_temp(selected, temp):
    s = list(dict.fromkeys(selected))
    if isinstance(temp, (int, float)):
        def add(x):
            if x not in s:
                s.append(x)

        def drop(x):
            if x in s:
                s.remove(x)
        if temp >= 37.5:
            add("fare"); drop("bure")
        if temp >= 39:
            add("gaore")
        if temp < 37.3:
            add("bure"); drop("fare")
    return s


def cond(w, has):
    if not w:
        return True
    if "all" in w and not all(has(x) for x in w["all"]):
        return False
    if "any" in w and not any(has(x) for x in w["any"]):
        return False
    if "any2" in w and not any(has(x) for x in w["any2"]):
        return False
    if "none" in w and any(has(x) for x in w["none"]):
        return False
    if "unless" in w and any(all(has(x) for x in g) for g in w["unless"]):
        return False
    if "atleast" in w and sum(1 for x in w["atleast"][1] if has(x)) < w["atleast"][0]:
        return False
    return True


def score_pattern(p, has):
    main_hit = [x for x in p["main"] if has(x)]
    minor_hit = [x for x in p["minor"] if has(x)]
    against = [a for a in p["against"] if has(a[0])]
    full = len(p["main"]) * MAIN + len(p["minor"]) * MINOR
    score = len(main_hit) * MAIN + len(minor_hit) * MINOR - sum(a[1] for a in against)
    mods = [m for m in p.get("mods", [])
            if (all(has(x) for x in m["whenAll"]) if m.get("whenAll") else any(has(x) for x in m["when"]))]
    return {"id": p["id"], "name": p["name"], "formula": p["formula"], "source": p["source"],
            "score": score, "base": score, "fit": (max(0, score) / full if full else 0), "full": full,
            "mainHit": main_hit, "mainTotal": len(p["main"]), "minorHit": minor_hit, "against": against,
            "mods": mods, "rules": [], "mainMissing": [x for x in p["main"] if not has(x)], "p": p,
            "gated": False, "ruled": False, "ruleBoost": False, "cautions": []}


def weight_of(p, sid):
    if sid in p["main"]:
        return MAIN
    if sid in p["minor"]:
        return MINOR
    for a in p["against"]:
        if a[0] == sid:
            return -a[1]
    return 0


def diagnose(kb, selected, temp=None):
    sel = with_temp(selected, temp)
    sset = set(sel)
    has = sset.__contains__
    allp = [score_pattern(p, has) for p in kb["patterns"]]
    for r in allp:
        if r["p"].get("gate") and not cond(r["p"]["gate"], has):
            r["gated"] = True
            r["score"] -= 100
    by_id = {r["id"]: r for r in allp}
    fired, asks = [], []

    # 第一層
    jing = []
    for j in kb.get("jing", []):
        if j.get("gate") and not cond(j["gate"], has):
            jing.append({"id": j["id"], "name": j["name"], "score": 0, "hit": [], "source": j["source"], "gated": True})
            continue
        s, hit = 0, []
        for sid, w in j["w"].items():
            if has(sid):
                s += w; hit.append(sid)
        for sid, w in j.get("against", {}).items():
            if has(sid):
                s -= w
        if j.get("explicit") and has(j["explicit"]):
            s += 12; hit.insert(0, j["explicit"])
        jing.append({"id": j["id"], "name": j["name"], "score": s, "hit": hit, "source": j["source"]})
    jing.sort(key=lambda j: -j["score"])  # stable, same as Array.prototype.sort
    jing_by_id = {j["id"]: j for j in jing}
    top_jing = jing[0] if jing and jing[0]["score"] >= 3 else None
    hebing = [j for j in jing if j["score"] >= 5 and j["score"] >= 0.6 * top_jing["score"]] if top_jing else []

    mult, cap = kb.get("jingMult") or 0.6, kb.get("jingCap") or 6
    for r in allp:
        js = [jing_by_id.get(i, {"score": 0})["score"] for i in r["p"].get("jing", [])]
        best = max(js) if js else 0
        if best > 0:
            r["jingBonus"] = min(best * mult, cap)
            r["score"] += r["jingBonus"]
        if best >= 3:
            r["ruled"] = True

    for rule in kb.get("jingRules", []):
        if not top_jing or not (top_jing["id"] == rule["jing"] or any(j["id"] == rule["jing"] for j in hebing)):
            continue
        for pid, v in rule["penalty"].items():
            if pid in by_id:
                by_id[pid]["score"] -= v
                by_id[pid]["cautions"].append(rule["name"])
        fired.append({"id": rule["id"], "kind": "caution", "name": rule["name"], "source": rule["source"],
                      "note": rule.get("note", ""), "detail": "發汗類方劑已降分"})

    for rule in kb.get("rules", []):
        if not cond(rule.get("when"), has):
            continue
        f = {"id": rule["id"], "kind": rule["kind"], "name": rule["name"], "source": rule["source"],
             "note": rule.get("note", ""), "detail": ""}
        if rule["kind"] == "boost":
            for pid, v in rule["boost"].items():
                by_id[pid]["score"] += v
                by_id[pid]["rules"].append(rule["name"])
                if v > 0:
                    by_id[pid]["ruled"] = True; by_id[pid]["ruleBoost"] = True
        elif rule["kind"] == "branch":
            b = next((x for x in rule["branch"] if has(x["if"])), None)
            if b:
                for pid, v in b["boost"].items():
                    by_id[pid]["score"] += v
                    by_id[pid]["rules"].append(rule["name"])
                    if v > 0:
                        by_id[pid]["ruled"] = True; by_id[pid]["ruleBoost"] = True
                f["detail"] = b["text"]
            else:
                f["detail"] = "尚未回答：" + "；".join(x["text"] for x in rule["branch"])
                asks.extend({"id": i, "for": rule["name"]} for i in rule["ask"])
        elif rule["kind"] == "caution":
            for pid, v in rule["penalty"].items():
                if pid in by_id:
                    by_id[pid]["score"] -= v
                    by_id[pid]["cautions"].append(rule["name"])
            f["detail"] = "相關方劑已降分" if len(rule["penalty"]) == 1 else "發汗類方劑已降分"
        elif rule["kind"] == "order":
            f.update(first=rule["first"], then=rule["then"], priority=rule.get("priority", 0))
        fired.append(f)

    def keyed(r):
        key = r["p"].get("key")
        return not key or any(has(x) for x in key)

    def backed(r):
        return bool(not r["gated"] and ((len(r["mainHit"]) > 0 and keyed(r)) or r["ruled"]))

    for r in allp:  # 原文規則加分可越過閘門
        if r["gated"] and r["ruleBoost"]:
            r["gated"] = False; r["score"] += 100; r["gateBypassed"] = True
    ranked = [r for r in allp if not r["gated"] and (backed(r) or r["score"] > 0)]
    ranked.sort(key=lambda r: (-int(backed(r)), -r["score"], -len(r["mainHit"])))
    for r in ranked:
        r["fit"] = max(0, min(r["score"], r["full"])) / r["full"] if r["full"] else 0

    orders = sorted([f for f in fired if f["kind"] == "order"], key=lambda f: -f["priority"])
    plan = None
    if orders:
        o = orders[0]
        top = ranked[0]["id"] if ranked else None
        if o["then"] == "top":
            then = top if (top and top != o["first"]) else (ranked[1]["id"] if len(ranked) > 1 else None)
        else:
            then = o["then"]
        plan = {"first": o["first"], "then": then, "rule": o["name"], "source": o["source"], "note": o["note"]}
    first = plan["first"] if plan else (ranked[0]["id"] if ranked else None)

    top3 = [r["p"] for r in ranked[:3]]
    cand = []
    for p in top3:
        for sid in p["main"] + p["minor"] + [a[0] for a in p["against"]]:
            if sid not in cand:
                cand.append(sid)
    redflags = kb.get("redflags", {})
    sep = []
    for sid in cand:
        if has(sid) or sid in redflags:
            continue
        w = [weight_of(p, sid) for p in top3]
        spread = max(w) - min(w)
        if spread > 0:
            sep.append({"id": sid, "spread": spread, "for": top3[w.index(max(w))]["formula"]})
    sep.sort(key=lambda x: -x["spread"])
    seen, questions = set(), []
    for q in [q for q in asks if not has(q["id"])] + sep:
        if q["id"] not in seen:
            seen.add(q["id"]); questions.append(q)
    questions = questions[:6]

    red = [msg for sid, msg in redflags.items() if has(sid)]
    if has("fare") and has("xie") and has("ou"):
        red.append("發熱又吐瀉，津液耗損快，請少量多次補充水分；若尿少、口乾、頭暈，應就醫。")
    return {"ranked": ranked, "rules": fired, "plan": plan, "first": first, "redflags": red,
            "questions": questions, "selected": sel, "jing": jing, "topJing": top_jing, "hebing": hebing}


def check(kb, cases):
    out = []
    for c in cases:
        d = diagnose(kb, c["f"], c.get("temp"))
        exp = [] if c.get("expect") is None else (c["expect"] if isinstance(c["expect"], list) else [c["expect"]])
        rank = 0
        if c.get("expect") is not None:
            rank = next((i + 1 for i, x in enumerate(d["ranked"]) if x["id"] in exp), 0)
        ok = (d["first"] in exp) if exp else True
        if c.get("expectNot"):
            ok = ok and d["first"] not in c["expectNot"] and not (d["plan"] and d["plan"]["first"] in c["expectNot"])
        if c.get("expectCaution"):
            ok = ok and any(r["kind"] == "caution" for r in d["rules"])
        out.append({"id": c["id"], "label": c.get("label", ""), "text": c.get("text", ""), "expect": exp,
                    "expectNot": c.get("expectNot", []), "expectCaution": bool(c.get("expectCaution")),
                    "ok": ok, "first": d["first"], "rank": rank, "plan": d["plan"]})
    return out


def case_sets(kb):
    """(title, cases, note) for the self-check: cases_vN newest first, then the build self-check."""
    keys = sorted([k for k in kb if k.startswith("cases_v") and k[7:].isdigit()], key=lambda k: -int(k[7:]))
    sets = [(kb[k].get("pageTitle") or kb[k].get("title") or k, kb[k].get("cases", []),
             (kb[k].get("note") or "") + (kb[k].get("result") or "")) for k in keys]
    page = kb.get("page", {})
    sets.append((page.get("casesTitle", "建庫自檢"), kb.get("cases", []), page.get("casesNote", "")))
    return sets


def parse_free_text(kb, text):
    """口語輸入 → 症狀代號；規則與 bianzheng.js 命令列相同。回傳 (ids, temp, unknown)。"""
    import re
    L, A = labels(kb), aliases(kb)
    redflags = kb.get("redflags", {})
    ids, temp, unknown = [], None, []
    for a in re.split(r"[\s,，、;；]+", text.strip()):
        if not a:
            continue
        m = re.fullmatch(r"(\d{2}(?:\.\d)?)(度|℃)?", a)
        if m:
            temp = float(m.group(1)); continue
        if a in L:
            ids.append(a); continue
        # 完全相符的別名優先；其次是輸入中包含的最長別名；最後是包含輸入的最短別名
        inside = sorted([k for k in A if k in a], key=len, reverse=True)
        outside = sorted([k for k in A if a in k], key=len)
        al = a if a in A else (inside[0] if inside else (outside[0] if outside else None))
        if al:
            ids.append(A[al]); continue
        hit = [(i, l) for i, l in L.items() if a in l]
        if not hit:
            unknown.append(a); continue
        plain = [h for h in hit if h[0] not in redflags]
        hit = plain or hit
        starts = [h for h in hit if h[1].startswith(a)]
        ids.append(sorted(starts or hit, key=lambda h: len(h[1]))[0][0])
    return list(dict.fromkeys(ids)), temp, unknown


engine = SimpleNamespace(**{n: globals()[n] for n in ['labels', 'aliases', 'with_temp', 'cond', 'score_pattern', 'weight_of', 'diagnose', 'check', 'case_sets', 'parse_free_text']})
engine.MAIN, engine.MINOR = MAIN, MINOR


# ══ 原文查詢（來自 tcm/lookup.py）══════════════════════════════════════════════
BOOKS = ["本草備要", "神農本草經", "本草綱目", "傷寒論", "醫方集解", "溫病條辨"]
RUBRICS = ("釋名", "集解", "正誤", "修治", "氣味", "主治", "發明", "附方", "附錄")
DEFAULT_RUBRICS = ("氣味", "主治", "發明")

# variant characters / alternate names seen in these editions
VARIANTS = [("耆", "芪"), ("參", "蔘"), ("朮", "術"), ("濕", "溼"), ("黃", "黄"),
            ("鞕", "硬"), ("栝樓", "瓜蔞"), ("栝蔞", "瓜蔞"), ("薑", "姜"), ("麪", "麵"),
            ("癢", "痒"), ("搔", "瘙")]
ALIASES = {"山藥": ["署豫", "薯蕷"], "菊花": ["鞠華", "甘菊花"], "白朮": ["術"], "蒼朮": ["術"],
           "乾地黃": ["地黃"], "生地黃": ["地黃"], "熟地黃": ["地黃"], "玄參": ["元參"],
           "茺蔚子": ["充蔚子"], "旋覆花": ["旋復花"], "枸杞子": ["枸杞"], "地骨皮": ["枸杞"],
           # 本草綱目 古名／併條
           "金銀花": ["忍冬"], "陳皮": ["橘"], "青皮": ["橘"], "川芎": ["芎藭"], "羌活": ["獨活"],
           "蒼耳": ["葈耳", "枲耳"], "蒼耳子": ["葈耳"], "淮山": ["薯蕷", "署豫"], "肉桂": ["桂"],
           "桂枝": ["桂"], "生薑": ["生薑"], "白芍": ["芍藥"], "赤芍": ["芍藥"], "丹皮": ["牡丹"],
           "牡丹皮": ["牡丹"], "杏仁": ["杏"], "桃仁": ["桃"], "酸棗仁": ["酸棗"], "山梔": ["梔子", "巵子"],
           "梔子": ["巵子", "卮子"], "枳實": ["枳"], "枳殼": ["枳"], "葛根": ["葛"]}


def forms(q):
    out = {q}
    for a, b in VARIANTS:
        for s in list(out):
            out |= {s.replace(a, b), s.replace(b, a)}
    for s in list(out):
        out |= set(ALIASES.get(s, []))
    return sorted(out, key=len, reverse=True)


def blocks_by_heading(text):
    """Split into (heading, body) on markdown headings."""
    parts = re.split(r"^(#{1,4} .*)$", text, flags=re.M)
    yield "", parts[0]
    for i in range(1, len(parts), 2):
        yield parts[i], parts[i + 1]


def herb_book(text, qs):
    hits = []
    for h, body in blocks_by_heading(text):
        name = h.lstrip("# ").strip()
        if name and any(name == q or name.startswith(q) for q in qs):
            hits.append(f"{h}\n{body.strip()}")
    return hits


def gangmu(text, qs, rubrics):
    """本草綱目: '## 藥' blocks; '### 部位' and non-rubric '#### 子項' (e.g. 龍骨 under 龍) also match.
    Only the requested rubrics are kept, so a huge entry (人參 ≈ 2 萬字) stays short."""
    lines = text.split("\n")
    level = lambda l: len(l) - len(l.lstrip("#")) if l.startswith("#") and " " in l else 0
    is_rubric = lambda l: l.startswith("#### ") and l[5:].strip() in RUBRICS
    hits, herb, vol = [], "", ""
    for i, l in enumerate(lines):
        lv = level(l)
        if lv == 1:
            vol = l[2:].strip()
        if lv == 2:
            herb = l[3:].strip()
        if lv < 2 or is_rubric(l):
            continue
        name = l.lstrip("# ").strip()
        if not any(name == q or (lv == 2 and name.startswith(q)) for q in qs):
            continue
        j = i + 1
        while j < len(lines) and not (level(lines[j]) and level(lines[j]) <= lv and not is_rubric(lines[j])):
            j += 1
        block = lines[i + 1:j]
        label = f"〔{vol}〕{herb}" + ("" if lv == 2 else f" › {name}")
        out, keep = [label], True
        for b in block:
            if is_rubric(b):
                keep = rubrics is None or b[5:].strip() in rubrics
                if keep:
                    out.append(f"【{b[5:].strip()}】")
            elif b.startswith("#") and level(b):
                keep = True
                out.append(f"〈{b.lstrip('# ').strip()}〉")
            elif keep and b.strip():
                out.append(b)
        hits.append("\n".join(out))
    return hits


def shanghan(text, qs, qnum):
    lines = text.split("\n")
    hits = []
    for i, l in enumerate(lines):
        if qnum and l.startswith(f"【第{qnum}條】"):
            j = i + 1
            while j < len(lines) and not lines[j].startswith("【第") and not lines[j].startswith("#"):
                j += 1
            hits.append("\n".join(lines[i:j]).strip())
        elif not qnum and l.startswith("【第") and any(q in l for q in qs):
            hits.append(l)
        elif not qnum and l.startswith(":;") and any(l[2:].startswith(q) for q in qs):
            j = i + 1
            while j < len(lines) and lines[j].startswith("::"):
                j += 1
            hits.append("【方】" + "\n".join(x.lstrip(":;") for x in lines[i:j]))
    return hits


def yifang(text, qs):
    lines = text.split("\n")
    hits, section = [], ""
    for i, l in enumerate(lines):
        if l.startswith("## "):
            section = l[3:]
        s = l.strip()
        if any(s == q or (s.startswith(q) and s[len(q):len(q) + 1] in "（(") for q in qs):
            j = i + 1
            # entry runs until the next short line that looks like a formula title
            while j < len(lines) and not (re.fullmatch(r"[^，。；：（）\s]{2,10}(湯|散|丸|飲|丹|膏|方|煎)(（[^）]*）)?", lines[j].strip())
                                           or lines[j].startswith("## ")):
                j += 1
            hits.append(f"〔{section}〕\n" + "\n".join(lines[i:j]).strip())
    return hits


def wenbing(text, qs):
    lines = text.split("\n")
    hits, juan = [], ""
    for i, l in enumerate(lines):
        if l.startswith("# "):
            juan = l[2:]
        if re.match(r"^[一二三四五六七八九十百]+、", l) and any(q in l for q in qs):
            hits.append(f"〔{juan}〕{l.strip()}")
        elif l.startswith("【") and any(q in l for q in qs) and l.rstrip().endswith("方】"):
            j = i + 1
            while j < len(lines) and not re.match(r"^([一二三四五六七八九十百]+、|【|#)", lines[j]):
                j += 1
            hits.append(f"〔{juan}〕" + "\n".join(lines[i:j]).strip())
    return hits


# ── 全文搜尋：症狀詞、詞句（癮疹、搔癢、下利清穀…）──────────────────────────────
FULLTEXT_ORDER = ["醫方集解", "傷寒論", "溫病條辨", "本草備要", "神農本草經", "本草綱目"]
_NUM = "一二三四五六七八九十百"
_FORMULA_TITLE = re.compile(r"[^，。；：（）\s]{2,10}(湯|散|丸|飲|丹|膏|方|煎)(（[^）]*）)?")


def segments(book, text):
    """把一部書切成 (所屬條目, 內文) 的清單，供全文搜尋標示出處。

    條目＝標題層級（卷、部、藥名、綱目的段落名），再加各書自己的條目起點：
    《傷寒論》【第N條】與方（:;），《溫病條辨》「一、」條文與【…方】，《醫方集解》方名行。
    內文去掉換行與空白，跨行斷開的詞（如「丹斑／癮疹」）也搜得到。
    """
    segs, stack, entry, buf = [], ["", "", "", ""], "", []

    def flush():
        body = re.sub(r"[ 　]+", "", "".join(x.strip() for x in buf))
        if body:
            label = " › ".join([x for x in stack if x][-3:] + ([entry] if entry else []))
            segs.append((label, body))
        buf.clear()

    for l in text.split("\n"):
        m = re.match(r"^(#{1,4}) (.*)$", l)
        start = None
        if m:
            flush()
            lv = len(m.group(1))
            # 《醫方集解》只有開頭一個「# 序」，各劑是 ##；不讓「序」掛在每條前面
            name = "" if (book == "醫方集解" and lv == 1) else m.group(2).strip()[:30]
            stack[lv - 1:] = [name] + [""] * (4 - lv)
            entry = ""
            continue
        if book == "傷寒論":
            if (n := re.match(r"^【第(\d+)條】", l)):
                start = f"第{n.group(1)}條"
            elif l.startswith(":;"):
                start = l[2:].strip()[:20]
            elif entry.endswith("方") and buf and not l.startswith("::") and l.strip():
                start = ""  # 方後回到正文
        elif book == "溫病條辨":
            if (n := re.match(rf"^([{_NUM}]+)、", l)):
                start = f"第{n.group(1)}條"
            elif l.startswith("【") and l.rstrip().endswith("方】"):
                start = l.strip()[1:-1]
        elif book == "醫方集解" and _FORMULA_TITLE.fullmatch(l.strip()):
            start = l.strip()
        if start is not None:
            flush()
            entry = start
        buf.append(l)
    flush()
    return segs


def fulltext(query, book=None, get_segments=None, context=60, per_entry=3):
    """全文搜尋。回傳 (qs, [(書, [(條目, 次數, [片段…]), …]), …])，依 FULLTEXT_ORDER 排列。

    qs 是實際搜尋的字形（含異體），供呼叫端標示關鍵字。`get_segments(book)` 可傳入快取版本。
    """
    get_segments = get_segments or (lambda b: segments(b, (TEXTS / f"{b}.md").read_text(encoding="utf-8")))
    q = re.sub(r"[\s　]+", "", query)
    if not q:
        return [], []
    qs = forms(q)
    pat = re.compile("|".join(re.escape(x) for x in qs))
    results = []
    for b in ([book] if book else FULLTEXT_ORDER):
        hits = []
        for label, body in get_segments(b):
            ms = list(pat.finditer(body))
            if not ms:
                continue
            wins = []
            for m in ms:
                s, e = max(0, m.start() - context), min(len(body), m.end() + context)
                if wins and s <= wins[-1][1]:
                    wins[-1][1] = e
                else:
                    wins.append([s, e])
            snips = [("…" if s else "") + body[s:e] + ("…" if e < len(body) else "") for s, e in wins]
            if hits and hits[-1][0] == label:  # 同一條目被小標題切開時合併
                hits[-1] = (label, hits[-1][1] + len(ms), hits[-1][2] + snips)
            else:
                hits.append((label, len(ms), snips))
        hits = [(lab, n, list(dict.fromkeys(sn))[:per_entry]) for lab, n, sn in hits]
        if hits:
            results.append((b, hits))
    return qs, results


ROLES_FILE = find_data("醫方集解_君臣.json")


def original_roles(qs):
    """Explicit 君臣佐使 statements from 《醫方集解》 for this formula name (manually reviewed)."""
    if not ROLES_FILE:
        return None
    for f in json.loads(ROLES_FILE.read_text(encoding="utf-8"))["formulas"]:
        if f["formula"] in qs or any(q == f["formula"] for q in qs):
            return f
    return None


def search(query, book=None, rubrics=DEFAULT_RUBRICS, read=None):
    """Structured version of main() for the web app.

    Returns (roles, results): roles is the reviewed 君臣 record or None; results is a list of
    (book, [passages]).  `read` lets the caller supply a cached text reader.
    """
    read = read or (lambda b: find_data(f"{b}.md").read_text(encoding="utf-8"))
    query = query.strip()
    qnum = query if query.isdigit() else None
    qs = forms(query)
    roles = None if qnum else original_roles(qs)
    results = []
    for b in ([book] if book else BOOKS):
        text = read(b)
        if qnum:
            hits = shanghan(text, qs, qnum) if b == "傷寒論" else []
        elif b == "本草綱目":
            hits = gangmu(text, qs, rubrics)
        elif b in ("本草備要", "神農本草經"):
            hits = herb_book(text, qs)
        elif b == "傷寒論":
            hits = shanghan(text, qs, None)
        elif b == "醫方集解":
            hits = yifang(text, qs) if re.search(r"(湯|散|丸|飲|丹|膏|煎|方)$", query) else []
        else:
            hits = wenbing(text, qs)
        if hits:
            results.append((b, hits))
    return roles, results


lookup = SimpleNamespace(**{n: globals()[n] for n in ['forms', 'blocks_by_heading', 'herb_book', 'gangmu', 'shanghan', 'yifang', 'wenbing', 'segments', 'fulltext', 'original_roles', 'search', 'BOOKS', 'RUBRICS', 'DEFAULT_RUBRICS', 'FULLTEXT_ORDER']})


# ══ 頁面（來自 app_pages.py）═══════════════════════════════════════════════════
DISCLAIMER = "以上僅供學習參考，實際用藥請由中醫師面診後處方。"



# ── data ──────────────────────────────────────────────────────────────────────
@st.cache_data
def kb_names():
    order = {"外感": 0, "脾胃": 1, "皮膚": 2}
    return sorted([n for n in order if find_data(f"{n}.json")], key=lambda n: order.get(n, 9))


@st.cache_data
def load_kb(name):
    return json.loads(find_data(f"{name}.json").read_text(encoding="utf-8"))


@st.cache_resource
def texts():
    return {b: find_data(f"{b}.md").read_text(encoding="utf-8") for b in lookup.BOOKS}


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


FT_SHOW = 30  # 每部書最多列出的條目數


def render_fulltext(q, book):
    qs, results = lookup.fulltext(q, None if book == "全部" else book, get_segments=book_segments)
    if not results:
        hint = "「養」應為「癢」？" if "養" in q else "可以換同義詞、異體字，或縮短關鍵字。"
        st.warning(f"六部書的全文都找不到「{q}」。{hint}")
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
    st.write("查《本草備要》《神農本草經》《本草綱目》《傷寒論》《醫方集解》《溫病條辨》原文。"
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
    if not results and not roles:
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


# ── navigation ────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("**中藥典籍辨證**")
    st.caption("原文出自維基文庫公有領域版本。辨證程式是學習用的規則系統，不能取代面診。")
    st.caption(DISCLAIMER)

nav = st.navigation([st.Page(page_bianzheng, title="辨證選方", icon="🩺", default=True),
                     st.Page(page_lookup, title="典籍原文查詢", icon="📖", url_path="lookup")])
nav.run()
