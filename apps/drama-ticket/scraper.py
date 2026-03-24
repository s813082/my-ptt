"""
PTT Drama-Ticket 孫燕姿演唱會售票監控爬蟲
- 爬取 PTT Drama-Ticket 看板
- 篩選標題含「售票」且內文/標題含「孫燕姿」的文章
- 進一步檢查是否符合 5/15 或 5/17、兩張連號等條件
- 透過 Telegram Bot 發送通知
"""

import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# ── 本地開發：自動載入 .env 檔案（不影響 GitHub Actions）──────────
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

# ── 設定 ─────────────────────────────────────────────
PTT_BASE_URL = "https://www.ptt.cc"
BOARD_URL = f"{PTT_BASE_URL}/bbs/Drama-Ticket/index.html"
COOKIES = {"over18": "1"}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    )
}

# 搜尋關鍵字
TITLE_KEYWORDS = ["售票"]
CONTENT_KEYWORDS = ["孫燕姿"]

# 進階篩選條件（文章內文）
DATE_KEYWORDS = ["5/15", "5/17", "05/15", "05/17", "5月15", "5月17"]
SEAT_KEYWORDS = ["連號", "連座", "兩張", "2張", "二張", "兩位", "一起"]

# Telegram 設定
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# 已通知文章記錄檔（避免重複通知）
SEEN_FILE = Path(__file__).parent / "seen_posts.json"
# 爬取頁數（往前翻幾頁）
MAX_PAGES = 3
# HTTP 重試設定
MAX_RETRIES = 3
RETRY_BACKOFF = 1.5  # 每次重試等待秒數的倍率


# ── 工具函式 ──────────────────────────────────────────

def load_seen_posts() -> set:
    """載入已通知過的文章 ID"""
    if SEEN_FILE.exists():
        try:
            data = json.loads(SEEN_FILE.read_text(encoding="utf-8"))
            return set(data)
        except (json.JSONDecodeError, TypeError):
            print("[WARN] seen_posts.json 格式異常，將重新建立")
            return set()
    return set()


def save_seen_posts(seen: set) -> None:
    """儲存已通知的文章 ID（只保留最新 500 筆）"""
    data = list(seen)[-500:]
    SEEN_FILE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def post_id_from_url(url: str) -> str:
    """從文章 URL 產生唯一 ID"""
    return hashlib.md5(url.encode()).hexdigest()


def fetch_with_retry(url: str, method: str = "GET", **kwargs) -> requests.Response | None:
    """帶有重試機制的 HTTP 請求"""
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.request(
                method, url, headers=HEADERS, cookies=COOKIES, timeout=15, **kwargs
            )
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF * attempt
                print(f"[RETRY] 第 {attempt}/{MAX_RETRIES} 次請求失敗: {e}，{wait:.1f}s 後重試...")
                time.sleep(wait)
            else:
                print(f"[ERROR] 請求失敗已達重試上限 ({MAX_RETRIES} 次): {url}")
                print(f"[ERROR] 最後錯誤: {e}")
                return None


def fetch_page(url: str) -> BeautifulSoup | None:
    """取得頁面並回傳 BeautifulSoup 物件"""
    resp = fetch_with_retry(url)
    if resp is None:
        return None
    return BeautifulSoup(resp.text, "html.parser")


def get_prev_page_url(soup: BeautifulSoup) -> str | None:
    """取得上一頁的連結"""
    btn_group = soup.select("div.btn-group-paging a")
    for btn in btn_group:
        if "上頁" in btn.text:
            href = btn.get("href")
            if href:
                return urljoin(PTT_BASE_URL, href)
    return None


def parse_post_list(soup: BeautifulSoup) -> list[dict]:
    """解析文章列表，回傳含標題與連結的 dict list"""
    posts = []
    entries = soup.select("div.r-ent")
    for entry in entries:
        title_tag = entry.select_one("div.title a")
        if not title_tag:
            continue
        title = title_tag.text.strip()
        href = title_tag.get("href", "")
        url = urljoin(PTT_BASE_URL, href)

        # 取得推文數
        nrec_tag = entry.select_one("div.nrec span")
        nrec = nrec_tag.text.strip() if nrec_tag else "0"

        posts.append({"title": title, "url": url, "nrec": nrec})
    return posts


def matches_title(title: str) -> bool:
    """檢查標題是否包含售票相關關鍵字"""
    return any(kw in title for kw in TITLE_KEYWORDS)


