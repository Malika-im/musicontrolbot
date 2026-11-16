"""
Audio Download Service.
Handles downloading audio files from Telegram Bot API and external safe URLs (SSRF protected).
"""

from pathlib import Path
from typing import Tuple
import httpx

from app.core.config import get_settings
from app.core.exceptions import AudioValidationError, SSRFSecurityError
from app.core.logging import logger
from app.core.security import validate_safe_url


class AudioDownloadService:
    def __init__(self):
        self.settings = get_settings()

    async def download_telegram_file(self, file_id: str, destination_path: Path) -> Path:
        """
        Download a file from Telegram using Bot API.
        """
        base_api = f"https://api.telegram.org/bot{self.settings.TELEGRAM_BOT_TOKEN}"
        file_info_url = f"{base_api}/getFile?file_id={file_id}"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(file_info_url)
            if resp.status_code != 200:
                logger.error(f"Telegram getFile error: {resp.text}")
                raise AudioValidationError("Не удалось получить информацию о файле от Telegram.")

            data = resp.json()
            if not data.get("ok"):
                raise AudioValidationError(f"Telegram API вернул ошибку: {data.get('description')}")

            file_path_tg = data["result"]["file_path"]
            download_url = f"https://api.telegram.org/file/bot{self.settings.TELEGRAM_BOT_TOKEN}/{file_path_tg}"

            # Stream download
            async with client.stream("GET", download_url) as stream_resp:
                if stream_resp.status_code != 200:
                    raise AudioValidationError("Ошибка при скачивании файла из Telegram.")

                bytes_downloaded = 0
                with open(destination_path, "wb") as f:
                    async for chunk in stream_resp.aiter_bytes(chunk_size=65536):
                        bytes_downloaded += len(chunk)
                        if bytes_downloaded > self.settings.max_file_size_bytes:
                            destination_path.unlink(missing_ok=True)
                            raise AudioValidationError(
                                f"Файл слишком большой (> {self.settings.MAX_FILE_SIZE_MB} МБ)."
                            )
                        f.write(chunk)

        logger.info(f"Downloaded Telegram file {file_id} ({bytes_downloaded} bytes) to {destination_path}")
        return destination_path

    async def download_from_external_url(self, url: str, destination_path: Path) -> Tuple[Path, str]:
        """
        Download audio from an external HTTP/HTTPS URL with SSRF protection.
        Returns (destination_path, detected_filename).
        """
        # Step 1: Validate initial URL against SSRF
        validate_safe_url(url)

        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            current_url = url
            # Manually handle redirects up to 3 times to validate each hop against SSRF
            redirect_count = 0
            while redirect_count < 3:
                resp = await client.get(current_url)
                if resp.is_redirect:
                    redirect_target = resp.headers.get("location")
                    if not redirect_target:
                        raise SSRFSecurityError("Перенаправление без целевого адреса.")
                    # Re-validate redirect target
                    validate_safe_url(redirect_target)
                    current_url = redirect_target
                    redirect_count += 1
                else:
                    break

            # Check HTTP Status
            if resp.status_code != 200:
                raise AudioValidationError(
                    f"Сервер источника вернул статус {resp.status_code}",
                    "Не удалось скачать аудио по ссылке. Сервер источника недоступен."
                )

            # Check content-type header
            content_type = resp.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise AudioValidationError(
                    "Ссылка ведет на веб-страницу, а не на прямой аудиофайл.",
                    "По указанной ссылке находится веб-страница, а не прямой аудиофайл. Отправьте прямую ссылку на трек."
                )

            # Check content-length header if present
            content_length = resp.headers.get("content-length")
            if content_length and int(content_length) > self.settings.max_file_size_bytes:
                raise AudioValidationError(
                    f"Размер файла по ссылке ({int(content_length)} байт) превышает лимит {self.settings.MAX_FILE_SIZE_MB} МБ."
                )

            # Stream download to disk
            bytes_downloaded = 0
            with open(destination_path, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=65536):
                    bytes_downloaded += len(chunk)
                    if bytes_downloaded > self.settings.max_file_size_bytes:
                        destination_path.unlink(missing_ok=True)
                        raise AudioValidationError(
                            f"Размер файла по ссылке превысил лимит {self.settings.MAX_FILE_SIZE_MB} МБ."
                        )
                    f.write(chunk)

        # Infer filename from URL path
        url_path = Path(current_url.split("?")[0])
        filename = url_path.name or "external_audio.mp3"

        logger.info(f"Downloaded external audio from {url} ({bytes_downloaded} bytes) to {destination_path}")
        return destination_path, filename
