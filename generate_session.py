"""
Run this script LOCALLY (not on Railway) to generate a SESSION_STRING.

Usage:
    python generate_session.py

Then copy the printed SESSION_STRING into your Railway environment variables.
"""

import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession


async def main():
    print("=== Telethon SESSION_STRING Generator ===\n")
    api_id   = int(input("API_ID   : ").strip())
    api_hash = input("API_HASH : ").strip()
    phone    = input("PHONE (+998...): ").strip()

    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        await client.send_code_request(phone)
        code = input("Telegram kodi: ").strip()
        try:
            await client.sign_in(phone, code)
        except Exception:
            password = input("2FA paroli: ").strip()
            await client.sign_in(password=password)

        session_string = client.session.save()

    print("\n✅ SESSION_STRING (Railway ga qo'ying):\n")
    print(session_string)
    print("\nRailway → Service → Variables → SESSION_STRING = <yuqoridagi qiymat>")


if __name__ == "__main__":
    asyncio.run(main())
