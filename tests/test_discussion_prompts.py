"""Focused unit tests for deterministic Discussion prompt rules."""

from datetime import date

import pytest

from app.services.discussion_prompts import build_discussion_prompts


def prompt_keys(
    *,
    difficult_mood_dates: tuple[date, ...] = (),
    total_meetings: int = 0,
    concrete_next_step_count: int = 0,
    positive_replies: int = 0,
    meetings_booked: int = 0,
    blocker_counts: tuple[tuple[str | None, int], ...] = (),
) -> list[str]:
    return [
        prompt.key
        for prompt in build_discussion_prompts(
            difficult_mood_dates=difficult_mood_dates,
            total_meetings=total_meetings,
            concrete_next_step_count=concrete_next_step_count,
            positive_replies=positive_replies,
            meetings_booked=meetings_booked,
            blocker_counts=blocker_counts,
        )
    ]


def test_consecutive_difficult_days_uses_longest_distinct_calendar_streak() -> None:
    prompts = build_discussion_prompts(
        difficult_mood_dates=(
            date(2026, 7, 1),
            date(2026, 7, 1),
            date(2026, 7, 3),
            date(2026, 7, 4),
            date(2026, 7, 5),
        ),
        total_meetings=0,
        concrete_next_step_count=0,
        positive_replies=0,
        meetings_booked=0,
        blocker_counts=(),
    )

    assert len(prompts) == 1
    assert prompts[0].key == "consecutive_difficult_days"
    assert prompts[0].title == "Mood pattern"
    assert (
        prompts[0].message
        == "Difficult mood was recorded on 3 consecutive days."
    )
    assert prompts[0].priority == 1


def test_consecutive_difficult_days_requires_two_dates_without_a_gap() -> None:
    assert prompt_keys(
        difficult_mood_dates=(date(2026, 7, 1),),
    ) == []
    assert prompt_keys(
        difficult_mood_dates=(date(2026, 7, 1), date(2026, 7, 3)),
    ) == []
    assert prompt_keys(
        difficult_mood_dates=(date(2026, 7, 1), date(2026, 7, 2)),
    ) == ["consecutive_difficult_days"]


@pytest.mark.parametrize(
    ("total_meetings", "concrete_count", "expected"),
    [
        (3, 0, []),
        (4, 2, []),
        (4, 1, ["few_concrete_next_steps"]),
        (5, 2, ["few_concrete_next_steps"]),
    ],
)
def test_few_concrete_next_steps_uses_exact_threshold_boundaries(
    total_meetings: int,
    concrete_count: int,
    expected: list[str],
) -> None:
    assert prompt_keys(
        total_meetings=total_meetings,
        concrete_next_step_count=concrete_count,
    ) == expected


def test_few_concrete_next_steps_message_uses_exact_counts() -> None:
    prompt = build_discussion_prompts(
        difficult_mood_dates=(),
        total_meetings=5,
        concrete_next_step_count=2,
        positive_replies=0,
        meetings_booked=0,
        blocker_counts=(),
    )[0]

    assert prompt.title == "Few concrete next steps"
    assert prompt.message == (
        "Only 2 of 5 meetings had a concrete next step."
    )


@pytest.mark.parametrize(
    ("positive_replies", "meetings_booked", "expected"),
    [
        (2, 0, []),
        (3, 1, []),
        (3, 0, ["positive_replies_without_booked_meetings"]),
    ],
)
def test_positive_replies_without_booked_meetings_boundaries(
    positive_replies: int,
    meetings_booked: int,
    expected: list[str],
) -> None:
    assert prompt_keys(
        positive_replies=positive_replies,
        meetings_booked=meetings_booked,
    ) == expected


def test_positive_replies_message_uses_exact_count() -> None:
    prompt = build_discussion_prompts(
        difficult_mood_dates=(),
        total_meetings=0,
        concrete_next_step_count=0,
        positive_replies=4,
        meetings_booked=0,
        blocker_counts=(),
    )[0]

    assert prompt.title == "Positive replies without booked meetings"
    assert prompt.message == (
        "4 positive replies were recorded, but no meetings were booked."
    )


def test_repeated_blocker_ignores_empty_and_applies_count_then_label_order() -> None:
    prompts = build_discussion_prompts(
        difficult_mood_dates=(),
        total_meetings=0,
        concrete_next_step_count=0,
        positive_replies=0,
        meetings_booked=0,
        blocker_counts=(
            (None, 10),
            ("", 10),
            ("   ", 10),
            ("Zulu", 4),
            ("Alpha", 4),
            ("Higher count", 5),
        ),
    )

    assert len(prompts) == 1
    assert prompts[0].key == "repeated_blocker"
    assert prompts[0].title == "Repeated blocker"
    assert prompts[0].message == "Higher count was reported 5 times."
    assert prompts[0].priority == 4

    alphabetical_tie = build_discussion_prompts(
        difficult_mood_dates=(),
        total_meetings=0,
        concrete_next_step_count=0,
        positive_replies=0,
        meetings_booked=0,
        blocker_counts=(("Zulu", 3), ("Alpha", 3)),
    )
    assert alphabetical_tie[0].message == "Alpha was reported 3 times."
    assert prompt_keys(blocker_counts=(("Alpha", 2),)) == []


def test_fixed_priority_returns_all_unique_supported_prompt_types() -> None:
    prompts = build_discussion_prompts(
        difficult_mood_dates=(date(2026, 7, 1), date(2026, 7, 2)),
        total_meetings=4,
        concrete_next_step_count=1,
        positive_replies=3,
        meetings_booked=0,
        blocker_counts=(("No response", 3),),
    )

    assert [prompt.key for prompt in prompts] == [
        "consecutive_difficult_days",
        "few_concrete_next_steps",
        "positive_replies_without_booked_meetings",
        "repeated_blocker",
    ]
    assert [prompt.priority for prompt in prompts] == [1, 2, 3, 4]
    assert len({prompt.key for prompt in prompts}) == 4
