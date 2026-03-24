#!/usr/bin/env python3
"""
LLM 情緒分析器
- 支援 GitHub Copilot SDK (優先) + GitHub Models API (次選) + Google Gemini API (備援)
- 批次送出留言分析 (500~1000 則/批)
- 產出每日情緒統計 JSON
"""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

TW_TZ = timezone(timedelta(hours=8))

# ──────────────────────────────────────────────
# LLM Provider 介面
# ──────────────────────────────────────────────

SYSTEM_PROMPT = """你是台股情緒分析師。你將收到一批 PTT 盤中閒聊的留言，請逐一判斷每則留言的投資情緒。

分類標準（僅根據留言文字內容判斷，不考慮推/噓類型）：
- bullish：看多、認為會漲、加碼、抄底、樂觀、開心賺錢
- bearish：看空、認為會跌、出場、恐慌、悲觀、賠錢抱怨
- neutral：閒聊、無關股市、純梗圖文字、問問題、無法判斷

回覆規則：
1. 只回覆一個 JSON 物件，不要加任何說明文字
2. 格式：{"results": [{"id": 1, "sentiment": "bullish"}, {"id": 2, "sentiment": "bearish"}, ...]}
3. id 必須與輸入的 id 一致
4. sentiment 只能是 bullish / bearish / neutral 三者之一"""


def build_user_prompt(comments_batch):
    """建構 user prompt，傳入一批留言"""
    comments_for_prompt = [{"id": c["id"], "content": c["content"]} for c in comments_batch]
    return f"留言列表：\n{json.dumps(comments_for_prompt, ensure_ascii=False)}"


# GitHub Models 備援模型清單，依序嘗試。
# 格式：(model_id, supports_json_mode)
# supports_json_mode=True 表示可傳 response_format={"type":"json_object"}（僅 OpenAI 系列支援）
_GITHUB_MODELS_FALLBACK = [
    ("openai/gpt-4.1", True),
    ("openai/gpt-4.1-mini", True),
    ("meta/Llama-3.3-70B-Instruct", False),
    ("microsoft/Phi-4", False),
]

_TEMPERATURE_UNSUPPORTED_HINTS = [
    "unsupported value",
    "temperature",
]
_TEMPERATURE_DEFAULT_ONLY_HINTS = [
    "only the default",
    "default (1)",
]


def _is_temperature_unsupported_error(exc):
    """判斷是否為模型不支援自訂 temperature 的錯誤"""
    err = str(exc).lower()
    status_code = getattr(exc, "status_code", None)
    if status_code != 400:
        return False
    if not all(hint in err for hint in _TEMPERATURE_UNSUPPORTED_HINTS):
        return False
    return any(hint in err for hint in _TEMPERATURE_DEFAULT_ONLY_HINTS)


