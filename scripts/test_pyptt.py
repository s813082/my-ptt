#!/usr/bin/env python3
"""
PyPtt 連線 & 留言讀取測試

用法：
  1. 安裝套件：
       pip install PyPtt

  2. 設定環境變數（你的 PTT 帳號密碼）：
       export PTT_ID=你的帳號
       export PTT_PW=你的密碼

  3. 執行指定 test case（或全部）：
       python3 scripts/test_pyptt.py            # 跑全部
       python3 scripts/test_pyptt.py --case 1   # 只測連線
       python3 scripts/test_pyptt.py --case 2 --url https://www.ptt.cc/bbs/Stock/M.1772757002.A.4E5.html
"""

import os
import re
import sys
from collections import Counter

# ── 預設測試文章 URL（Case 2）──────────────────────────────────
DEFAULT_TEST_URL = "https://www.ptt.cc/bbs/Stock/M.1772757002.A.4E5.html"
# ──────────────────────────────────────────────────────────────

def _require_pyptt():
    try:
        import PyPtt
        return PyPtt
    except ImportError:
        print("[錯誤] 請先安裝 PyPtt：pip install PyPtt")
        sys.exit(1)

def _get_credentials():
    ptt_id = os.environ.get("PTT_ID", "").strip()
    ptt_pw = os.environ.get("PTT_PW", "").strip()
    if not ptt_id or not ptt_pw:
        print("[錯誤] 請先設定環境變數 PTT_ID 與 PTT_PW")
        print("  export PTT_ID=你的帳號")
        print("  export PTT_PW=你的密碼")
        sys.exit(1)
    return ptt_id, ptt_pw

