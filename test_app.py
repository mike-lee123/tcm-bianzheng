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
print("96 books:", [h.value for h in at3.subheader], "OK")