def fetch_post_content(url: str) -> str:
    """取得文章內文純文字"""
    soup = fetch_page(url)
    if not soup:
        return ""
    main_content = soup.select_one("div#main-content")
    if not main_content:
        return ""
    # 移除 metaline（作者/標題/時間）
    for tag in main_content.select("div.article-metaline, div.article-metaline-right"):
        tag.decompose()
    # 移除推文
    for tag in main_content.select("div.push"):
        tag.decompose()
    return main_content.get_text(separator="\n", strip=True)


def matches_content(text: str, title: str) -> bool:
    """檢查標題+內文是否包含孫燕姿"""
    combined = title + " " + text
    return any(kw in combined for kw in CONTENT_KEYWORDS)


def check_advanced_criteria(text: str, title: str) -> dict:
    """進階條件檢查：日期、連號"""
    combined = title + " " + text
    found_dates = [d for d in DATE_KEYWORDS if d in combined]
    found_seats = [s for s in SEAT_KEYWORDS if s in combined]
    return {
        "dates": found_dates,
        "seats": found_seats,
        "is_high_match": bool(found_dates) and bool(found_seats),
    }


def format_telegram_message(post: dict, criteria: dict, content_preview: str) -> str:
    """格式化 Telegram 通知訊息"""
    match_level = "🔥 高度符合" if criteria["is_high_match"] else "📋 可能相關"
    dates_str = ", ".join(criteria["dates"]) if criteria["dates"] else "未明確提到"
    seats_str = ", ".join(criteria["seats"]) if criteria["seats"] else "未明確提到"

    # 內文預覽（最多 500 字）
    preview = content_preview[:500].replace("\n", "\n> ")

    # 取得台灣時間
    tw_tz = timezone(timedelta(hours=8))
    scan_time = datetime.now(tw_tz).strftime("%Y-%m-%d %H:%M:%S")

    msg = (
        f"{match_level}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"⏰ 掃描時間: {scan_time}\n"
        f"📌 {post['title']}\n"
        f"🔗 {post['url']}\n"
        f"👍 推文數: {post['nrec']}\n"
        f"📅 日期關鍵字: {dates_str}\n"
        f"💺 座位關鍵字: {seats_str}\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"📝 內文預覽:\n> {preview}\n"
    )
    return msg