def call_github_models(prompt, system_prompt):
    """
    呼叫 GitHub Models API (OpenAI 相容格式)
    需要環境變數：GITHUB_TOKEN，且 workflow 需設定 models:read 權限。
    若某模型回傳 403（無存取權）或 429（請求過多），自動切換下一個備援模型。
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("[分析] openai 套件未安裝，跳過 GitHub Models")
        return None

    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("[分析] GITHUB_TOKEN 未設定，跳過 GitHub Models")
        return None

    client = OpenAI(
        base_url="https://models.github.ai/inference",
        api_key=token,
    )

    for model, supports_json_mode in _GITHUB_MODELS_FALLBACK:
        try:
            kwargs = dict(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
            )
            if supports_json_mode:
                kwargs["response_format"] = {"type": "json_object"}

            try:
                response = client.chat.completions.create(**kwargs)
            except Exception as e:
                is_temperature_unsupported = (
                    _is_temperature_unsupported_error(e)
                    and "temperature" in kwargs
                )
                if is_temperature_unsupported:
                    kwargs.pop("temperature", None)
                    print(f"[分析] GitHub Models 模型 {model} 不支援自訂 temperature，改用預設值重試...")
                    response = client.chat.completions.create(**kwargs)
                else:
                    raise

            print(f"[分析] GitHub Models 使用模型: {model}")
            return response.choices[0].message.content
        except Exception as e:
            # openai.APIStatusError carries a numeric status_code; fall back to
            # string matching for other HTTP client wrappers that may not.
            status_code = getattr(e, "status_code", None)
            err_str = str(e)
            is_403 = status_code == 403 or (
                status_code is None and ("403" in err_str or "no_access" in err_str or "No access" in err_str)
            )
            is_429 = status_code == 429 or (
                status_code is None and ("429" in err_str or "too many requests" in err_str.lower())
            )
            if is_403:
                print(f"[分析] GitHub Models 模型 {model} 無存取權限 (403)，嘗試下一個備援模型...")
                continue
            if is_429:
                print(f"[分析] GitHub Models 模型 {model} 請求過多 (429)，嘗試下一個備援模型...")
                continue
            print(f"[分析] GitHub Models API 錯誤 ({model}): {e}")
            return None

    print("[分析] GitHub Models: 所有備援模型均無法存取，請確認 GITHUB_TOKEN 擁有 models:read 權限")
    return None


def call_copilot_sdk(prompt, system_prompt):
    """
    呼叫 GitHub Copilot SDK
    需要：pip install github-copilot-sdk 且 copilot CLI 已安裝並認證
    """
    try:
        import asyncio

        from copilot import CopilotClient, MessageOptions, PermissionHandler, SessionConfig
    except ImportError:
        print("[分析] github-copilot-sdk 套件未安裝，跳過 Copilot SDK")
        return None

    async def _run():
        client = CopilotClient()
        session = None
        try:
            await client.start()
            session = await client.create_session(
                SessionConfig(
                    model="gpt-4.1",
                    system_message={"mode": "append", "content": system_prompt},
                    on_permission_request=PermissionHandler.approve_all,
                )
            )
            response = await session.send_and_wait(MessageOptions(prompt=prompt), timeout=120.0)
            if response and response.data and hasattr(response.data, "content"):
                return response.data.content
            # 若 send_and_wait 回傳的是 session.idle 事件，從 messages 中取最後一則 assistant 訊息
            messages = await session.get_messages()
            for msg in reversed(messages):
                if msg.type == "assistant.message" and msg.data and msg.data.content:
                    return msg.data.content
            return None
        finally:
            if session:
                await session.destroy()
            await client.stop()

    try:
        return asyncio.run(_run())
    except Exception as e:
        print(f"[分析] Copilot SDK 錯誤: {e}")
        return None


def call_gemini(prompt, system_prompt):
    """
    呼叫 Google Gemini API
    需要環境變數：GEMINI_API_KEY
    """
    try:
        import google.generativeai as genai
    except ImportError:
        print("[分析] google-generativeai 套件未安裝，跳過 Gemini")
        return None

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("[分析] GEMINI_API_KEY 未設定，跳過 Gemini")
        return None

    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel(
            "gemini-2.0-flash",
            system_instruction=system_prompt,
        )

        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"[分析] Gemini API 錯誤: {e}")
        return None


def _is_ci_environment():
    """偵測是否在 CI 環境（GitHub Actions 等），CI 環境無法使用 Copilot SDK"""
    return bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))


def call_llm(prompt, system_prompt, max_retries=3):
    """
    呼叫 LLM：Copilot SDK 優先（本機）→ GitHub Models → Gemini
    在 CI/GitHub Actions 環境下，Copilot SDK 需要本機 CLI 登入，無法使用，自動跳過。
    """
    if _is_ci_environment():
        providers = [
            ("GitHub Models", call_github_models),
            ("Gemini", call_gemini),
        ]
    else:
        providers = [
            ("Copilot SDK", call_copilot_sdk),
            ("GitHub Models", call_github_models),
            ("Gemini", call_gemini),
        ]

    for attempt in range(max_retries):
        for name, fn in providers:
            print(f"[分析] 嘗試 {name}...")
            result = fn(prompt, system_prompt)
            if result:
                print(f"[分析] ✅ {name} 回應成功")
                return result
            print(f"[分析] ⚠️ {name} 失敗，嘗試下一個")

        if attempt < max_retries - 1:
            wait = (attempt + 1) * 5
            print(f"[分析] 所有 API 均失敗，{wait} 秒後重試 ({attempt + 1}/{max_retries})...")
            time.sleep(wait)

    print("[分析] 錯誤：所有 LLM API 均呼叫失敗")
    return None


# ──────────────────────────────────────────────
# 解析 LLM 回應
# ──────────────────────────────────────────────


def parse_llm_response(response_text):
    """
    解析 LLM 回傳的 JSON

    Returns:
        list[dict]: [{"id": 1, "sentiment": "bullish"}, ...]
    """
    if not response_text:
        return []

    # 移除 Markdown code block（Gemini 常回傳 ```json ... ```）
    cleaned = re.sub(r"```(?:json)?\s*", "", response_text).strip().rstrip("`").strip()

    def _extract(text):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                for key in ["results", "data", "sentiments", "analysis"]:
                    if key in data and isinstance(data[key], list):
                        return data[key]
                if "id" in data and "sentiment" in data:
                    return [data]
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
        return None

    # 直接解析
    result = _extract(cleaned)
    if result is not None:
        return result

    # 從文字中提取 JSON 物件 {"results": [...]}
    obj_match = re.search(r"\{[\s\S]*\}", cleaned)
    if obj_match:
        result = _extract(obj_match.group())
        if result is not None:
            return result

    # 從文字中提取 JSON 陣列 [...]
    arr_match = re.search(r"\[[\s\S]*\]", cleaned)
    if arr_match:
        result = _extract(arr_match.group())
        if result is not None:
            return result

    print(f"[分析] 警告：無法解析 LLM 回應，前 200 字：{response_text[:200]}")
    return []


# ──────────────────────────────────────────────
# 批次分析
# ──────────────────────────────────────────────


def analyze_batch(comments_batch):
    """分析一批留言"""
    prompt = build_user_prompt(comments_batch)
    response = call_llm(prompt, SYSTEM_PROMPT)
    results = parse_llm_response(response)
    return results


def analyze_all_comments(comments, batch_size=50):
    """
    分批分析所有留言

    Args:
        comments: 留言列表（已篩選過）
        batch_size: 每批數量 (預設 50，建議 50~100；因 LLM output token 上限，超過 100 易截斷)

    Returns:
        list[dict]: 每則留言的分析結果
    """
    if not comments:
        print("[分析] 沒有留言需要分析")
        return []

    batch_size = min(batch_size, 100)
    total = len(comments)
    all_results = []

    print(f"[分析] 開始分析 {total} 則留言（每批 {batch_size} 則）")

    for i in range(0, total, batch_size):
        batch = comments[i : i + batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"[分析] 處理第 {batch_num}/{total_batches} 批 ({len(batch)} 則)...")

        results = analyze_batch(batch)

        if results:
            all_results.extend(results)
            print(f"[分析] 第 {batch_num} 批完成，取得 {len(results)} 個結果")
        else:
            print(f"[分析] 第 {batch_num} 批失敗，標記為 neutral")
            for c in batch:
                all_results.append({"id": c["id"], "sentiment": "neutral"})

        # rate limiting: 批次間等待
        if i + batch_size < total:
            time.sleep(3)

    return all_results


# ──────────────────────────────────────────────
# 統計彙總
# ──────────────────────────────────────────────


def aggregate_results(date_str, raw_data, analysis_results):
    """
    將分析結果彙總成每日 JSON 格式
    """
    # 建立 id → sentiment 映射
    sentiment_map = {}
    for r in analysis_results:
        if isinstance(r, dict) and "id" in r and "sentiment" in r:
            sentiment_map[r["id"]] = r["sentiment"]

    # 統計
    counts = {"bullish": 0, "bearish": 0, "neutral": 0}
    intraday = {}  # "HH:MM" -> {bullish, bearish, neutral}

    # 完整保留原始的所有留言與資料結構
    comments = raw_data.get("comments", [])
    for comment in comments:
        cid = comment.get("id")
        sentiment = sentiment_map.get(cid, "neutral")

        # 驗證 sentiment 值
        if sentiment not in ("bullish", "bearish", "neutral"):
            sentiment = "neutral"

        # 原地直接幫把情緒寫回那則留言
        comment["sentiment"] = sentiment
        counts[sentiment] += 1

        # 按 30 分鐘時段統計
        time_str = comment.get("time", "")
        slot = None
        if time_str:
            time_match = re.search(r"(\d{2}):(\d{2})", time_str)
            if time_match:
                h = int(time_match.group(1))
                m = int(time_match.group(2))
                # 四捨五入到最近的 30 分鐘
                m_slot = 0 if m < 30 else 30
                slot = f"{h:02d}:{m_slot:02d}"

        if slot:
            if slot not in intraday:
                intraday[slot] = {"bullish": 0, "bearish": 0, "neutral": 0}
            intraday[slot][sentiment] += 1

    # 補齊盤中所有 30 分鐘時段（09:00 ~ 13:30），確保圖表顯示完整交易日時間軸
    TRADING_SLOTS = [
        f"{h:02d}:{m:02d}"
        for h in range(9, 14)
        for m in (0, 30)
        if h < 13 or (h == 13 and m <= 30)
    ]
    for slot in TRADING_SLOTS:
        if slot not in intraday:
            intraday[slot] = {"bullish": 0, "bearish": 0, "neutral": 0}

    total = counts["bullish"] + counts["bearish"] + counts["neutral"]
    total = max(total, 1)  # 避免除零

    # 生成文字雲 (使用 jieba 取 Top 50 關鍵字)
    try:
        import jieba
        import jieba.analyse

        # 設定停用詞 (簡單過濾一些常見無意義詞彙)
        stop_words = set(
            ["真的", "就是", "還是", "不是", "到底", "什麼", "這樣", "怎麼", "可以", "這個", "那個", "覺得", "現在", "大家", "今天", "明天"]
        )

        all_text = " ".join([c.get("content", "") for c in comments])
        # 提取關鍵字 (tf-idf)
        keywords = jieba.analyse.extract_tags(all_text, topK=60, withWeight=True)

        word_cloud = []
        for word, weight in keywords:
            if word not in stop_words and len(word) > 1:
                # 簡單縮放權重，讓前端好畫
                word_cloud.append({"word": word, "count": int(weight * 100)})
                if len(word_cloud) >= 50:
                    break
    except ImportError:
        print("[分析] 警告：jieba 未安裝，略過文字雲生成")
        word_cloud = []

    # 產出最終 JSON
    output = {
        "date": date_str,
        "article_url": raw_data.get("article_url", ""),
        "article_title": raw_data.get("article_title", ""),
        "market_summary": raw_data.get("market_summary"),
        "total_comments_raw": raw_data.get("total_comments_raw", 0),
        "total_comments_analyzed": len(comments),
        "sentiment": counts,
        "sentiment_ratio": {
            "bullish_pct": round(counts["bullish"] / total * 100, 1),
            "bearish_pct": round(counts["bearish"] / total * 100, 1),
            "neutral_pct": round(counts["neutral"] / total * 100, 1),
        },
        "intraday_sentiment": [{"slot": s, **intraday[s]} for s in sorted(intraday.keys())],
        "word_cloud": word_cloud,
        "comments": comments,  # 完整保留原本含有 author 等欄位的留言，並加上了 sentiment
        "scraped_at": raw_data.get("scraped_at", ""),
        "analyzed_at": datetime.now(TW_TZ).isoformat(),
    }

    return output


# ──────────────────────────────────────────────
# 主程式
# ──────────────────────────────────────────────


def run_analyzer(input_path, output_path=None, batch_size=500):
    """
    執行分析主流程

    Args:
        input_path: 爬蟲輸出的 raw JSON 路徑
        output_path: 最終分析結果 JSON 路徑
        batch_size: 每批分析數量
    """
    # 讀取爬蟲資料
    with open(input_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    date_str = raw_data.get("date", "unknown")
    comments = raw_data.get("comments", [])

    print(f"[分析] 載入 {date_str} 的資料，共 {len(comments)} 則留言")

    # 執行 LLM 分析
    results = analyze_all_comments(comments, batch_size=batch_size)

    # 彙總結果
    output = aggregate_results(date_str, raw_data, results)

    # 決定輸出路徑
    if output_path is None:
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        os.makedirs(data_dir, exist_ok=True)
        output_path = os.path.join(data_dir, f"{date_str}.json")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"[分析] 結果已儲存至: {output_path}")
    print(
        f"[分析] 多空統計: 🟢 看多 {output['sentiment']['bullish']} | "
        f"🔴 看空 {output['sentiment']['bearish']} | "
        f"⚪ 中立 {output['sentiment']['neutral']}"
    )
    print(
        f"[分析] 比例: 看多 {output['sentiment_ratio']['bullish_pct']}% | "
        f"看空 {output['sentiment_ratio']['bearish_pct']}% | "
        f"中立 {output['sentiment_ratio']['neutral_pct']}%"
    )

    return output


def main():
    """CLI 入口"""
    import argparse

    parser = argparse.ArgumentParser(description="PTT 盤中閒聊情緒分析")
    parser.add_argument("--input", type=str, required=True, help="爬蟲輸出的 raw JSON 檔案路徑")
    parser.add_argument("--output", type=str, help="分析結果 JSON 輸出路徑")
    parser.add_argument("--batch-size", type=int, default=50, help="每批分析留言數量 (預設 50，建議上限 100)")

    args = parser.parse_args()

    run_analyzer(args.input, args.output, args.batch_size)


if __name__ == "__main__":
    main()
