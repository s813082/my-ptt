# PTT 盤中閒聊情緒分析 — 執行記錄

> 日期：2026-03-06
> 執行者：GitHub Copilot
> 目標：從頭到尾完整跑一次「爬蟲 → LLM 分析」流程並記錄每個步驟

---

## 完整流程說明

```
python scripts/main.py [--date YYYY-MM-DD] [--url URL] [--batch-size N]
```

```
開始
  │
  ▼
[週末/平日判斷]
  │  週六/週日 → 😴 非交易日，流程結束（exit 0）
  │  週一~週五 ↓
  ▼
[PTT 搜尋盤中閒聊文章]
  │  找不到 → 📭 休市（國定假日等），流程結束（exit 0）
  │  找到   ↓
  ▼
Step 1：爬蟲抓取留言（scraper.py）
  │  輸出：data/{date}_raw.json
  ▼
Step 2：LLM 情緒分析（analyzer.py）
  │  batch_size=50，逐批送 Copilot SDK → GitHub Models → Gemini（fallback）
  │  輸出：data/{date}.json
  ▼
Step 3：同步到前端
  │  複製至 docs/data/{date}.json + 更新 docs/data/index.json
  │  清理暫存檔 data/{date}_raw.json
  ▼
結束，輸出最終統計
```

---

## 環境確認

| 項目 | 狀態 | 說明 |
|------|------|------|
| Python | ✅ | 已確認可執行 |
| github-copilot-sdk | ✅ | 已安裝 |
| copilot CLI | ✅ | `c:\Users\s8130\AppData\Roaming\Code\User\globalStorage\github.copilot-chat\copilotCli\copilot.BAT` |
| Copilot SDK 連線 | ✅ | test_copilot_sdk.py 測試通過，回應 OK |

---

## 2026-03-06 執行記錄（週五）

### 週期判斷

| 項目 | 結果 |
|------|------|
| 日期 | 2026-03-06（週五）|
| 是否交易日 | ✅ 是，繼續執行 |

### Step 1：搜尋今日文章 URL

| 搜尋結果 | 內容 |
|----------|------|
| 掃描頁數 | 5 頁（index.html → index9805.html）|
| 文章標題 | `[閒聊] 2026/03/06 盤中閒聊` |
| 文章 URL | https://www.ptt.cc/bbs/Stock/M.1772757002.A.4E5.html |
| 狀態 | ✅ 找到文章，確認有開盤 |

### Step 2：爬蟲抓取留言

| 項目 | 數值 |
|------|------|
| 文章頁數 | 1 頁 |
| 原始推文總數 | 1,489 則 |
| 篩選後有效留言 | **1,393 則** |
| 輸出檔案 | `data/2026-03-06_raw.json` |
| 狀態 | ✅ 成功 |

### Step 3：LLM 情緒分析

**LLM 優先順序**：Copilot SDK → GitHub Models → Gemini

#### ❌ 第一次嘗試（batch_size=500）— 失敗

| 批次 | 送出 | 回傳 | 問題 |
|------|------|------|------|
| 1/3 | 500 則 | **50 則** | 輸出被截斷 |
| 2/3 | 500 則 | **50 則** | 輸出被截斷 |
| 3/3 | 393 則 | **50 則** | 輸出被截斷 |

**根本原因**：每批 500 則留言的 prompt 過長，LLM 的輸出 token 上限導致 JSON response 每批只回傳約 50 筆就被截斷。
**修復方案**：將 `batch_size` 從 500 縮小至 50。

#### ✅ 第二次嘗試（batch_size=50）— 成功

| 統計項目 | 數值 |
|----------|------|
| 總批次 | 28 批（27批×50則 + 最後1批×43則）|
| 已分析留言數 | **1,393 則**（全部完整）|
| LLM Provider | Copilot SDK（每批皆成功）|
| 輸出檔案 | `data/2026-03-06.json` |
| 狀態 | ✅ 成功 |

### Step 4：前端同步

| 項目 | 狀態 |
|------|------|
| 初次同步 | ❌ 失敗（`docs/data/` 仍為舊資料，瀏覽器顯示全 neutral）|
| 問題原因 | `main.py` 舊版未自動同步到 `docs/data/`，需手動複製 |
| 修復方式 | 手動複製 + `main.py` 新增自動同步邏輯 |
| 修復後 | ✅ 強制重新整理後頁面正確顯示最新資料 |

