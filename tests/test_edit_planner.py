"""
Tests for AudioEditPlanner and Natural Language Understanding (Stage 4 & Stage 8).
Validates prompt parsing, pitch shifting commands, phrase filtering, and feasibility checks.
"""

import pytest
from app.core.exceptions import PlannerAmbiguityError
from app.services.audio_edit_planner import AudioEditPlanner


def test_planner_backing_vocals_prompts():
    planner = AudioEditPlanner()

    # 1. "Оставь только бэк-вокал"
    plan1 = planner.plan_edit("Оставь только бэк-вокал")
    assert plan1.action_type == "BACKING_VOCALS"
    assert "backing_vocals" in plan1.stems_to_keep

    # 2. "Убери основной голос, но оставь все бэки"
    plan2 = planner.plan_edit("Убери основной голос, но оставь все бэки")
    assert plan2.action_type == "KARAOKE"
    assert "backing_vocals" in plan2.stems_to_keep
    assert "lead_vocals" in plan2.stems_to_remove

    # 3. "Удали бэк-вокал, оставив основной голос"
    plan3 = planner.plan_edit("Удали бэк-вокал, оставив основной голос")
    assert plan3.action_type == "REMOVE_BACKING_VOCALS"
    assert "lead_vocals" in plan3.stems_to_keep


def test_planner_pitch_shift_prompts():
    planner = AudioEditPlanner()

    # "Понизь тональность на полтона"
    p1 = planner.plan_edit("Понизь тональность на полтона")
    assert p1.pitch_semitones == -1.0

    # "Подними тональность на полтона"
    p2 = planner.plan_edit("Подними тональность на полтона")
    assert p2.pitch_semitones == 1.0

    # "Понизь на один тон"
    p3 = planner.plan_edit("Понизь на один тон")
    assert p3.pitch_semitones == -2.0

    # "Подними на два тона"
    p4 = planner.plan_edit("Подними на два тона")
    assert p4.pitch_semitones == 4.0

    # "Сделай на 3 полутона ниже"
    p5 = planner.plan_edit("Сделай на 3 полутона ниже")
    assert p5.pitch_semitones == -3.0

    # "Сделай на 4 полутона выше"
    p6 = planner.plan_edit("Сделай на 4 полутона выше")
    assert p6.pitch_semitones == 4.0

    # "Верни исходную тональность"
    p7 = planner.plan_edit("Верни исходную тональность")
    assert p7.pitch_semitones == 0.0

    # Combined: "Сделай минусовку на тон ниже"
    p8 = planner.plan_edit("Сделай минусовку на тон ниже")
    assert p8.action_type == "KARAOKE"
    assert p8.pitch_semitones == -2.0


def test_planner_word_filtering_prompts():
    planner = AudioEditPlanner()

    # "Оставь слова 'я тебя люблю'"
    p1 = planner.plan_edit("Оставь слова 'я тебя люблю'")
    assert p1.action_type == "FILTER_WORDS"
    assert "я тебя люблю" in p1.keep_phrases

    # "Удали слова 'черт'"
    p2 = planner.plan_edit("Удали слова 'черт'")
    assert p2.action_type == "FILTER_WORDS"
    assert "черт" in p2.remove_phrases


def test_planner_instruments_prompts():
    planner = AudioEditPlanner()

    # "Оставь только пианино и вокал"
    p = planner.plan_edit("Оставь только пианино и вокал")
    assert p.action_type == "SEPARATE_STEMS"
    assert "piano" in p.stems_to_keep
    assert "vocals" in p.stems_to_keep


def test_planner_unfeasible_duet_prompt():
    planner = AudioEditPlanner()

    # "Убери мужской голос, оставь женский" should prompt clarification
    with pytest.raises(PlannerAmbiguityError) as exc_info:
        planner.plan_edit("Убери мужской голос, оставь женский")

    assert "мужского и женского голоса" in exc_info.value.clarification_prompt
