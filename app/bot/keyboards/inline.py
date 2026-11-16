"""
Inline Keyboard Markups for Telegram Bot.
"""

from typing import Any, Dict, List
import uuid


def get_audio_action_keyboard(audio_id: uuid.UUID) -> Dict[str, Any]:
    """Main menu of processing options for received audio."""
    a_id = str(audio_id)
    return {
        "inline_keyboard": [
            [
                {"text": "🎵 Создать минусовку", "callback_data": f"act:karaoke:{a_id}"},
                {"text": "🎤 Извлечь основной вокал", "callback_data": f"act:lead_vocals:{a_id}"},
            ],
            [
                {"text": "🎧 Извлечь бэк-вокал", "callback_data": f"act:backing_vocals:{a_id}"},
                {"text": "🎼 Удалить бэк-вокал", "callback_data": f"act:remove_backing:{a_id}"},
            ],
            [
                {"text": "🎹 Разделить на инструменты", "callback_data": f"act:stems:{a_id}"},
                {"text": "🎹 Изменить тональность", "callback_data": f"act:pitch_menu:{a_id}"},
            ],
            [
                {"text": "✂️ Умное редактирование (текстом)", "callback_data": f"act:smart_prompt:{a_id}"},
            ],
        ]
    }


def get_pitch_keyboard(audio_id: uuid.UUID) -> Dict[str, Any]:
    """Pitch shifting options keyboard (Section 13.5)."""
    a_id = str(audio_id)
    return {
        "inline_keyboard": [
            [
                {"text": "⬇️ -1 полутон", "callback_data": f"pitch:-1:{a_id}"},
                {"text": "⬇️ -2 полутона", "callback_data": f"pitch:-2:{a_id}"},
                {"text": "⬇️ -3 полутона", "callback_data": f"pitch:-3:{a_id}"},
            ],
            [
                {"text": "⬆️ +1 полутон", "callback_data": f"pitch:1:{a_id}"},
                {"text": "⬆️ +2 полутона", "callback_data": f"pitch:2:{a_id}"},
                {"text": "⬆️ +3 полутона", "callback_data": f"pitch:3:{a_id}"},
            ],
            [
                {"text": "✍️ Ввести своё значение", "callback_data": f"pitch:custom:{a_id}"},
                {"text": "◀️ Назад в меню", "callback_data": f"pitch:back:{a_id}"},
            ],
        ]
    }


def get_result_keyboard(task_id: uuid.UUID, audio_id: uuid.UUID) -> Dict[str, Any]:
    """Result options keyboard."""
    t_id = str(task_id)
    a_id = str(audio_id)
    return {
        "inline_keyboard": [
            [
                {"text": "🎤 Получить оригинальный вокал", "callback_data": f"act:lead_vocals:{a_id}"},
                {"text": "🎧 Получить бэк-вокал", "callback_data": f"act:backing_vocals:{a_id}"},
            ],
            [
                {"text": "🎹 Изменить тональность", "callback_data": f"act:pitch_menu:{a_id}"},
                {"text": "✂️ Продолжить редактирование", "callback_data": f"act:smart_prompt:{a_id}"},
            ],
            [
                {"text": "🔄 Обработать другую песню", "callback_data": "act:new_song"},
            ],
        ]
    }
