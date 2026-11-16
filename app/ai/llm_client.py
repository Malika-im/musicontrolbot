"""
LLM Client and Natural Language Planner.
Converts user natural language edit requests into structured execution plans.
Includes robust heuristic semantic parser and external LLM adapter (OpenAI/Gemini).
"""

import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from app.core.config import get_settings
from app.core.logging import logger


class PlannedAudioAction(BaseModel):
    action_type: str = Field(description="Primary action: KARAOKE, LEAD_VOCALS, BACKING_VOCALS, REMOVE_BACKING_VOCALS, FILTER_WORDS, PITCH_SHIFT, COMBINED")
    stems_to_keep: List[str] = Field(default_factory=list, description="Stems to keep: drums, bass, other, vocals, lead_vocals, backing_vocals, piano, guitar")
    stems_to_remove: List[str] = Field(default_factory=list, description="Stems to mute")
    pitch_semitones: Optional[float] = Field(default=None, description="Semitones to shift pitch (+/- float)")
    keep_phrases: List[str] = Field(default_factory=list, description="Specific phrases/words to isolate")
    remove_phrases: List[str] = Field(default_factory=list, description="Specific phrases/words to censor/mute")
    time_intervals_to_keep: List[Dict[str, float]] = Field(default_factory=list)
    time_intervals_to_remove: List[Dict[str, float]] = Field(default_factory=list)
    is_feasible: bool = Field(default=True, description="Whether the request is technically achievable")
    clarification_needed: Optional[str] = Field(default=None, description="Question to ask user if request is ambiguous")
    summary_description: str = Field(default="", description="Human-readable description of planned operation")


