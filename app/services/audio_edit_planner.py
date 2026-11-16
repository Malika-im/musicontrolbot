"""
Audio Edit Planner Service.
Parses natural language requests into structured execution plans,
validates feasibility, handles ambiguities, and sequences audio operations.
"""

from typing import Tuple
from app.ai.llm_client import LLMClient, PlannedAudioAction
from app.core.exceptions import PlannerAmbiguityError
from app.core.logging import logger


class AudioEditPlanner:
    def __init__(self, llm_client: LLMClient | None = None):
        self.llm_client = llm_client or LLMClient()

    def plan_edit(self, user_prompt: str) -> PlannedAudioAction:
        """
        Analyze user's natural language request and produce a validated execution plan.
        Raises PlannerAmbiguityError if the request cannot be reliably fulfilled
        or needs user clarification.
        """
        prompt = user_prompt.strip()
        if not prompt:
            raise PlannerAmbiguityError("Пустой запрос.", "Пожалуйста, напишите, что именно нужно сделать с аудио.")

        logger.info(f"Planning audio edit for prompt: '{prompt}'")
        action = self.llm_client.parse_user_prompt(prompt)

        # Check feasibility
        if not action.is_feasible:
            logger.warning(f"Unfeasible prompt rejected: {prompt}")
            raise PlannerAmbiguityError(
                f"Невозможно выполнить запрос: {action.clarification_needed}",
                action.clarification_needed or "⚠️ Извините, выполнить такой запрос с этим аудио невозможно."
            )

        # Check for ambiguity
        if action.clarification_needed:
            raise PlannerAmbiguityError(
                f"Уточнение запроса: {action.clarification_needed}",
                action.clarification_needed
            )

        logger.info(f"Planned action: type={action.action_type}, pitch={action.pitch_semitones}, stems={action.stems_to_keep}")
        return action
