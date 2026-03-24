#!/usr/bin/env python3
"""
#!/usr/bin/env python3

PTT Stock 板「盤中閒聊」傳統網頁爬蟲
- 使用 requests + BeautifulSoup
- 支援重用文章 URL（避免每半小時重複搜尋）
- 支援時間窗增量抓取（since_ts, until_ts）
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

TW_TZ = timezone(timedelta(hours=8))
BOARD = "Stock"
BASE_URL = "https://www.ptt.cc"

def get_html(url):
    """取得網頁內容（含 over18 cookie）"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    cookies = {"over18": "1"}
    try:
        res = requests.get(url, headers=headers, cookies=cookies, timeout=20)
        if res.status_code == 200:
            return res.text
        print(f"[爬蟲] 取得網頁失敗：{url} (status={res.status_code})")
    except Exception as e:
        print(f"[爬蟲] 網路錯誤：{e}")
    return None

def extract_date_from_title(title):
    """從標題提取日期，格式：YYYY/MM/DD"""
    m = re.search(r"(\d{4})/(\d{2})/(\d{2})", title or "")
    if not m:
        return None
    return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

def find_today_chat_url(target_date):
    """搜尋目標日期的盤中閒聊文章 URL"""
    date_token = f"{target_date.year:04d}/{target_date.month:02d}/{target_date.day:02d}"
    query = f"{date_token} 盤中閒聊"
    url = f"{BASE_URL}/bbs/{BOARD}/search?q={query}"

    html = get_html(url)
    if not html:
        return None

    soup = BeautifulSoup(html, "html.parser")
    for ent in soup.select(".r-ent"):
        a = ent.select_one(".title a")
        if not a:
            continue
        title = a.text.strip()
        if "盤中閒聊" not in title:
            continue
        if date_token not in title:
            continue
        href = a.get("href")
        if href:
            return BASE_URL + href
    return None

def _parse_article_title(soup):
    title_meta = soup.select_one('meta[property="og:title"]')
    if title_meta and title_meta.get("content"):
        return title_meta["content"].strip()

    title_node = soup.select_one(".article-metaline .article-meta-value")
    if title_node:
        return title_node.text.strip()
    return ""

def _parse_market_summary(soup):
    content_node = soup.select_one("#main-content")
    if not content_node:
        return None

    text = content_node.get_text("\n", strip=False)
    m = re.search(
        r"台\s*股\s*([\d.]+)\s*[▲▼]\s*([\d.]+)\s*\(([-+]?[\d.]+)%\)",
        text,
    )
    if not m:
        return None
    return {
        "taiex_close": float(m.group(1)),
        "change_points": float(m.group(2)),
        "change_percent": float(m.group(3)),
    }

def parse_comments_from_html(html, target_date):
    """解析 HTML 推文，回傳原始留言（含 timestamp）"""
    soup = BeautifulSoup(html, "html.parser")
    title = _parse_article_title(soup)

    title_date = extract_date_from_title(title)
    if title_date:
        try:
            year = datetime.strptime(title_date, "%Y-%m-%d").year
        except ValueError:
            year = target_date.year
    else:
        year = target_date.year

    comments = []
    for push in soup.select(".push"):
        tag_node = push.select_one(".push-tag")
        user_node = push.select_one(".push-userid")
        content_node = push.select_one(".push-content")
        ipdt_node = push.select_one(".push-ipdatetime")
        if not all([tag_node, user_node, content_node, ipdt_node]):
            continue

        p_type = tag_node.text.strip()
        author = user_node.text.strip()
        content = content_node.text.strip().lstrip(":").strip()
        ipdt = ipdt_node.text.strip()

        tm = re.search(r"(\d{2})/(\d{2})\s+(\d{2}):(\d{2})", ipdt)
        if not tm:
            continue

        month, day, hour, minute = map(int, tm.groups())
        dt = datetime(year, month, day, hour, minute, tzinfo=TW_TZ)

        # 只取目標日期且 14:00 前資料
        if dt.date() != target_date:
            continue
        if dt.hour >= 14:
            continue

        comments.append(
            {
                "type": p_type,
                "author": author,
                "content": content,
                "time": dt.strftime("%H:%M"),
                "timestamp": int(dt.timestamp()),
            }
        )

    comments.sort(key=lambda x: (x.get("timestamp", 0), x.get("author", ""), x.get("content", "")))
    return comments, title, _parse_market_summary(soup)

