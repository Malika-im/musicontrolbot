"""
Audio and Media Handlers.
Processes audio files, voice notes, documents, video audio tracks, and safe external URLs.
"""

from pathlib import Path
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.audio.ffmpeg_utils import FFmpegUtils
from app.bot.bot_service import TelegramBotService
from app.bot.keyboards.inline import get_audio_action_keyboard
from app.core.exceptions import AudioValidationError, SSRFSecurityError
from app.core.logging import logger
from app.database.repositories import AudioFileRepository, UserRepository
from app.services.audio_download_service import AudioDownloadService
from app.services.audio_pitch_service import AudioPitchService
from app.services.audio_validation_service import AudioValidationService
from app.storage.storage_service import StorageService


class AudioHandlers:
    def __init__(
        self,
        bot_service: TelegramBotService,
        session: AsyncSession,
        storage_service: Optional[StorageService] = None,
        download_service: Optional[AudioDownloadService] = None,
        validation_service: Optional[AudioValidationService] = None,
        pitch_service: Optional[AudioPitchService] = None,
    ):
        self.bot = bot_service
        self.session = session
        self.storage = storage_service or StorageService()
        self.download = download_service or AudioDownloadService()
        self.validator = validation_service or AudioValidationService()
        self.pitch = pitch_service or AudioPitchService()
        self.user_repo = UserRepository(session)
        self.audio_repo = AudioFileRepository(session)

    async def handle_media_message(
        self,
        chat_id: int,
        telegram_id: int,
        username: Optional[str],
        message: Dict[str, Any],
    ) -> None:
        """Process incoming audio, voice, document, or video message."""
        user = await self.user_repo.get_or_create(telegram_id=telegram_id, username=username)

        # Identify media type and file_id
        file_id = None
        orig_name = "audio.mp3"
        ext = "mp3"
        is_video = False

        if "audio" in message:
            audio_obj = message["audio"]
            file_id = audio_obj["file_id"]
            orig_name = audio_obj.get("file_name", "track.mp3")
            ext = Path(orig_name).suffix.lstrip(".") or "mp3"
        elif "voice" in message:
            voice_obj = message["voice"]
            file_id = voice_obj["file_id"]
            orig_name = "voice_note.ogg"
            ext = "ogg"
        elif "document" in message:
            doc_obj = message["document"]
            file_id = doc_obj["file_id"]
            orig_name = doc_obj.get("file_name", "document.mp3")
            ext = Path(orig_name).suffix.lstrip(".") or "mp3"
        elif "video" in message:
            video_obj = message["video"]
            file_id = video_obj["file_id"]
            orig_name = video_obj.get("file_name", "video.mp4")
            ext = Path(orig_name).suffix.lstrip(".") or "mp4"
            is_video = True
        elif "video_note" in message:
            vn_obj = message["video_note"]
            file_id = vn_obj["file_id"]
            orig_name = "video_note.mp4"
            ext = "mp4"
            is_video = True

        if not file_id:
            return

        clean_name = self.validator.sanitize_filename(orig_name)
        status_msg = await self.bot.send_message(
            chat_id=chat_id,
            text=f"⏳ Загружаем файл <b>{clean_name}</b>...",
        )
        msg_id = status_msg["message_id"] if status_msg else None

        try:
            # Generate local storage path
            temp_dest = self.storage.get_upload_path(user.id, extension=ext)
            await self.download.download_telegram_file(file_id, temp_dest)

            # If video, extract audio stream
            if is_video:
                audio_dest = self.storage.get_upload_path(user.id, extension="mp3")
                FFmpegUtils.extract_audio_from_video(temp_dest, audio_dest)
                temp_dest.unlink(missing_ok=True)
                temp_dest = audio_dest
                clean_name = f"{Path(clean_name).stem}.mp3"

            # Validate audio
            fmt, duration, file_size = self.validator.validate_audio(temp_dest, clean_name)

            # Detect key and BPM (Section 13.4)
            detected_key, detected_bpm = self.pitch.analyze_musical_profile(temp_dest)

            # Save in database
            audio_record = await self.audio_repo.create(
                user_id=user.id,
                original_filename=clean_name,
                file_format=fmt,
                duration=duration,
                file_size=file_size,
                storage_path=str(temp_dest),
                detected_key=detected_key,
                detected_bpm=detected_bpm,
            )
            await self.session.commit()

            # Format response
            mins = int(duration // 60)
            secs = int(duration % 60)
            text = (
                f"🎵 <b>Файл принят:</b> {clean_name}\n"
                f"⏱ <b>Длительность:</b> {mins}:{secs:02d}\n"
                f"🎼 <b>Исходная тональность:</b> {detected_key}\n"
                f"🥁 <b>Темп (BPM):</b> {detected_bpm}\n\n"
                f"Выберите желаемый вариант обработки:"
            )
            keyboard = get_audio_action_keyboard(audio_record.id)

            if msg_id:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=keyboard,
                )
            else:
                await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

        except AudioValidationError as e:
            await self.bot.send_message(chat_id=chat_id, text=f"⚠️ {e.user_friendly_message}")
        except Exception as e:
            logger.exception(f"Error handling media message: {e}")
            await self.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Не удалось обработать отправленный файл. Пожалуйста, попробуйте другую аудиозапись."
            )

    async def handle_external_url(
        self,
        chat_id: int,
        telegram_id: int,
        username: Optional[str],
        url: str,
    ) -> None:
        """Download and process audio from an external HTTP/HTTPS link."""
        user = await self.user_repo.get_or_create(telegram_id=telegram_id, username=username)
        status_msg = await self.bot.send_message(
            chat_id=chat_id,
            text="⏳ Проверяем внешнюю ссылку и скачиваем аудио...",
        )
        msg_id = status_msg["message_id"] if status_msg else None

        try:
            temp_dest = self.storage.get_upload_path(user.id, extension="mp3")
            saved_path, filename = await self.download.download_from_external_url(url, temp_dest)

            clean_name = self.validator.sanitize_filename(filename)
            fmt, duration, file_size = self.validator.validate_audio(saved_path, clean_name)
            detected_key, detected_bpm = self.pitch.analyze_musical_profile(saved_path)

            audio_record = await self.audio_repo.create(
                user_id=user.id,
                original_filename=clean_name,
                file_format=fmt,
                duration=duration,
                file_size=file_size,
                storage_path=str(saved_path),
                detected_key=detected_key,
                detected_bpm=detected_bpm,
            )
            await self.session.commit()

            mins = int(duration // 60)
            secs = int(duration % 60)
            text = (
                f"🎵 <b>Файл по ссылке загружен:</b> {clean_name}\n"
                f"⏱ <b>Длительность:</b> {mins}:{secs:02d}\n"
                f"🎼 <b>Исходная тональность:</b> {detected_key}\n"
                f"🥁 <b>Темп (BPM):</b> {detected_bpm}\n\n"
                f"Выберите действие:"
            )
            keyboard = get_audio_action_keyboard(audio_record.id)

            if msg_id:
                await self.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=keyboard,
                )
            else:
                await self.bot.send_message(chat_id=chat_id, text=text, reply_markup=keyboard)

        except (SSRFSecurityError, AudioValidationError) as e:
            await self.bot.send_message(chat_id=chat_id, text=f"⚠️ {e.user_friendly_message}")
        except Exception as e:
            logger.exception(f"External URL download failed: {e}")
            await self.bot.send_message(
                chat_id=chat_id,
                text="⚠️ Не удалось загрузить аудио по ссылке. Убедитесь, что это прямая публичная ссылка на MP3/WAV."
            )
