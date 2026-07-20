"""Deterministic Discussion prompt rules for filtered Dashboard data."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DiscussionPrompt:
    """One neutral Dashboard prompt in its fixed product priority."""

    key: str
    title: str
    message: str
    priority: int


def _longest_consecutive_streak(values: Iterable[date]) -> int:
    """Return the longest run of distinct consecutive calendar dates."""
    longest = 0
    current = 0
    previous: date | None = None
    for value in sorted(set(values)):
        current = current + 1 if previous == value - timedelta(days=1) else 1
        longest = max(longest, current)
        previous = value
    return longest


def build_discussion_prompts(
    *,
    difficult_mood_dates: Iterable[date],
    total_meetings: int,
    concrete_next_step_count: int,
    positive_replies: int,
    meetings_booked: int,
    blocker_counts: Iterable[tuple[str | None, int]],
) -> tuple[DiscussionPrompt, ...]:
    """Build every supported prompt from already-filtered Dashboard values."""
    prompts: list[DiscussionPrompt] = []

    streak_length = _longest_consecutive_streak(difficult_mood_dates)
    if streak_length >= 2:
        prompts.append(
            DiscussionPrompt(
                key="consecutive_difficult_days",
                title="Mood pattern",
                message=(
                    "Difficult mood was recorded on "
                    f"{streak_length} consecutive days."
                ),
                priority=1,
            ),
        )

    if (
        total_meetings >= 4
        and concrete_next_step_count * 2 < total_meetings
    ):
        prompts.append(
            DiscussionPrompt(
                key="few_concrete_next_steps",
                title="Few concrete next steps",
                message=(
                    f"Only {concrete_next_step_count} of {total_meetings} "
                    "meetings had a concrete next step."
                ),
                priority=2,
            ),
        )

    if positive_replies >= 3 and meetings_booked == 0:
        prompts.append(
            DiscussionPrompt(
                key="positive_replies_without_booked_meetings",
                title="Positive replies without booked meetings",
                message=(
                    f"{positive_replies} positive replies were recorded, "
                    "but no meetings were booked."
                ),
                priority=3,
            ),
        )

    qualifying_blockers: list[tuple[str, int]] = []
    for label, count in blocker_counts:
        if label is None or not label.strip() or count < 3:
            continue
        qualifying_blockers.append((label, count))
    qualifying_blockers.sort(
        key=lambda item: (-item[1], item[0].casefold(), item[0]),
    )
    if qualifying_blockers:
        blocker_label, blocker_count = qualifying_blockers[0]
        prompts.append(
            DiscussionPrompt(
                key="repeated_blocker",
                title="Repeated blocker",
                message=f"{blocker_label} was reported {blocker_count} times.",
                priority=4,
            ),
        )

    return tuple(prompts)


__all__ = ["DiscussionPrompt", "build_discussion_prompts"]
