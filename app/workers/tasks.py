"""
Celery Background Audio Processing Tasks.
Executes AI stem separation, pitch transposition, smart editing, and delivers results to users.
"""

import asyncio
from datetime import datetime, timezone
from pathlib import Path
import uuid
from typing import Any, Dict

from app.audio.ffmpeg_utils import FFmpegUtils
from app.bot.bot_service import TelegramBotService
from app.bot.keyboards.inline import get_result_keyboard
from app.core.config import get_settings
from app.core.logging import logger
from app.database.connection import get_session_factory
from app.database.models import ProcessingStatus, TaskType
from app.database.repositories import AudioFileRepository, TaskRepository, UserRepository
from app.services.audio_mixing_service import AudioMixingService
from app.services.audio_pitch_service import AudioPitchService
from app.services.audio_separation_service import AudioSeparationService
from app.services.background_vocal_service import BackgroundVocalService
from app.services.speech_recognition_service import SpeechRecognitionService
from app.services.vocal_separation_service import VocalSeparationService
from app.storage.storage_service import StorageService
from app.workers.celery_app import celery_app


@celery_app.task(bind=True, name="process_audio_task")
def process_audio_task(self, task_id_str: str) -> Dict[str, Any]:
    """Celery task entry point."""
    logger.info(f"Starting Celery audio worker task: {task_id_str}")
    return asyncio.run(_async_process_audio_task(task_id_str))