### 最終統計（2026-03-06）

| 情緒 | 則數 | 比例 |
|------|------|------|
| 🟢 看多 (bullish) | 411 | 29.5% |
| 🔴 看空 (bearish) | 500 | 35.9% |
| ⚪ 中立 (neutral) | 482 | 34.6% |
| **合計** | **1,393** | **100%** |

**結論**：2026-03-06 PTT 盤中閒聊情緒偏空，看空（35.9%）略高於看多（29.5%）。

---

## 錯誤記錄（完整）

| # | 步驟 | 錯誤描述 | 原因 | 修復方式 | 修改檔案 |
|---|------|----------|------|----------|----------|
| 1 | Copilot SDK 連線 | `CopilotClient` 不支援 `async with` | 舊版用法已廢棄 | 改用 `await client.start()` + `try/finally client.stop()` | `test_copilot_sdk.py`, `analyzer.py` |
| 2 | Copilot SDK 連線 | `create_session` 需要 `on_permission_request` | 必填欄位未傳入 | 加入 `PermissionHandler.approve_all` | 同上 |
| 3 | Copilot SDK 連線 | `create_session` 需傳 `SessionConfig` 型別 | 直接傳 dict 不被接受 | 改用 `SessionConfig(...)` 和 `MessageOptions(...)` | 同上 |
| 4 | LLM 分析截斷 | 每批 500 則但只回傳 50 個結果 | batch_size 過大，LLM output token 上限截斷 JSON | `batch_size` 預設從 500 → 50，上限從 1000 → 100 | `analyzer.py` |
| 5 | 前端顯示舊資料 | 頁面仍顯示全 neutral 舊資料 | `data/` 與 `docs/data/` 兩目錄未同步 | `main.py` 新增自動同步邏輯 | `main.py` |
| 6 | main.py 語法錯誤 | `NameError: name 'args' is not defined` | 重寫 `main.py` 時舊程式碼殘留在 `if __name__` 之後 | 刪除殘留的舊程式碼 | `main.py` |

---

## 程式碼修改摘要

| 檔案 | 修改內容 |
|------|----------|
| `scripts/test_copilot_sdk.py` | 修正 Copilot SDK 用法（3 個 bug）|
| `scripts/analyzer.py` | 同步修正 `call_copilot_sdk()`；預設 batch_size 500→50，上限 1000→100 |
| `scripts/main.py` | 新增週一～週五判斷；找不到文章=休市（exit 0）；自動同步 `docs/data/`；預設 batch-size 500→50 |

---

## 週末/休市測試結果

| 日期 | 星期 | 結果 |
|------|------|------|
| 2026-03-07 | 週六 | ✅ 😴 非交易日，流程結束 |
| 2026-03-08 | 週日 | ✅ 😴 非交易日，流程結束 |


| 項目 | 狀態 | 說明 |
|------|------|------|
| Python | ✅ | 已確認可執行 |
| github-copilot-sdk | ✅ | 已安裝 |
| copilot CLI | ✅ | `c:\Users\s8130\AppData\Roaming\Code\User\globalStorage\github.copilot-chat\copilotCli\copilot.BAT` |
| Copilot SDK 連線 | ✅ | test_copilot_sdk.py 測試通過，回應 OK |

---

## Step 1：搜尋今日文章 URL

**目標日期**：2026-03-06
**搜尋板塊**：PTT Stock
**掃描頁數**：5 頁（index.html → index9805.html）

| 搜尋結果 | 內容 |
|----------|------|
| 文章標題 | `[閒聊] 2026/03/06 盤中閒聊` |
| 文章 URL | https://www.ptt.cc/bbs/Stock/M.1772757002.A.4E5.html |
| 狀態 | ✅ 成功 |

---

## Step 2：爬蟲抓取留言

**文章 URL**：https://www.ptt.cc/bbs/Stock/M.1772757002.A.4E5.html

| 項目 | 數值 |
|------|------|
| 文章頁數 | 1 頁 |
| 原始推文總數 | 1,489 則 |
| 篩選後有效留言 | **1,393 則** |
| 輸出檔案 | `data/2026-03-06_raw.json` |
| 狀態 | ✅ 成功 |

---

## Step 3：LLM 情緒分析

