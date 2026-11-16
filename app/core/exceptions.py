"""
Custom Domain Exceptions.
"""


class MusicBotException(Exception):
    """Base exception for AI Music Bot."""

    def __init__(self, message: str, user_friendly_message: str | None = None):
        super().__init__(message)
        self.message = message
        self.user_friendly_message = (
            user_friendly_message
            or "⚠️ Произошла ошибка при обработке аудио. Пожалуйста, попробуйте позже."
        )


class AudioValidationError(MusicBotException):
    """Raised when an audio file fails validation (size, duration, format, corrupted)."""
    pass


class SSRFSecurityError(MusicBotException):
    """Raised when an external download URL points to an internal or restricted network address."""
    pass


class TaskLimitExceededError(MusicBotException):
    """Raised when user exceeds maximum concurrent processing tasks."""
    pass


class AudioSeparationError(MusicBotException):
    """Raised when AI stem separation fails."""
    pass


class SpeechRecognitionError(MusicBotException):
    """Raised when Whisper speech-to-text fails."""
    pass


class PitchShiftError(MusicBotException):
    """Raised when audio pitch transposition fails."""
    pass


class PlannerAmbiguityError(MusicBotException):
    """Raised when user's natural language edit command is ambiguous or unfeasible."""
    def __init__(self, message: str, clarification_prompt: str):
        super().__init__(message, clarification_prompt)
        self.clarification_prompt = clarification_prompt


class StorageError(MusicBotException):
    """Raised when disk storage is full or file operations fail."""
    pass