async def _async_process_audio_task(task_id_str: str) -> Dict[str, Any]:
    task_id = uuid.UUID(task_id_str)
    session_factory = get_session_factory()
    storage = StorageService()
    bot = TelegramBotService()
    pitch_service = AudioPitchService()
    separation_service = AudioSeparationService(storage_service=storage)
    vocal_service = VocalSeparationService(separation_service=separation_service)
    bg_vocal_service = BackgroundVocalService(separation_service=separation_service)
    speech_service = SpeechRecognitionService()

    async with session_factory() as session:
        task_repo = TaskRepository(session)
        user_repo = UserRepository(session)
        task = await task_repo.get_by_id(task_id)
        if not task:
            logger.error(f"Task {task_id} not found in database.")
            return {"status": "error", "message": "Task not found"}

        user = task.user
        chat_id = user.telegram_id
        audio = task.audio_file
        input_audio_path = Path(audio.storage_path)
        stems_dir = storage.get_task_stems_dir(task_id)

        try:
            # Step 1: 🔍 Анализируем аудио
            await task_repo.update_status(task_id, ProcessingStatus.ANALYZING)
            await session.commit()
            status_msg = await bot.send_message(chat_id, "🔍 <b>Анализируем аудио и тональность...</b>")
            msg_id = status_msg["message_id"] if status_msg else None

            orig_key = task.original_key or audio.detected_key
            if not orig_key or "Unknown" in orig_key:
                orig_key, _ = pitch_service.analyze_musical_profile(input_audio_path)

            # Step 2: 🎧 Разделяем звуковые дорожки
            if msg_id:
                await bot.edit_message_text(chat_id, msg_id, "🎧 <b>Разделяем звуковые дорожки с помощью AI...</b>")
            await task_repo.update_status(task_id, ProcessingStatus.SEPARATING)
            await session.commit()

            task_type = task.task_type
            result_path = None
            result_key = orig_key
            semitones = task.semitones_shifted

            # Step 3: Execute target audio operation
            if msg_id:
                await bot.edit_message_text(chat_id, msg_id, "🎼 <b>Обрабатываем результат...</b>")
            await task_repo.update_status(task_id, ProcessingStatus.PROCESSING)
            await session.commit()

            # 3.1. Pitch shifting only
            if task_type == TaskType.PITCH_SHIFT.value:
                output_file = storage.get_result_path(task_id, "transposed", "mp3")
                semi = semitones or task.processing_parameters.get("semitones", 0.0)
                result_path, orig_key, result_key = pitch_service.transpose(
                    input_path=input_audio_path,
                    output_path=output_file,
                    semitones=semi,
                    original_key=orig_key,
                )

            # 3.2. Pure Backing Track (минусовка)
            elif task_type == TaskType.KARAOKE.value:
                # Check if backing vocals should be preserved
                keep_backings = task.processing_parameters.get("stems_to_keep", [])
                output_file = storage.get_result_path(task_id, "instrumental", "mp3")

                if "backing_vocals" in keep_backings:
                    intermediate_inst = bg_vocal_service.create_instrumental_with_backings(
                        audio_path=input_audio_path,
                        stems_dir=stems_dir,
                        output_path=output_file,
                    )
                else:
                    intermediate_inst = vocal_service.create_instrumental(
                        audio_path=input_audio_path,
                        stems_dir=stems_dir,
                        output_path=output_file,
                    )

                if semitones:
                    transposed_file = storage.get_result_path(task_id, "instrumental_transposed", "mp3")
                    result_path, orig_key, result_key = pitch_service.transpose(
                        input_path=intermediate_inst,
                        output_path=transposed_file,
                        semitones=semitones,
                        original_key=orig_key,
                    )
                else:
                    result_path = intermediate_inst

            # 3.3. Lead vocals extraction
            elif task_type == TaskType.LEAD_VOCALS.value:
                output_file = storage.get_result_path(task_id, "lead_vocal", "mp3")
                lead_path = bg_vocal_service.remove_backing_vocals(
                    audio_path=input_audio_path,
                    stems_dir=stems_dir,
                    output_path=output_file,
                )
                if semitones:
                    transposed_file = storage.get_result_path(task_id, "lead_vocal_transposed", "mp3")
                    result_path, orig_key, result_key = pitch_service.transpose(
                        lead_path, transposed_file, semitones, orig_key
                    )
                else:
                    result_path = lead_path

            # 3.4. Backing vocals extraction
            elif task_type == TaskType.BACKING_VOCALS.value:
                output_file = storage.get_result_path(task_id, "backing_vocals", "mp3")
                bg_path = bg_vocal_service.extract_backing_vocals_only(
                    audio_path=input_audio_path,
                    stems_dir=stems_dir,
                    output_path=output_file,
                )
                if semitones:
                    transposed_file = storage.get_result_path(task_id, "backing_transposed", "mp3")
                    result_path, orig_key, result_key = pitch_service.transpose(
                        bg_path, transposed_file, semitones, orig_key
                    )
                else:
                    result_path = bg_path

            # 3.5. Remove backing vocals (keep lead voice)
            elif task_type == TaskType.REMOVE_BACKING_VOCALS.value:
                output_file = storage.get_result_path(task_id, "lead_solo", "mp3")
                result_path = bg_vocal_service.remove_backing_vocals(
                    audio_path=input_audio_path,
                    stems_dir=stems_dir,
                    output_path=output_file,
                )

            # 3.6. Full stems separation (archive or primary stems)
            elif task_type == TaskType.SEPARATE_STEMS.value:
                stems = separation_service.separate_stems(input_audio_path, stems_dir)
                stems_to_keep = task.processing_parameters.get("stems_to_keep", [])
                if stems_to_keep:
                    output_file = storage.get_result_path(task_id, "stems_mix", "mp3")
                    result_path = AudioMixingService.mix_selected_stems(stems, stems_to_keep, output_file)
                else:
                    # By default mix accompaniment
                    output_file = storage.get_result_path(task_id, "accompaniment", "mp3")
                    result_path = vocal_service.create_instrumental(input_audio_path, stems_dir, output_file, stems)

            # 3.7. Filter words (Whisper) or Smart Edit
            elif task_type in ("FILTER_WORDS", "SMART_EDIT"):
                params = task.processing_parameters
                keep_phrases = params.get("keep_phrases", [])
                remove_phrases = params.get("remove_phrases", [])

                # Extract vocal stem first to run Whisper cleanly
                stems = separation_service.separate_stems(input_audio_path, stems_dir)
                vocal_stem = stems.get("vocals", input_audio_path)

                words = speech_service.get_word_timestamps(vocal_stem)

                if keep_phrases:
                    intervals = speech_service.locate_phrases(vocal_stem, keep_phrases, cached_words=words)
                    masked_vocal = storage.get_result_path(task_id, "words_kept", "mp3")
                    AudioMixingService.apply_word_filters(vocal_stem, masked_vocal, keep_intervals=intervals)
                    # Mix filtered vocal with instrumental
                    inst_file = stems_dir / "temp_inst.wav"
                    vocal_service.create_instrumental(input_audio_path, stems_dir, inst_file, stems)
                    output_file = storage.get_result_path(task_id, "smart_mix", "mp3")
                    result_path = FFmpegUtils.mix_tracks([inst_file, masked_vocal], output_file)

                elif remove_phrases:
                    intervals = speech_service.locate_phrases(vocal_stem, remove_phrases, cached_words=words)
                    masked_vocal = storage.get_result_path(task_id, "words_muted", "mp3")
                    AudioMixingService.apply_word_filters(vocal_stem, masked_vocal, remove_intervals=intervals)
                    inst_file = stems_dir / "temp_inst.wav"
                    vocal_service.create_instrumental(input_audio_path, stems_dir, inst_file, stems)
                    output_file = storage.get_result_path(task_id, "smart_mix", "mp3")
                    result_path = FFmpegUtils.mix_tracks([inst_file, masked_vocal], output_file)

                else:
                    # General smart edit fallback
                    output_file = storage.get_result_path(task_id, "edited", "mp3")
                    result_path = vocal_service.create_instrumental(input_audio_path, stems_dir, output_file, stems)

                if semitones:
                    transposed_file = storage.get_result_path(task_id, "smart_transposed", "mp3")
                    result_path, orig_key, result_key = pitch_service.transpose(
                        result_path, transposed_file, semitones, orig_key
                    )

            if not result_path or not Path(result_path).exists():
                raise Exception("Файл результата не был сформирован.")

            # Step 4: Mark COMPLETED in DB
            await task_repo.update_status(
                task_id=task_id,
                status=ProcessingStatus.COMPLETED,
                result_path=str(result_path),
                semitones_shifted=semitones,
                original_key=orig_key,
                result_key=result_key,
            )
            await session.commit()

            # Clean up intermediate stems directory
            storage.cleanup_task_temp_files(task_id)

            # Step 5: Send final result to user
            if msg_id:
                await bot.edit_message_text(chat_id, msg_id, "✅ <b>Готово! Отправляем аудио...</b>")

            key_info = f"\n🎼 Тональность: <b>{result_key}</b>" if result_key else ""
            shift_info = f" ({semitones:+.1f} полут.)" if semitones else ""
            caption = (
                f"Готово! 🎉\n"
                f"Файл: <b>{audio.original_filename}</b>\n"
                f"Обработка: <b>{task_type}</b>{shift_info}{key_info}"
            )

            await bot.send_audio(
                chat_id=chat_id,
                audio_path=Path(result_path),
                caption=caption,
                title=f"{audio.original_filename} [{task_type}]",
                performer="AI Music Bot",
                reply_markup=get_result_keyboard(task_id, audio.id),
            )

            return {"status": "success", "result_path": str(result_path)}

        except Exception as exc:
            logger.exception(f"Worker task error for {task_id}: {exc}")
            await task_repo.update_status(
                task_id=task_id,
                status=ProcessingStatus.FAILED,
                error_message=str(exc),
            )
            await session.commit()
            storage.cleanup_task_temp_files(task_id)

            await bot.send_message(
                chat_id=chat_id,
                text="⚠️ Произошла ошибка при обработке композиции. Пожалуйста, попробуйте еще раз."
            )
            return {"status": "failed", "error": str(exc)}