def _prefilter_comments(raw_comments, since_ts=None, until_ts=None):
    """篩掉無意義留言 + 套用增量時間窗"""
    img_pattern = re.compile(r"^https?://\S+\.(jpg|jpeg|png|gif|webp|bmp)(\?\S*)?$", re.IGNORECASE)
    url_only_pattern = re.compile(r"^https?://\S+$")
    symbol_pattern = re.compile(r"^[\s\W]+$")

    filtered = []
    for c in raw_comments:
        ts = c.get("timestamp")
        if ts is None:
            continue
        if since_ts is not None and ts <= since_ts:
            continue
        if until_ts is not None and ts > until_ts:
            continue

        content = (c.get("content") or "").strip()
        if not content:
            continue
        if len(content) < 3:
            continue
        if img_pattern.match(content):
            continue
        if url_only_pattern.match(content):
            continue
        if symbol_pattern.match(content):
            continue

        item = {
            "type": c.get("type", ""),
            "author": c.get("author", ""),
            "content": content,
            "time": c.get("time", ""),
            "timestamp": ts,
        }
        filtered.append(item)

    filtered.sort(key=lambda x: (x["timestamp"], x.get("author", ""), x.get("content", "")))
    for idx, item in enumerate(filtered, start=1):
        item["id"] = idx
    return filtered

def run_scraper(target_date=None, article_url=None, since_ts=None, until_ts=None):
    """執行爬蟲，支援 URL 重用與增量抓取"""
    if target_date:
        date_obj = datetime.strptime(target_date, "%Y-%m-%d").date()
    else:
        date_obj = datetime.now(TW_TZ).date()

    print(f"[爬蟲] 目標日期：{date_obj}")

    if not article_url:
        article_url = find_today_chat_url(date_obj)
        if not article_url:
            print("[爬蟲] 找不到今日盤中閒聊文章")
            return None

    print(f"[爬蟲] 文章網址：{article_url}")
    html = get_html(article_url)
    if not html:
        return None

    raw_comments, article_title, market_summary = parse_comments_from_html(html, date_obj)
    latest_ts = max((c.get("timestamp", 0) for c in raw_comments), default=None)
    filtered_comments = _prefilter_comments(raw_comments, since_ts=since_ts, until_ts=until_ts)

    return {
        "date": date_obj.isoformat(),
        "article_url": article_url,
        "article_title": article_title,
        "market_summary": market_summary,
        "total_comments_raw": len(raw_comments),
        "total_comments_filtered": len(filtered_comments),
        "latest_timestamp_all": latest_ts,
        "window_since_ts": since_ts,
        "window_until_ts": until_ts,
        "comments": filtered_comments,
        "scraped_at": datetime.now(TW_TZ).isoformat(),
    }

def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="PTT 盤中閒聊網頁爬蟲")
    parser.add_argument("--date", type=str, help="目標日期 YYYY-MM-DD，預設今天")
    parser.add_argument("--url", type=str, help="直接指定文章 URL（跳過搜尋）")
    parser.add_argument("--since-ts", type=int, help="只抓 timestamp > since_ts 的留言")
    parser.add_argument("--until-ts", type=int, help="只抓 timestamp <= until_ts 的留言")
    parser.add_argument("--output", type=str, help="輸出 JSON 路徑")

    args = parser.parse_args()
    result = run_scraper(
        target_date=args.date,
        article_url=args.url,
        since_ts=args.since_ts,
        until_ts=args.until_ts,
    )
    if result is None:
        sys.exit(1)

    if args.output:
        output_path = args.output
    else:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        output_path = os.path.join(data_dir, f"{result['date']}_raw.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[爬蟲] 已輸出：{output_path}")
    print(f"[爬蟲] 本輪有效留言：{result['total_comments_filtered']} 則")

if __name__ == "__main__":
    main()
