# PTT Toolset: 智慧助理與情緒雷達 🚀

本專案是一個整合式的 PTT 自動化工具箱，目前包含「**孫燕姿售票監控**」與「**股票情緒雷達**」兩大核心功能。透過 GitHub Actions 實現全自動排程、AI 分析與即時通知。

---

## 📂 專案架構 (Project Structure)

專案採用模組化設計，所有的核心應用程式皆收納於 `apps/` 目錄下：

```text
.
├── .github/workflows/    # GitHub Actions 排程設定
├── apps/
│   ├── drama-ticket/     # 【模組 1】孫燕姿售票監控
│   └── sentiment-radar/  # 【模組 2】PTT 股票情緒雷達
├── data/                 # 存放情緒雷達分析結果 (JSON)
├── docs/                 # GitHub Pages 網頁展示 (情緒雷達 UI)
│   └── assets/           # 專案相關資源與截圖
├── .gitignore
└── README.md             # 本說明文件
```

---

## 🎯 功能模組 1：孫燕姿售票監控

自動爬取 [PTT Drama-Ticket 看板](https://www.ptt.cc/bbs/Drama-Ticket/index.html)，篩選孫燕姿演唱會售票文章，並透過 Telegram Bot 即時通知。

### 🌟 特色
- **精準篩選**：自動比對標題「售票」與「孫燕姿」，進階標記「5/15、5/17、連號、兩張」等高符合度條件。
- **極速排程**：透過 GitHub Actions 5 組 cron job 實現**每分鐘**掃描一次。
- **智慧防重**：使用 GitHub Actions Cache 記錄已通知的文章。

### 🚀 快速開始
1. **設定 Secrets**：在 GitHub Repo 設定 `TELEGRAM_BOT_TOKEN` 與 `TELEGRAM_CHAT_ID`。
2. **啟動**：Push 後自動執行，或手動執行 `PTT Drama-Ticket Monitor` workflow。
3. **本地測試**：
   ```bash
   cd apps/drama-ticket
   pip install -r requirements.txt
   python scraper.py
   ```

---

## 📈 功能模組 2：PTT 股票情緒雷達

針對 PTT Stock 板「盤中閒聊」文章，利用 AI (Gemini/GitHub Models) 進行情緒分析，並將結果呈現在視覺化網頁上。

### 🌟 特色
- **增量更新**：每半小時自動抓取最新留言，僅分析新數據以節省 Token。
- **AI 驅動**：自動分類留言情緒（Bullish/Bearish/Neutral）。
- **視覺化展示**：自動更新 `docs/` 並透過 GitHub Pages 顯示即時趨勢。

### 🚀 快速開始
1. **設定 Secrets**：設定 `GEMINI_API_KEY` 或 `GITHUB_TOKEN`。
2. **網頁預覽**：[前往專案網頁](https://s813082.github.io/my-ptt/) (請確保已啟用 GitHub Pages)。
3. **本地測試**：
   ```bash
   cd apps/sentiment-radar
   pip install -r requirements.txt
   python main.py
   ```

---

## 🛠️ 開發環境 (Development)

本專案建議使用 Python 3.12+ 進行開發。

### 安裝依賴
```bash
# 建立虛擬環境
python -m venv .venv
source .venv/bin/activate

# 安裝所有模組依賴
pip install -r apps/drama-ticket/requirements.txt
pip install -r apps/sentiment-radar/requirements.txt
```

## ❓ 常見問題 (FAQ)

<details>
<summary><b>Q1：如何設定 Telegram Bot Token 與 Chat ID？</b></summary>

1. **建立 Telegram Bot**：在 Telegram 搜尋 [@BotFather](https://t.me/BotFather)，輸入 `/newbot` 依指示建立，取得 `Bot Token`。
2. **取得 Chat ID**：向剛建立的 Bot 發送任意訊息，然後開啟 `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`，在回傳的 JSON 中找到 `chat.id`。
3. **設定 GitHub Secrets**：
   - 前往你的 GitHub Repo → **Settings** → **Secrets and variables** → **Actions**
   - 點擊 **New repository secret**，分別新增：
     - `TELEGRAM_BOT_TOKEN`：填入 Bot Token
     - `TELEGRAM_CHAT_ID`：填入 Chat ID

</details>

<details>
<summary><b>Q2：Workflow 排程沒有跑？</b></summary>

- **確認 Secrets 已設定**：前往 Settings → Secrets 確認 `TELEGRAM_BOT_TOKEN` 和 `TELEGRAM_CHAT_ID` 已新增。
- **GitHub 排程延遲**：GitHub Actions 的 cron 排程不保證準時，可能有 3~15 分鐘的延遲，這是正常現象。
- **手動觸發測試**：前往 Actions 頁面 → 選擇 Workflow → 點擊 **Run workflow** 手動執行，確認流程是否正常。
- **Fork 的 Repo**：如果是 Fork 來的，需到 Actions 頁面手動啟用 Workflows。

</details>

<details>
<summary><b>Q3：為什麼收不到 Telegram 通知？</b></summary>

- 確認你已經**主動向 Bot 發送過訊息**（Bot 無法主動對未互動的使用者發送訊息）。
- 確認 `TELEGRAM_CHAT_ID` 是正確的數字（個人聊天為正數，群組為負數）。
- 檢查 GitHub Actions 的執行日誌，搜尋 `[ERROR]` 或 `[WARN]` 關鍵字。

</details>

<details>
<summary><b>Q4：如何新增或修改監控的關鍵字？</b></summary>

編輯 `apps/drama-ticket/scraper.py` 中的以下變數：

```python
TITLE_KEYWORDS = ["售票"]          # 標題必須包含的關鍵字
CONTENT_KEYWORDS = ["孫燕姿"]      # 內文必須包含的關鍵字
DATE_KEYWORDS = ["5/15", "5/17"]   # 進階篩選：日期
SEAT_KEYWORDS = ["連號", "兩張"]    # 進階篩選：座位
```

</details>

---

## 📜 聲明 (Disclaimer)
本專案僅供學術研究與個人使用，請遵守 PTT 站方之爬蟲相關規定。
如有侵權或任何問題，請聯繫開發者。

---