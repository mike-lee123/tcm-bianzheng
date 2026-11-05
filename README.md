# 中藥典籍辨證（Streamlit 版）

兩個頁面：

- **辨證選方**：規則式辨證，知識庫有「外感」（v1.5）與「脾胃」（v0.3，試做、首選命中率低）。可點選症狀，或用口語輸入（如「拉肚子 怕冷 38度」）。
- **典籍原文查詢**：《本草備要》《神農本草經》《本草綱目》《傷寒論》《醫方集解》《溫病條辨》原文；方劑會附《醫方集解》原文君臣。

原文出自維基文庫公有領域版本。辨證程式是學習用的規則系統，不能取代面診；實際用藥請由中醫師面診後處方。

## 檔案

| 檔案 | 用途 |
|---|---|
| `streamlit_app.py` | 主程式（頁面設定與導覽） |
| `app_pages.py` | 兩個頁面的內容 |
| `tcm/engine.py` | 辨證引擎（由 JS 版移植，`parity_test.py` 逐題比對過） |
| `tcm/lookup.py` | 原文查詢 |
| `data/` | 典籍原文、辨證知識庫、原文君臣 |
| `requirements.txt` | 套件需求 |
| `test_app.py` | 自動測試（兩個頁面都會跑一遍） |

## 在自己電腦上執行

```bash
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## 部署到 Streamlit Community Cloud（免費）

1. 在 GitHub 建一個新的 repository（建議 Public），把這個資料夾裡的**所有檔案**上傳到 repo 的根目錄，包括 `data/`、`tcm/`、`.streamlit/` 資料夾。
   - 網頁上傳：repo 頁面按「Add file → Upload files」，把資料夾內容整個拖進去，按「Commit changes」。
   - 或用指令：
     ```bash
     git init
     git add .
     git commit -m "first version"
     git branch -M main
     git remote add origin https://github.com/<你的帳號>/<repo 名稱>.git
     git push -u origin main
     ```
2. 到 <https://share.streamlit.io>，用 GitHub 帳號登入。
3. 按「Create app」→「Deploy a public app from GitHub」，填入：
   - Repository：`<你的帳號>/<repo 名稱>`
   - Branch：`main`
   - Main file path：`streamlit_app.py`
   - App URL：可以自訂子網域，例如 `tcm-bianzheng`（網址會是 `https://tcm-bianzheng.streamlit.app`）
   - Advanced settings → Python version 選 3.11 或 3.12
4. 按「Deploy」，等一兩分鐘安裝完成就有網址。

### 關於「永久有效」

- 網址會一直有效，只要 GitHub repo 和 Streamlit 帳號還在。
- 免費方案的 app 一段時間沒人使用會進入休眠；之後有人開啟網址時，頁面會出現喚醒按鈕，按下後約 30 秒到 1 分鐘恢復，網址不變。
- 之後修改程式或知識庫，只要把新檔案推到 GitHub，網站會自動更新。

## 更新知識庫

知識庫的正本在 tcm-classics skill 的 `references/bianzheng/`。更新後把 `外感.json`、`脾胃.json` 複製到 `data/bianzheng/`，若引擎也改過，先執行：

```bash
python parity_test.py <skill 目錄>/assets/bianzheng_engine.js
python test_app.py
```

兩者都通過再推上 GitHub。