def send_telegram(message: str) -> bool:
    """透過 Telegram Bot 發送純文字訊息"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] 未設定 Telegram Bot Token 或 Chat ID，跳過通知")
        print(f"[INFO] 訊息內容:\n{message}\n")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "disable_web_page_preview": False,
    }
    try:
        resp = requests.post(url, json=payload, timeout=10)
        if resp.status_code == 200:
            print("[OK] Telegram 通知已發送")
            return True
        else:
            print(f"[ERROR] Telegram 回應: {resp.status_code} {resp.text}")
            return False
    except requests.RequestException as e:
        print(f"[ERROR] Telegram 發送失敗: {e}")
        return False


def validate_config() -> bool:
    """啟動時驗證必要設定"""
    ok = True
    if not TELEGRAM_BOT_TOKEN:
        print("[WARN] ⚠️ 環境變數 TELEGRAM_BOT_TOKEN 未設定 — Telegram 通知將被跳過")
        ok = False
    if not TELEGRAM_CHAT_ID:
        print("[WARN] ⚠️ 環境變數 TELEGRAM_CHAT_ID 未設定 — Telegram 通知將被跳過")
        ok = False
    if ok:
        print("[OK] ✅ Telegram 設定驗證通過")
    return ok


# ── 主程式 ───────────────────────────────────────────

def main():
    print("══════════════════════════════════════════════")
    print("🎯 PTT Drama-Ticket 售票監控系統啟動")
    print("══════════════════════════════════════════════")
    print(f"[CONFIG] 目標看板: Drama-Ticket")
    print(f"[CONFIG] 標題篩選: {TITLE_KEYWORDS}")
    print(f"[CONFIG] 內容篩選: {CONTENT_KEYWORDS}")
    print(f"[CONFIG] 進階日期: {DATE_KEYWORDS}")
    print(f"[CONFIG] 進階座位: {SEAT_KEYWORDS}")
    print(f"[CONFIG] 爬取頁數: {MAX_PAGES}")
    print(f"[CONFIG] 重試次數: {MAX_RETRIES}")
    print()

    # 驗證 Telegram 設定
    validate_config()
    print()

    # 載入已通知紀錄
    seen = load_seen_posts()
    print(f"[INIT] 已載入 {len(seen)} 筆已通知文章紀錄")

    # 統計計數器
    stats = {
        "pages_scanned": 0,
        "posts_total": 0,
        "posts_title_match": 0,
        "posts_content_match": 0,
        "posts_high_match": 0,
        "posts_skipped_seen": 0,
        "notifications_sent": 0,
        "notifications_failed": 0,
    }

    new_matches = []
    current_url = BOARD_URL

    print()
    print("── 開始掃描 ──────────────────────────────────")

    for page_num in range(MAX_PAGES):
        print(f"\n📄 [頁面 {page_num + 1}/{MAX_PAGES}] {current_url}")
        soup = fetch_page(current_url)
        if not soup:
            print(f"   ❌ 頁面載入失敗，停止往前翻頁")
            break

        stats["pages_scanned"] += 1
        posts = parse_post_list(soup)
        stats["posts_total"] += len(posts)
        print(f"   📊 本頁共 {len(posts)} 篇文章")

        for post in posts:
            pid = post_id_from_url(post["url"])

            # 跳過已通知的文章
            if pid in seen:
                stats["posts_skipped_seen"] += 1
                continue

            # 第一層篩選：標題含「售票」
            if not matches_title(post["title"]):
                continue

            stats["posts_title_match"] += 1
            print(f"   🔍 [標題符合] {post['title']}")

            # 取得文章內文
            content = fetch_post_content(post["url"])
            time.sleep(0.5)  # 避免請求過快

            # 第二層篩選：內容含「孫燕姿」
            if not matches_content(content, post["title"]):
                print(f"      ↳ 內容不符，跳過")
                continue

            stats["posts_content_match"] += 1
            print(f"   ✅ [內容符合] 孫燕姿相關!")

            # 進階條件檢查
            criteria = check_advanced_criteria(content, post["title"])
            if criteria["is_high_match"]:
                stats["posts_high_match"] += 1
                print(f"   🔥 [高度符合] 日期: {criteria['dates']} / 座位: {criteria['seats']}")

            new_matches.append(
                {
                    "post": post,
                    "criteria": criteria,
                    "content": content,
                }
            )

            # 標記為已看過
            seen.add(pid)

        # 取得上一頁連結
        prev_url = get_prev_page_url(soup)
        if not prev_url:
            print(f"   ℹ️ 已到最後一頁，停止翻頁")
            break
        current_url = prev_url
        time.sleep(0.5)

    # ── 發送通知 ─────────────────────────────────────
    print()
    print("── 通知階段 ──────────────────────────────────")

    if new_matches:
        print(f"🎉 找到 {len(new_matches)} 篇新的符合文章!")
        for i, match in enumerate(new_matches, 1):
            print(f"\n   📨 [{i}/{len(new_matches)}] 發送通知: {match['post']['title']}")
            msg = format_telegram_message(match["post"], match["criteria"], match["content"])
            success = send_telegram(msg)
            if success:
                stats["notifications_sent"] += 1
            else:
                stats["notifications_failed"] += 1
    else:
        print("ℹ️ 本次掃描無新的符合文章")

    # ── 儲存紀錄 ─────────────────────────────────────
    save_seen_posts(seen)

    # ── 統計摘要 ─────────────────────────────────────
    print()
    print("══════════════════════════════════════════════")
    print("📊 本次執行統計摘要")
    print("══════════════════════════════════════════════")
    print(f"   📄 掃描頁數：{stats['pages_scanned']}")
    print(f"   📝 文章總數：{stats['posts_total']}")
    print(f"   ⏭️ 已通知跳過：{stats['posts_skipped_seen']}")
    print(f"   🔍 標題符合：{stats['posts_title_match']}")
    print(f"   ✅ 內容符合：{stats['posts_content_match']}")
    print(f"   🔥 高度符合：{stats['posts_high_match']}")
    print(f"   📨 已發送通知：{stats['notifications_sent']}")
    if stats["notifications_failed"]:
        print(f"   ❌ 通知失敗：{stats['notifications_failed']}")
    print(f"   💾 已通知文章累計：{len(seen)} 篇")
    print("══════════════════════════════════════════════")
    print("✅ 掃描完成")


if __name__ == "__main__":
    main()
