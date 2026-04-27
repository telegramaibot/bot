# === MODIFIED ===
# Telegram Remote UserBot

Remote-controlled Telegram UserBot built with Telethon and aiogram.

## Features

- Telethon userbot on your real Telegram account
- aiogram control bot from any device
- Login/password auth with bcrypt + JWT-backed DB sessions
- Admin commands for user/session management
- Message read/send/forward/search
- Voice note sending with gTTS + ffmpeg
- Media archive and scheduled tasks
- Keyword monitoring and daily reporting

## Quick Start

1. Install Python 3.10+
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Install `ffmpeg` for voice-note conversion.

```bash
apt-get update && apt-get install -y ffmpeg
```
4. Copy `.env.example` to `.env` and fill in values.
5. Run:

```bash
python -m userbot_remote.main
```

## Railway Notes

- For Railway, prefer setting `SESSION_STRING` in environment variables.
- If `SESSION_STRING` is absent, the app falls back to session-file login, which needs interactive code entry on first run.
- Do not commit `.env` or Telethon session files.

## Procfile

The deploy command is already configured:

```text
worker: python -m userbot_remote.main
```