**LLM 優先順序**：Copilot SDK → GitHub Models → Gemini

### ❌ 第一次嘗試（batch_size=500）— 失敗

| 批次 | 送出 | 回傳 | 問題 |
|------|------|------|------|
| 1/3 | 500 則 | **50 則** | 輸出被截斷 |
| 2/3 | 500 則 | **50 則** | 輸出被截斷 |
| 3/3 | 393 則 | **50 則** | 輸出被截斷 |

**根本原因**：每批 500 則留言的 prompt 過長，LLM 的輸出 token 上限導致 JSON response 每批只回傳約 50 筆就被截斷。
**修復方案**：將 `batch_size` 從 500 大幅縮小至 50，確保每批 prompt 及回應都在 token 限制內。

### ✅ 第二次嘗試（batch_size=50）— 成功

共 28 批，全部由 Copilot SDK 回應成功：

| 統計項目 | 數值 |
|----------|------|
| 總批次 | 28 批（27批×50則 + 最後1批×43則）|
| 已分析留言數 | **1,393 則**（全部完整）|
| LLM Provider | Copilot SDK（每批皆成功）|
| 輸出檔案 | `data/2026-03-06.json` |
| 狀態 | ✅ 成功 |

---

## 錯誤記錄

| # | 步驟 | 錯誤描述 | 原因 | 修復方式 |
|---|------|----------|------|----------|
| 1 | Step 3 | 每批 500 則但只回傳 50 個結果 | `batch_size=500` 使 prompt 過長，LLM output token 上限導致 JSON 被截斷 | 將 `batch_size` 從 500 改為 50 |

---

## 最終統計（2026-03-06）

| 情緒 | 則數 | 比例 |
|------|------|------|
| 🟢 看多 (bullish) | 407 | 29.2% |
| 🔴 看空 (bearish) | 502 | 36.0% |
| ⚪ 中立 (neutral) | 484 | 34.7% |
| **合計** | **1,393** | **100%** |

**結論**：今日（2026-03-06）PTT 盤中閒聊情緒偏空，看空（36.0%）略高於看多（29.2%）。

---

## 待改善事項

1. **`batch_size` 預設值應調整**：目前 `analyzer.py` 預設 500，但受 LLM output token 限制，實際上限約 50 則。建議將預設值改為 50，並在 `SYSTEM_PROMPT` 備註。
2. **jieba 未安裝**：文字雲功能跳過，若需要關鍵字分析請執行 `pip install jieba`。

---

## Step 4：前端資料同步（補充修正）

**問題描述**：啟動本地 server（`python -m http.server 8080` 於 `docs/` 目錄）後，頁面顯示的是舊資料，並非剛完成的分析結果。

**根本原因**：

| 路徑 | 內容 |
|------|------|
| `data/2026-03-06.json` | ✅ 最新分析結果（bullish=407, bearish=502, neutral=484, 共 1393 則）|
| `docs/data/2026-03-06.json` | ❌ 舊資料（全部 neutral=1361，批次截斷的殘留結果）|

前端 `app.js` 讀取的是 `./data/`（相對於 `docs/` 的路徑），因此需要將 `data/` 的結果同步到 `docs/data/`。

**修復方式**：手動複製 `data/2026-03-06.json` → `docs/data/2026-03-06.json`

**後續建議**：`main.py` 的流程應在分析完成後，自動將結果同步到 `docs/data/`，而非只寫入 `data/`。

| 項目 | 修正後 |
|------|--------|
| `docs/data/2026-03-06.json` | ✅ 已更新（1393 則，多空正確）|
| 頁面顯示 | ✅ 重新整理後正確顯示最新資料 |

---

## 錯誤記錄（更新）

| # | 步驟 | 錯誤描述 | 原因 | 修復方式 |
|---|------|----------|------|----------|
| 1 | Step 3 | 每批 500 則但只回傳 50 個結果 | `batch_size=500` 使 prompt 過長，LLM output token 上限導致 JSON 被截斷 | `batch_size` 從 500 → 50，上限從 1000 → 100 |
| 2 | Step 4 | 前端顯示舊資料 | 分析器輸出到 `data/`，但 server 讀取 `docs/data/`，兩目錄未同步 | 複製 `data/2026-03-06.json` → `docs/data/2026-03-06.json` |