# ══════════════════════════════════════════════════════════════
# Test Case 1：連線 / 登入測試
# ══════════════════════════════════════════════════════════════
def test_1_connection():
    """
    驗證能否成功登入 PTT。
    - 登入成功 → 取得 PTT 伺服器時間後立即登出
    - 失敗 → 印出錯誤原因
    """
    print("=" * 60)
    print("Test Case 1：PTT 連線 / 登入測試")
    print("=" * 60)

    PyPtt = _require_pyptt()
    ptt_id, ptt_pw = _get_credentials()
    print(f"[ℹ] 使用帳號：{ptt_id}")

    ptt_bot = PyPtt.API()
    try:
        ptt_bot.login(ptt_id, ptt_pw, kick_other_session=True)
        ptt_time = ptt_bot.get_time()
        print(f"[✅] 登入成功！PTT 伺服器時間：{ptt_time}")
        return True

    except PyPtt.exceptions.WrongIDorPassword:
        print("[❌] 帳號或密碼錯誤，請確認後重試")
        return False
    except PyPtt.exceptions.LoginTooOften:
        print("[❌] 登入太頻繁，請稍後再試（PTT 限制）")
        return False
    except PyPtt.exceptions.LoginError:
        print("[❌] 登入失敗（未知原因）")
        return False
    except Exception as e:
        print(f"[❌] 發生例外：{e}")
        return False
    finally:
        try:
            ptt_bot.logout()
            print("[✅] 已正常登出")
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════
# Test Case 2：從指定 URL 取得完整推文
# ══════════════════════════════════════════════════════════════
def test_2_fetch_comments(url: str = DEFAULT_TEST_URL):
    """
    透過 PyPtt 的 Telnet 連線取得文章完整推文（不受網頁隱藏限制）。
    - 自動從 URL 解析 board + AID
    - 印出每半小時時段的推文數量分佈
    - 印出前 5 則推文的原始資料，確認欄位正確
    """
    print("\n" + "=" * 60)
    print("Test Case 2：從指定 URL 讀取完整推文")
    print(f"  URL: {url}")
    print("=" * 60)

    PyPtt = _require_pyptt()
    ptt_id, ptt_pw = _get_credentials()

    # Stock 板文章常見修改格式，加入自訂結尾讓 PyPtt 能正常解析推文
    from PyPtt import screens
    custom_end = "--\n※ 文章網址"
    if custom_end not in screens.Target.content_end_list:
        screens.Target.content_end_list.append(custom_end)

    ptt_bot = PyPtt.API()
    try:
        ptt_bot.login(ptt_id, ptt_pw, kick_other_session=True)
        print("[✅] 登入成功")

        # ── Step 1: URL → board + AID ─────────────────────────────
        board, aid = ptt_bot.get_aid_from_url(url)
        print(f"[ℹ] 解析結果：看板 = {board}，AID = {aid}")

        # ── Step 2: 取得文章完整資料（含所有推文）────────────────────
        print("[ℹ] 正在讀取文章與推文，請稍候...")
        post_info = ptt_bot.get_post(board, aid=aid)

        title    = post_info.get(PyPtt.PostField.title, "（無標題）")
        comments = post_info.get(PyPtt.PostField.comments, [])

        print(f"[✅] 標題：{title}")
        print(f"[✅] 取得推文：{len(comments)} 則")

        if not comments:
            print("[⚠] 沒有取得任何推文，請確認文章 URL 是否正確")
            return False

        # ── Step 3: 每半小時時段統計 ──────────────────────────────
        slot_counts: Counter = Counter()
        no_time_count = 0

        for c in comments:
            t_raw = c.get(PyPtt.CommentField.time, "")
            t_str = str(t_raw) if t_raw else ""
            m = re.search(r"(\d{1,2}):(\d{2})", t_str)
            if m:
                h  = int(m.group(1))
                mi = int(m.group(2))
                slot = f"{h:02d}:{0 if mi < 30 else 30:02d}"
                slot_counts[slot] += 1
            else:
                no_time_count += 1

        print("\n  ── 每半小時推文數量分佈 ──")
        for slot in sorted(slot_counts.keys()):
            bar = "█" * min(slot_counts[slot] // 5, 40)
            print(f"  {slot}  {slot_counts[slot]:>4} 則  {bar}")
        if no_time_count:
            print(f"  （無時間資訊）  {no_time_count} 則")

        # ── Step 4: 印出前 5 則推文，確認資料結構 ────────────────
        print("\n  ── 前 5 則推文（資料欄位預覽）──")
        for i, c in enumerate(comments[:5], 1):
            ctype   = c.get(PyPtt.CommentField.type,    "?")
            cauthor = c.get(PyPtt.CommentField.author,  "?")
            ccont   = c.get(PyPtt.CommentField.content, "?")
            ctime   = c.get(PyPtt.CommentField.time,    "?")
            print(f"  [{i}] type={ctype}  author={cauthor}  time={ctime}  content={str(ccont)[:40]}")

        return True

    except PyPtt.exceptions.WrongIDorPassword:
        print("[❌] 帳號或密碼錯誤")
        return False
    except PyPtt.exceptions.LoginTooOften:
        print("[❌] 登入太頻繁，請等待約 60 秒後再試")
        return False
    except PyPtt.exceptions.LoginError:
        print("[❌] 登入失敗（登入太频繁或其他原因），請稍後再試")
        return False
    except PyPtt.exceptions.NoSuchBoard:
        print("[❌] 看板不存在，請確認 URL 是否正確")
        return False
    except Exception as e:
        print(f"[❌] 發生例外：{e}")
        return False
    finally:
        try:
            ptt_bot.logout()
            print("\n[✅] 已正常登出")
        except Exception:
            pass

# ══════════════════════════════════════════════════════════════
# 主程式
# ══════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="PyPtt 連線與留言讀取測試")
    parser.add_argument(
        "--url",
        type=str,
        default=DEFAULT_TEST_URL,
        help=f"Case 2 要讀取的文章 URL（預設：{DEFAULT_TEST_URL}）",
    )
    parser.add_argument(
        "--case",
        type=int,
        choices=[1, 2],
        help="只執行指定的 test case (1 或 2)，省略則兩個都跑",
    )
    args = parser.parse_args()

    import time
    results = {}

    if args.case in (None, 1):
        results[1] = test_1_connection()

    if args.case in (None, 2):
        if 1 in results:  # Case 1 剛執行過，稍等避免觸發 PTT 登入頻率限制
            print("\n[ℹ] 等待 20 秒讓 PTT 解除登入頻率限制...")
            time.sleep(20)
        results[2] = test_2_fetch_comments(args.url)

    print("\n" + "=" * 60)
    print("Test 結果摘要")
    print("=" * 60)
    for case_num, ok in sorted(results.items()):
        status = "✅ PASS" if ok else "❌ FAIL"
        print(f"  Case {case_num}: {status}")
