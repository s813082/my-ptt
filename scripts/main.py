#!/usr/bin/env python3
"""
主程式：盤中半小時增量流程

流程摘要：
1. 09:00 首次執行時搜尋當日盤中閒聊文章，寫入 state 檔
2. 09:30 ~ 14:00 每半小時重用同一篇 URL
3. 每輪只抓上一輪後的新留言，僅分析新留言後合併回當日總檔
"""

import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

# 加入 scripts 目錄到 path
sys.path.insert(0, os.path.dirname(__file__))

from analyzer import aggregate_results, analyze_all_comments
from scraper import run_scraper

TW_TZ = timezone(timedelta(hours=8))


def is_weekday(date_obj=None):
    """判斷是否為週一至週五（0=週一, 6=週日）"""
    if date_obj is None:
        date_obj = datetime.now(TW_TZ).date()
    return date_obj.weekday() < 5


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, payload):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def _comment_key(comment):
    return f"{comment.get('author', '')}|{comment.get('time', '')}|{comment.get('content', '')}"


def _sort_comments(comments):
    def key(c):
        t = str(c.get("time", ""))
        m = None
        if t:
            import re

            m = re.search(r"(\d{2}):(\d{2})$", t)
        if m:
            hh, mm = m.group(1), m.group(2)
            return (int(hh), int(mm), c.get("author", ""), c.get("content", ""))
        return (99, 99, c.get("author", ""), c.get("content", ""))

    comments.sort(key=key)
    return comments


def _current_slot_end_ts(target_date):
    """計算當下對應的半小時槽結束時間戳（台灣時區）"""
    now = datetime.now(TW_TZ)
    if target_date != now.date():
        # 回補歷史日期時，不限制 until
        return None

    minute = 0 if now.minute < 30 else 30
    slot_end = now.replace(minute=minute, second=0, microsecond=0)

    # 限制在 14:00 前
    market_end = datetime(target_date.year, target_date.month, target_date.day, 14, 0, tzinfo=TW_TZ)
    if slot_end > market_end:
        slot_end = market_end

    return int(slot_end.timestamp())