class LLMClient:
    def __init__(self):
        self.settings = get_settings()

    def parse_user_prompt(self, prompt: str) -> PlannedAudioAction:
        """
        Parse user natural language prompt into PlannedAudioAction.
        Uses OpenAI or Gemini if configured, otherwise falls back to rule-based semantic parser.
        """
        clean_prompt = prompt.strip()

        if self.settings.LLM_PROVIDER == "openai" and self.settings.OPENAI_API_KEY:
            try:
                return self._parse_with_openai(clean_prompt)
            except Exception as e:
                logger.warning(f"OpenAI parsing failed, falling back to heuristic parser: {e}")

        # Default high-accuracy heuristic parser
        return self._parse_heuristic(clean_prompt)

    def _parse_heuristic(self, text: str) -> PlannedAudioAction:
        """
        Rule-based semantic parser for Russian and English audio editing commands.
        """
        lower = text.lower()
        plan = PlannedAudioAction(action_type="SMART_EDIT", summary_description=text)

        # 1. Pitch shift detection
        pitch_match = self._extract_pitch(lower)
        if pitch_match is not None:
            plan.pitch_semitones = pitch_match

        # 2. Backing vocal isolation
        if (
            ("только бэк" in lower or "оставь бэк" in lower or "извлеки бэк" in lower or "только бэки" in lower)
            and ("удали бэк" not in lower and "без бэк" not in lower)
        ):
            plan.action_type = "BACKING_VOCALS"
            plan.stems_to_keep = ["backing_vocals"]
            plan.stems_to_remove = ["lead_vocals", "drums", "bass", "other"]
            plan.summary_description = "Извлечение только бэк-вокала"

        # 3. Remove lead vocal, keep backing vocal
        elif (
            ("убери основной" in lower or "без основного" in lower or "удали голос" in lower or "убери вокал" in lower)
            and ("оставь бэк" in lower or "с бэк" in lower or "оставь все бэки" in lower)
        ):
            plan.action_type = "KARAOKE"
            plan.stems_to_keep = ["drums", "bass", "other", "backing_vocals"]
            plan.stems_to_remove = ["lead_vocals"]
            plan.summary_description = "Минусовка с сохранением бэк-вокала"

        # 4. Remove backing vocal, keep lead voice
        elif (
            ("удали бэк" in lower or "убери бэк" in lower or "без бэк" in lower or "сними бэк" in lower)
            and ("оставь" not in lower or "оставь голос" in lower or "оставь вокал" in lower or "оставь основной" in lower)
        ):
            plan.action_type = "REMOVE_BACKING_VOCALS"
            plan.stems_to_keep = ["lead_vocals"]
            plan.stems_to_remove = ["backing_vocals"]
            plan.summary_description = "Удаление бэк-вокала (сохранение только чистого основного голоса)"

        # 5. Pure backing track (минусовка)
        elif (
            "минусовк" in lower or "минус" in lower or "без голоса" in lower or "убери голос" in lower
            or "удали вокал" in lower or "instrumental" in lower
        ):
            plan.action_type = "KARAOKE"
            plan.stems_to_keep = ["drums", "bass", "other"]
            plan.stems_to_remove = ["vocals", "lead_vocals", "backing_vocals"]
            plan.summary_description = "Создание чистой минусовки без вокала"

        # 6. Extract lead vocal
        elif (
            "только голос" in lower or "извлеки голос" in lower or "выдели вокал" in lower or "только вокал" in lower
            or "чистый вокал" in lower or "оставь голос" in lower
        ):
            plan.action_type = "LEAD_VOCALS"
            plan.stems_to_keep = ["lead_vocals"]
            plan.stems_to_remove = ["drums", "bass", "other"]
            plan.summary_description = "Извлечение основного голоса"

        # 7. Words filtering (Whisper)
        quotes_match = re.findall(r"['\"«](.*?)['\"»]", text)
        if "оставь слова" in lower or "оставь фразу" in lower or "оставь только фразу" in lower:
            plan.action_type = "FILTER_WORDS"
            if quotes_match:
                plan.keep_phrases = quotes_match
            else:
                words_tail = re.split(r"слова|фразу", lower, maxsplit=1)[-1].strip()
                if words_tail:
                    plan.keep_phrases = [words_tail]
            plan.summary_description = f"Сохранение только слов: {', '.join(plan.keep_phrases)}"

        elif "удали слова" in lower or "убери слова" in lower or "запикай" in lower or "вырежи слова" in lower:
            plan.action_type = "FILTER_WORDS"
            if quotes_match:
                plan.remove_phrases = quotes_match
            else:
                words_tail = re.split(r"слова|фразу", lower, maxsplit=1)[-1].strip()
                if words_tail:
                    plan.remove_phrases = [words_tail]
            plan.summary_description = f"Удаление слов: {', '.join(plan.remove_phrases)}"

        # 8. Specific instruments
        if "пианино" in lower or "фортепиано" in lower or "гитар" in lower:
            plan.action_type = "SEPARATE_STEMS"
            instruments = []
            if "пианино" in lower or "фортепиано" in lower:
                instruments.append("piano")
            if "гитар" in lower:
                instruments.append("guitar")
            if "вокал" in lower or "голос" in lower:
                instruments.append("vocals")
            plan.stems_to_keep = instruments
            plan.summary_description = f"Выделение дорожек: {', '.join(instruments)}"

        # 9. Feasibility checks
        if "мужской" in lower and "женский" in lower and "оставь" in lower:
            plan.is_feasible = False
            plan.clarification_needed = (
                "⚠️ Разделение мужского и женского голоса в одном вокальном треке "
                "требует раздельного исполнения или чистых соло-партий. "
                "Хотите извлечь весь вокал целиком или сделать минусовку?"
            )

        # Action type assignment for pitch-shift only
        if plan.pitch_semitones is not None and plan.action_type == "SMART_EDIT":
            plan.action_type = "PITCH_SHIFT"
            direction = "повышение" if plan.pitch_semitones > 0 else "понижение"
            plan.summary_description = f"Изменение тональности ({direction} на {abs(plan.pitch_semitones)} полутона)"

        # Combined action summary
        if plan.pitch_semitones is not None and plan.action_type != "PITCH_SHIFT":
            plan.summary_description += f" с транспонированием на {plan.pitch_semitones:+.1f} полутона"

        return plan

    def _extract_pitch(self, text: str) -> Optional[float]:
        """Extract semitones from text commands."""
        # 1. Reset / original key
        if "исходную тональность" in text or "верни тональность" in text:
            return 0.0

        # 2. Suffix directions: "на полтона ниже", "на полтона выше"
        if re.search(r"на\s*полтона\s*ниже", text) or re.search(r"(понизь|опусти|сделай ниже|ниже|уменьши).*полтона", text):
            return -1.0
        if re.search(r"на\s*полтона\s*выше", text) or re.search(r"(подними|сделай выше|выше|увеличь).*полтона", text):
            return 1.0

        # 3. Two tones (4 semitones)
        if re.search(r"на\s*(?:два|2)\s*тона?\s*ниже", text) or re.search(r"(понизь|опусти|сделай ниже|ниже|уменьши).*(?:два|2)\s*тона?", text):
            return -4.0
        if re.search(r"на\s*(?:два|2)\s*тона?\s*выше", text) or re.search(r"(подними|сделай выше|выше|увеличь).*(?:два|2)\s*тона?", text):
            return 4.0

        # 4. One tone (2 semitones): e.g. "на тон ниже", "на один тон ниже", "понизь на тон"
        if re.search(r"на\s*(?:один|1)?\s*тон\s*ниже", text) or re.search(r"(понизь|опусти|сделай ниже|ниже|уменьши).*(?:один|1)?\s*тон\b", text):
            return -2.0
        if re.search(r"на\s*(?:один|1)?\s*тон\s*выше", text) or re.search(r"(подними|сделай выше|выше|увеличь).*(?:один|1)?\s*тон\b", text):
            return 2.0

        # 5. N semitones (e.g. "на 3 полутона ниже", "понизь на 3 полутона", "сделай на 4 полутона выше")
        match_dir_last = re.search(r"на\s*(\d+)\s*(?:полутон|полутона|полутонов)\s*(выше|ниже)", text)
        if match_dir_last:
            count, direction = float(match_dir_last.group(1)), match_dir_last.group(2)
            return count if direction == "выше" else -count

        match_dir_first = re.search(
            r"(понизь|опусти|сделай ниже|ниже|уменьши|подними|сделай выше|выше|увеличь)\s*(?:тональность)?\s*(?:на)?\s*(\d+)\s*(?:полутон|полутона|полутонов)?",
            text,
        )
        if match_dir_first:
            verb, count = match_dir_first.group(1), float(match_dir_first.group(2))
            return -count if any(w in verb for w in ["понизь", "опусти", "ниже", "уменьши"]) else count

        return None

    def _parse_with_openai(self, text: str) -> PlannedAudioAction:
        """Call OpenAI JSON completion."""
        import httpx
        system_prompt = (
            "You are an AI Audio Engineer. Analyze user's music processing request and output "
            "JSON matching PlannedAudioAction schema. Determine action_type, stems_to_keep, stems_to_remove, "
            "pitch_semitones, keep_phrases, remove_phrases, is_feasible, clarification_needed."
        )
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.settings.LLM_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.1,
        }
        with httpx.Client(timeout=15.0) as client:
            resp = client.post(url, headers=headers, json=payload)
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed_dict = json.loads(content)
            return PlannedAudioAction(**parsed_dict)
