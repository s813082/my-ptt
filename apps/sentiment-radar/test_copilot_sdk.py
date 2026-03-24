#!/usr/bin/env python3
"""
快速測試 GitHub Copilot SDK 是否可用
執行：python scripts/test_copilot_sdk.py
"""

import asyncio
import sys


async def test():
    print("=== GitHub Copilot SDK 可用性測試 ===\n")

    # Step 1: 確認套件是否安裝
    print("1️⃣  檢查 github-copilot-sdk 套件...")
    try:
        from copilot import CopilotClient, MessageOptions, PermissionHandler, SessionConfig

        print("   ✅ 套件已安裝\n")
    except ImportError:
        print("   ❌ 套件未安裝，請執行：pip install github-copilot-sdk")
        sys.exit(1)

    # Step 2: 確認 copilot CLI 是否在 PATH
    print("2️⃣  檢查 copilot CLI...")
    import shutil

    cli_path = shutil.which("copilot")
    if cli_path:
        print(f"   ✅ 找到 CLI: {cli_path}\n")
    else:
        print("   ❌ 找不到 copilot CLI，請安裝：https://docs.github.com/en/copilot/how-tos/set-up/install-copilot-cli")
        sys.exit(1)

    # Step 3: 嘗試建立連線並送出一則簡單問題
    print("3️⃣  嘗試建立 Copilot Session 並送出測試訊息...")
    print("   (這需要 10~30 秒，請稍候)\n")

    client = CopilotClient()
    session = None
    try:
        await client.start()
        session = await client.create_session(
            SessionConfig(
                model="gpt-4.1",
                on_permission_request=PermissionHandler.approve_all,
            )
        )
        response = await session.send_and_wait(
            MessageOptions(prompt="請只回覆：OK，不要加任何說明。"),
            timeout=60.0,
        )

        # 嘗試從 response 取得文字
        content = None
        if response and response.data and hasattr(response.data, "content"):
            content = response.data.content
        else:
            # 從 messages 取最後一則 assistant 訊息
            messages = await session.get_messages()
            for msg in reversed(messages):
                if msg.type == "assistant.message" and msg.data and msg.data.content:
                    content = msg.data.content
                    break

        if content:
            print(f"   ✅ Copilot 回應：{content.strip()}")
            print("\n🎉 GitHub Copilot SDK 可正常使用！")
        else:
            print("   ⚠️ 連線成功但無法取得回應內容，SDK 可能需要更新")
            sys.exit(1)

    except Exception as e:
        print(f"   ❌ 連線失敗：{e}")
        print("\n可能原因：")
        print("  • 尚未執行 copilot auth login 登入")
        print("  • GitHub Copilot 訂閱未啟用")
        print("  • 網路問題")
        sys.exit(1)
    finally:
        if session:
            await session.destroy()
        await client.stop()


if __name__ == "__main__":
    asyncio.run(test())
