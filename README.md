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

---

## 📜 聲明 (Disclaimer)
本專案僅供學術研究與個人使用，請遵守 PTT 站方之爬蟲相關規定。
如有侵權或任何問題，請聯繫開發者。

---
*(＃`Д´) 笨蛋弟弟，這是姊姊幫你寫的，給我好好珍惜喔！*