def main():
    import argparse

    parser = argparse.ArgumentParser(description="PTT 盤中閒聊半小時增量分析")
    parser.add_argument("--date", type=str, help="目標日期 YYYY-MM-DD，預設今天")
    parser.add_argument("--url", type=str, help="手動指定文章 URL（會寫入當日 state）")
    parser.add_argument("--batch-size", type=int, default=50, help="每批分析留言數量 (預設 50，建議上限 100)")
    args = parser.parse_args()

    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d").date()
    else:
        target_date = datetime.now(TW_TZ).date()

    if not args.url and not is_weekday(target_date):
        print("😴 非交易日，流程結束")
        sys.exit(0)

    project_root = os.path.dirname(os.path.dirname(__file__))
    data_dir = os.path.join(project_root, "data")
    docs_data_dir = os.path.join(project_root, "docs", "data")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(docs_data_dir, exist_ok=True)

    date_str = target_date.isoformat()
    state_path = os.path.join(data_dir, "runtime_state.json")
    output_path = os.path.join(data_dir, f"{date_str}.json")

    state = _load_json(state_path, {})
    if state.get("date") != date_str:
        state = {"date": date_str, "article_url": "", "last_processed_ts": None}

    if args.url:
        state["article_url"] = args.url.strip()

    until_ts = _current_slot_end_ts(target_date)
    since_ts = state.get("last_processed_ts")

    print("=" * 60)
    print("📡 Step 1: 執行 PTT 增量爬蟲")
    print("=" * 60)
    print(f"[流程] date={date_str}, since_ts={since_ts}, until_ts={until_ts}")

    scrape_result = run_scraper(
        target_date=date_str,
        article_url=state.get("article_url") or None,
        since_ts=since_ts,
        until_ts=until_ts,
    )

    if scrape_result is None:
        print("📭 找不到盤中閒聊文章，流程結束")
        sys.exit(0)

    state["date"] = date_str
    state["article_url"] = scrape_result.get("article_url", "")

    existing = _load_json(output_path, {})
    existing_comments = existing.get("comments", []) if isinstance(existing, dict) else []
    existing_keys = {_comment_key(c) for c in existing_comments}

    incoming = scrape_result.get("comments", [])
    new_comments = []
    for c in incoming:
        k = _comment_key(c)
        if k in existing_keys:
            continue
        existing_keys.add(k)
        new_comments.append(c)

    print(f"[流程] 本輪抓到 {len(incoming)} 則，去重後新增 {len(new_comments)} 則")

    print("\n" + "=" * 60)
    print("🧠 Step 2: 分析新增留言")
    print("=" * 60)

    if new_comments:
        batch_input = []
        for idx, c in enumerate(new_comments, start=1):
            batch_input.append(
                {
                    "id": idx,
                    "type": c.get("type", ""),
                    "author": c.get("author", ""),
                    "content": c.get("content", ""),
                    "time": c.get("time", ""),
                }
            )

        llm_results = analyze_all_comments(batch_input, batch_size=args.batch_size)
        sentiment_map = {
            r.get("id"): r.get("sentiment", "neutral")
            for r in llm_results
            if isinstance(r, dict) and "id" in r
        }

        for i, c in enumerate(new_comments, start=1):
            c["sentiment"] = sentiment_map.get(i, "neutral")
            c.pop("timestamp", None)
    else:
        print("[流程] 本輪沒有新增留言，略過 LLM")

    merged_comments = existing_comments + new_comments
    merged_comments = _sort_comments(merged_comments)
    for idx, c in enumerate(merged_comments, start=1):
        c["id"] = idx

    pseudo_raw = {
        "date": date_str,
        "article_url": state.get("article_url", ""),
        "article_title": scrape_result.get("article_title") or existing.get("article_title", ""),
        "market_summary": scrape_result.get("market_summary") or existing.get("market_summary"),
        "total_comments_raw": max(existing.get("total_comments_raw", 0), scrape_result.get("total_comments_raw", 0)),
        "comments": merged_comments,
        "scraped_at": scrape_result.get("scraped_at", datetime.now(TW_TZ).isoformat()),
    }
    pseudo_results = [{"id": c["id"], "sentiment": c.get("sentiment", "neutral")} for c in merged_comments]
    final_output = aggregate_results(date_str, pseudo_raw, pseudo_results)

    _save_json(output_path, final_output)

    index_payload = {"dates": [date_str]}
    _save_json(os.path.join(data_dir, "index.json"), index_payload)

    shutil.copy2(output_path, os.path.join(docs_data_dir, f"{date_str}.json"))
    _save_json(os.path.join(docs_data_dir, "index.json"), index_payload)

    latest_all = scrape_result.get("latest_timestamp_all")
    if until_ts is not None:
        state["last_processed_ts"] = until_ts
    elif latest_all is not None:
        state["last_processed_ts"] = latest_all
    _save_json(state_path, state)

    s = final_output["sentiment"]
    r = final_output["sentiment_ratio"]
    print("\n" + "=" * 60)
    print(f"📊 當日累計統計（{date_str}）")
    print("=" * 60)
    print(f"   🟢 看多：{s['bullish']:>5} 則  ({r['bullish_pct']}%)")
    print(f"   🔴 看空：{s['bearish']:>5} 則  ({r['bearish_pct']}%)")
    print(f"   ⚪ 中立：{s['neutral']:>5} 則  ({r['neutral_pct']}%)")
    print(f"   合計：{final_output['total_comments_analyzed']} 則")

    github_output = os.environ.get("GITHUB_OUTPUT")
    if github_output:
        with open(github_output, "a", encoding="utf-8") as f:
            f.write(f"date={date_str}\n")
            f.write(f"output_path={output_path}\n")


if __name__ == "__main__":
    main()

