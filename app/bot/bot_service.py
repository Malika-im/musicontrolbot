"""
Telegram Bot Service.
Handles direct asynchronous communication with Telegram Bot API via HTTPX.
"""

from pathlib import Path
from typing import Any, Dict, Optional
import httpx

from app.core.config import get_settings
from app.core.logging import logger


class TelegramBotService:
    def __init__(self, token: Optional[str] = None):
        self.settings = get_settings()
        self.token = token or self.settings.TELEGRAM_BOT_TOKEN
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def send_message(
        self,
        chat_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "HTML",
    ) -> Optional[Dict[str, Any]]:
        """Send text message to Telegram user."""
        url = f"{self.base_url}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                logger.error(f"Failed to send message: {resp.text}")
                return None
            return resp.json().get("result")

    async def edit_message_text(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        reply_markup: Optional[Dict[str, Any]] = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """Edit an existing Telegram message (e.g. for progress updates)."""
        url = f"{self.base_url}/editMessageText"
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200

    async def send_audio(
        self,
        chat_id: int,
        audio_path: Path,
        caption: Optional[str] = None,
        title: Optional[str] = None,
        performer: Optional[str] = None,
        reply_markup: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Upload and send processed audio file to user."""
        url = f"{self.base_url}/sendAudio"
        data = {
            "chat_id": str(chat_id),
            "parse_mode": "HTML",
        }
        if caption:
            data["caption"] = caption
        if title:
            data["title"] = title
        if performer:
            data["performer"] = performer

        if reply_markup:
            import json
            data["reply_markup"] = json.dumps(reply_markup)

        if not audio_path.exists():
            logger.error(f"Cannot send audio: file not found at {audio_path}")
            return False

        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(audio_path, "rb") as f:
                files = {"audio": (audio_path.name, f, "audio/mpeg")}
                resp = await client.post(url, data=data, files=files)
                if resp.status_code != 200:
                    logger.error(f"Failed to send audio: {resp.text}")
                    return False
                logger.info(f"Successfully sent audio {audio_path.name} to chat {chat_id}")
                return True

    async def send_chat_action(self, chat_id: int, action: str = "upload_voice") -> bool:
        """Display chat action status (e.g. upload_voice, typing, record_voice)."""
        url = f"{self.base_url}/sendChatAction"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json={"chat_id": chat_id, "action": action})
            return resp.status_code == 200

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: Optional[str] = None,
        show_alert: bool = False,
    ) -> bool:
        """Acknowledge inline button press."""
        url = f"{self.base_url}/answerCallbackQuery"
        payload = {"callback_query_id": callback_query_id, "show_alert": show_alert}
        if text:
            payload["text"] = text

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            return resp.status_code == 200

    async def set_webhook(self, webhook_url: str, secret_token: str) -> bool:
        """Register public HTTPS webhook with Telegram."""
        url = f"{self.base_url}/setWebhook"
        payload = {
            "url": webhook_url,
            "secret_token": secret_token,
            "allowed_updates": ["message", "callback_query"],
            "drop_pending_updates": True,
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json=payload)
            data = resp.json()
            logger.info(f"Webhook registration result: {data}")
            return data.get("ok", False)

    async def delete_webhook(self) -> bool:
        """Remove active webhook."""
        url = f"{self.base_url}/deleteWebhook"
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(url, json={"drop_pending_updates": True})
            return resp.status_code == 200
