"""Smoke test with Streamlit's AppTest: both pages render and a diagnosis runs without exceptions."""
import sys
from streamlit.testing.v1 import AppTest
sys.stdout.reconfigure(encoding="utf-8")

at = AppTest.from_file("streamlit_app.py", default_timeout=60).run()
assert not at.exception, at.exception
print("page1 title:", [t.value for t in at.title])
at.text_input[0].input("拉肚子 怕冷 頭痛 38度").run()
assert not at.exception, at.exception
print("after free text:", [m.value[:30] for m in at.markdown if m.value.startswith("### 首選")])
at.radio[0].set_value("脾胃").run()
assert not at.exception, at.exception
at.text_input[0].input("胃脹 打嗝 胃酸 口苦 壓力大").run()
assert not at.exception, at.exception
print("脾胃:", [m.value[:30] for m in at.markdown if m.value.startswith("### 首選")])
at.radio[0].set_value("皮膚").run()
assert not at.exception, at.exception
at.text_input[0].input("我皮膚長疹好幾年，晚上更癢，會脫皮，不會流水").run()
assert not at.exception, at.exception
first = [m.value for m in at.markdown if m.value.startswith("### 首選")]
assert first and "當歸飲子" in first[0], first
print("皮膚:", first)
cap = [c.value for c in at.caption if c.value.startswith(("已辨識", "前面有"))]
assert any("夜間癢甚" in c for c in cap) and any("滲水" in c for c in cap), cap
print("皮膚 parsed:", cap)
next(b for b in at.button if b.label == "清除全部").click().run()
at.text_input[0].input("終年皮膚長疹搔癢").run()
assert any("線索還不夠" in m.value for m in at.markdown), "probe box missing"
at.button(key="pb_皮膚_0_1").click().run()   # 乾燥、脫屑
assert not at.exception, at.exception
first = [m.value for m in at.markdown if m.value.startswith("### 首選")]
print("皮膚 after probe:", first)
assert "當歸飲子" in first[0], first
at.text_input[0].input("濕疹").run()
assert any("濕疹" in i.value for i in at.info), [i.value for i in at.info]
at.radio[0].set_value("咳嗽").run()
assert not at.exception, at.exception
at.text_input[0].input("咳嗽兩個月，痰白很多，胃口差，容易累").run()
assert not at.exception, at.exception
first = [m.value for m in at.markdown if m.value.startswith("### 首選")]
assert first and "六君子" in first[0], first
print("咳嗽:", first)
at.text_input[0].input("咳了兩個月，喉嚨乾癢，吃很多止咳藥都沒效").run()
assert not at.exception, at.exception
assert any("後世醫家用法" in m.value for m in at.markdown), "later section missing"
print("咳嗽 後世:", [m.value[:30] for m in at.markdown if "葉天士" in m.value][:1])
at.radio[0].set_value("失眠").run()
at.text_input[0].input("想太多睡不著，心悸，容易累，胃口差").run()
assert not at.exception, at.exception
first = [m.value for m in at.markdown if m.value.startswith("### 首選")]
assert first and "歸脾" in first[0], first
print("失眠:", first)
at.radio[0].set_value("月經").run()
at.text_input[0].input("經前乳房脹，易怒，月經不規則，口苦").run()
assert not at.exception, at.exception
first = [m.value for m in at.markdown if m.value.startswith("### 首選")]
assert first and "逍遙" in first[0], first
print("月經:", first)
at.switch_page("streamlit_app.py") if False else None
at2 = AppTest.from_file("streamlit_app.py", default_timeout=60)
at2.run()
at2.switch_page("streamlit_app.py")
print("ok")

def lookup_page():
    import app_pages
    app_pages.page_lookup()

