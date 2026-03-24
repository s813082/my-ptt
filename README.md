# PTT Drama-Ticket 孫燕姿售票監控

自動爬取 [PTT Drama-Ticket 看板](https://www.ptt.cc/bbs/Drama-Ticket/index.html)，篩選孫燕姿演唱會售票文章，透過 Telegram Bot 即時通知。

目標條件：**5/15 或 5/17、兩張連號**

## 篩選邏輯

| 層級 | 條件 | 說明 |
|------|------|------|
| 第一層 | 標題含「售票」 | 快速過濾非售票文 |
| 第二層 | 標題或內文含「孫燕姿」 | 進入文章全文比對 |
| 進階標記 | 含日期（5/15、5/17）＋座位（連號、兩張）| 標記為 🔥 高度符合 |

## 排程機制

5 個 cron job 彼此差 1 分鐘，效果等同**每分鐘掃描一次**：

```
cron 1: :00, :05, :10 ...
cron 2: :01, :06, :11 ...
cron 3: :02, :07, :12 ...
cron 4: :03, :08, :13 ...
cron 5: :04, :09, :14 ...
```

## seen_posts.json 說明

記錄已通知過的文章（防重複發送），透過 **GitHub Actions Cache** 在各次執行間持久保存，**不存入 git repo**。

| 事項 | 說明 |
|------|------|
| 存放位置 | GitHub Actions Cache（非 git） |
| 保存期限 | 7 天未使用自動過期 |
| 手動清空 | Repo → Actions → Caches → 刪除 `seen-posts-` 系列 |

## 快速開始

### 1. 建立 Telegram Bot

1. Telegram 搜尋 **@BotFather** → `/newbot` → 取得 Token
2. 對 Bot 傳任意訊息後，開啟以下網址取得 Chat ID：
   ```
   https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates
   ```
   回傳 JSON 中 `message.chat.id` 即為 Chat ID。

### 2. 設定 GitHub Secrets

Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Secret 名稱 | 說明 |
|---|---|
| `TELEGRAM_BOT_TOKEN` | BotFather 給的 Token |
| `TELEGRAM_CHAT_ID` | 你的 Chat ID（數字） |

### 3. Push 後 Actions 自動啟用

可到 Actions 頁面手動點 **Run workflow** 立即測試。

## 本地測試

```bash
# 建立虛擬環境
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 建立 .env（不會被 push）
cat > .env << EOF
TELEGRAM_BOT_TOKEN=你的Token
TELEGRAM_CHAT_ID=你的ChatID
EOF

# 執行（自動讀取 .env）
python scraper.py

# 重置記錄（強制重新通知所有文章）
rm seen_posts.json && python scraper.py
```

## 通知格式

```
🔥 高度符合
━━━━━━━━━━━━━━━━
📌 [售票] 孫燕姿5/17 $4380*2連號
🔗 https://www.ptt.cc/bbs/Drama-Ticket/M.xxxxxxx.html
👍 推文數: 2
📅 日期關鍵字: 5/17
💺 座位關鍵字: 連號
━━━━━━━━━━━━━━━━
📝 內文預覽:
> 節目：孫燕姿 時間：5月17日 18:30 張數：2（連號）...
```

## 自訂篩選條件

編輯 [scraper.py](scraper.py) 頂部常數：

```python
TITLE_KEYWORDS   = ["售票"]
CONTENT_KEYWORDS = ["孫燕姿"]
DATE_KEYWORDS    = ["5/15", "5/17", "5月15", "5月17"]
SEAT_KEYWORDS    = ["連號", "兩張", "2張", "連座"]
MAX_PAGES        = 10   # 往前爬幾頁
```

## 檔案結構

```
.
├── .github/
│   └── workflows/
│       └── check-ptt.yml   # GitHub Actions（5-cron 每分鐘排程）
├── .env                    # 本地憑證（.gitignore，不 push）
├── .gitignore
├── README.md
├── requirements.txt
└── scraper.py              # PTT 爬蟲主程式
```
