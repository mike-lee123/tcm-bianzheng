"""Compare the Python engine with the JS engine of the tcm-classics skill.

Usage: python parity_test.py <path to bianzheng_engine.js>
Runs every registered case plus 500 random symptom sets per knowledge base through both engines
and compares the first choice, full ranking, scores, fired rules, follow-up questions and red flags.
"""
import json, random, subprocess, sys, tempfile
from pathlib import Path
sys.stdout.reconfigure(encoding="utf-8")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from tcm import engine  # noqa: E402

JS = Path(sys.argv[1]).resolve()
NODE = r"""
const B=require(process.argv[2]);const fs=require("fs");
const kb=JSON.parse(fs.readFileSync(process.argv[3],"utf8"));const inputs=JSON.parse(fs.readFileSync(process.argv[4],"utf8"));
const out=inputs.map(([f,t])=>{const d=B.diagnose(kb,f,{temp:t===null?undefined:t});
 return {first:d.first??null,ranked:d.ranked.map(r=>[r.id,Math.round(r.score*1000)/1000]),rules:d.rules.map(r=>r.id+":"+(r.detail||"")),
 q:d.questions.map(q=>q.id+">"+q.for),red:d.redflags,plan:d.plan?[d.plan.first,d.plan.then??null]:null,jing:d.jing.map(j=>[j.id,j.score]),probes:B.pendingProbes(kb,d).map(([i])=>i),later:d.later.map(r=>[r.id,Math.round(r.score*1000)/1000])};});
fs.writeFileSync(process.argv[5],JSON.stringify(out));
"""

def py_out(kb, f, t):
    d = engine.diagnose(kb, f, t)
    return {"first": d["first"], "ranked": [[r["id"], round(r["score"] * 1000) / 1000] for r in d["ranked"]],
            "rules": [r["id"] + ":" + (r["detail"] or "") for r in d["rules"]],
            "q": [q["id"] + ">" + q["for"] for q in d["questions"]], "red": d["redflags"],
            "plan": [d["plan"]["first"], d["plan"]["then"]] if d["plan"] else None,
            "jing": [[j["id"], j["score"]] for j in d["jing"]],
            "probes": [i for i, _ in engine.pending_probes(kb, d)],
            "later": [[r["id"], round(r["score"] * 1000) / 1000] for r in d["later"]]}

bad_total = 0
for kbp in sorted((HERE / "data" / "bianzheng").glob("*.json")):
    kb = json.loads(kbp.read_text(encoding="utf-8"))
    inputs = [(c["f"], c.get("temp")) for _, cs, _ in engine.case_sets(kb) for c in cs]
    ids = list(engine.labels(kb))
    rnd = random.Random(7)
    for _ in range(500):
        inputs.append((rnd.sample(ids, rnd.randint(1, 9)), rnd.choice([None, None, 36.8, 37.6, 38.5, 39.2])))
    with tempfile.TemporaryDirectory() as td:
        ip, op, sp = Path(td) / "in.json", Path(td) / "out.json", Path(td) / "run.js"
        ip.write_text(json.dumps(inputs, ensure_ascii=False), encoding="utf-8")
        sp.write_text(NODE, encoding="utf-8")
        subprocess.run(["node", str(sp), str(JS), str(kbp), str(ip), str(op)], check=True)
        js = json.loads(op.read_text(encoding="utf-8"))
    bad = 0
    for (f, t), j in zip(inputs, js):
        p = py_out(kb, f, t)
        if p != j:
            bad += 1
            if bad <= 3:
                print("MISMATCH", kbp.stem, f, t)
                for k in p:
                    if p[k] != j[k]:
                        print("  ", k, "py=", p[k], "\n   ", k, "js=", j[k])
    # 不印各題組成績：凍結前執行本檔也不會看到驗證題分數（皮膚 v0.2 曾因此先看到總分）
    print(f"{kbp.stem}: {len(inputs)} inputs, mismatches {bad}")
    bad_total += bad

    # 口語解析：Python parse_text 與 JS parseText 逐句比對
    tab = engine.phrase_table(kb)
    words = list(tab) + list(kb.get("hints", {})) + list(kb.get("referralHints", {})) + ["吃什麼", "怎麼辦", "而且", "我", "還會", "38.5度", "39度", "37"]
    texts = list(words) + ["苔", "渴", "痛", "熱", ""]
    for _ in range(600):
        parts = [rnd.choice(["", "", "很", "不", "沒有", "更"]) + rnd.choice(words) for _ in range(rnd.randint(1, 6))]
        texts.append(rnd.choice(["", " ", "，", "、"]).join(parts))
    with tempfile.TemporaryDirectory() as td:
        ip, op, sp = Path(td) / "in.json", Path(td) / "out.json", Path(td) / "run.js"
        ip.write_text(json.dumps(texts, ensure_ascii=False), encoding="utf-8")
        sp.write_text('const B=require(process.argv[2]);const fs=require("fs");'
                      'const kb=JSON.parse(fs.readFileSync(process.argv[3],"utf8"));'
                      'const t=JSON.parse(fs.readFileSync(process.argv[4],"utf8"));'
                      'fs.writeFileSync(process.argv[5],JSON.stringify(t.map(x=>{const r=B.parseText(kb,x);'
                      'return {...r,temp:r.temp===undefined?null:r.temp};})));', encoding="utf-8")
        subprocess.run(["node", str(sp), str(JS), str(kbp), str(ip), str(op)], check=True)
        js = json.loads(op.read_text(encoding="utf-8"))
    pbad = 0
    for t, j in zip(texts, js):
        p = engine.parse_text(kb, t)
        if p != j:
            pbad += 1
            if pbad <= 3:
                print("PARSE MISMATCH", kbp.stem, repr(t), "\n   py=", p, "\n   js=", j)
    print(f"{kbp.stem}: parse {len(texts)} texts, mismatches {pbad}")
    bad_total += pbad
sys.exit(1 if bad_total else 0)