at3 = AppTest.from_function(lookup_page, default_timeout=120).run()
assert not at3.exception, at3.exception
at3.text_input[0].input("四逆湯").run()
assert not at3.exception, at3.exception
print("lookup roles:", [s.value[:40] for s in at3.success])
print("lookup books:", [h.value for h in at3.subheader])
at3.text_input[0].input("黃耆").run()
assert not at3.exception, at3.exception
print("黃耆 books:", [h.value for h in at3.subheader])
at3.text_input[0].input("96").run()
print("96 books:", [h.value for h in at3.subheader])
at3.text_input[0].input("癮疹").run()  # 條目查不到 → 自動改全文
assert not at3.exception, at3.exception
assert any("改用全文" in i.value for i in at3.info), [i.value for i in at3.info]
print("癮疹 fallback:", [h.value for h in at3.subheader])
at3.radio[0].set_value("全文（症狀、詞句）").run()
at3.text_input[0].input("搔養").run()
assert not at3.exception, at3.exception
assert any("癢" in w.value for w in at3.warning), [w.value for w in at3.warning]
at3.text_input[0].input("搔癢").run()
assert not at3.exception, at3.exception
assert at3.subheader[0].value.startswith("《醫方集解》"), at3.subheader[0].value
print("搔癢 full:", [h.value for h in at3.subheader])
at3.radio[0].set_value("條目（藥名、方名、條號）").run()
at3.text_input[0].input("當歸飲子").run(); assert not at3.exception, at3.exception
assert any(h.value.startswith("《濟生方》") for h in at3.subheader), [h.value for h in at3.subheader]
at3.radio[0].set_value("全文（症狀、詞句）").run()
at3.text_input[0].input("唇風").run(); assert not at3.exception, at3.exception
assert any(h.value.startswith("《外科正宗》") for h in at3.subheader), [h.value for h in at3.subheader]
print("new books ok")
at3.radio[0].set_value("條目（藥名、方名、條號）").run()
at3.text_input[0].input("阿膠").run(); assert not at3.exception, at3.exception
assert any("使用者資料合集" in h.value for h in at3.subheader), [h.value for h in at3.subheader]
assert any("駱駝" in w.value for w in at3.warning)
at3.text_input[0].input("撥雲退翳丸").run(); assert not at3.exception, at3.exception
assert any("使用者資料合集" in h.value for h in at3.subheader)
print("user data ok")
print("消風散 quote:", [m.value[:60] for m in at3.markdown if "**搔癢**" in m.value][:1], "OK")

# 免疫風濕科轉介：獨立欄位，不混進皮膚警示
at4 = AppTest.from_file("streamlit_app.py", default_timeout=90).run()
at4.radio[0].set_value("皮膚").run()
at4.text_input[0].input("牛皮癬 蝴蝶斑 關節腫痛 很癢").run(); assert not at4.exception, at4.exception
assert any("免疫風濕科就醫建議" in m.value for m in at4.markdown), "referral box missing"
assert len([w for w in at4.warning if "過敏免疫風濕科" in w.value]) == 3, [w.value[:20] for w in at4.warning]
assert not any("免疫" in e.value for e in at4.error), "referral leaked into red flags"
assert not any("乾癬" in i.value for i in at4.info), "referral leaked into hints"
print("referral box ok")

# 免疫：獨立欄位，只做轉介
at5 = AppTest.from_file("streamlit_app.py", default_timeout=90).run()
assert "免疫" in at5.radio[0].options, at5.radio[0].options
at5.radio[0].set_value("免疫").run(); assert not at5.exception, at5.exception
assert any("免疫風濕科就醫轉介" in t.value for t in at5.title)
at5.text_input[0].input("臉頰紅斑 關節腫痛 吃類固醇 胸痛").run(); assert not at5.exception, at5.exception
assert len([w for w in at5.warning if "🏥" in str(w.icon) or "免疫" in w.value]) >= 3, [w.value[:20] for w in at5.warning]
assert any("急診" in e.value for e in at5.error)
assert not any(m.value.startswith("### 首選") for m in at5.markdown), "referral-only tab must not diagnose"
print("免疫 tab ok")
