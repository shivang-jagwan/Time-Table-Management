from __future__ import annotations

import random
from collections import defaultdict
from typing import Any


def choose_lns_strategy(
    iteration: int,
    *,
    feedback: dict[str, Any] | None = None,
    strategy_scores: dict[str, float] | None = None,
    seed: int | None = None,
) -> str:
    """Choose LNS strategy using objective attribution and online gains.

    Decision order:
    1) Exploration pulse every 4th iteration
    2) Attribution-guided prior (teacher vs section vs high-penalty)
    3) Historical gain winner (if available)
    4) Deterministic fallback
    """
    strategies = [
        "destroy_teacher_schedule",
        "destroy_day_block",
        "destroy_high_penalty_classes",
        "destroy_congested_slots",
    ]
    if not strategies:
        return "destroy_random"

    rng = random.Random((0 if seed is None else int(seed)) + int(iteration))
    # Controlled exploration to avoid policy lock-in.
    if int(iteration) % 4 == 3:
        return rng.choice(strategies)

    feedback = feedback or {}
    teacher_penalty = float(sum((feedback.get("teacher_penalty_score", {}) or {}).values()))
    section_penalty = float(sum((feedback.get("section_penalty_score", {}) or {}).values()))
    high_penalty_count = int(len(feedback.get("high_penalty_x_keys", []) or []))
    congested_slots = list(feedback.get("congested_slots", []) or [])

    prior = "destroy_day_block"
    if teacher_penalty >= section_penalty and teacher_penalty > 0:
        prior = "destroy_teacher_schedule"
    if high_penalty_count > 0 and high_penalty_count >= max(8, int(0.2 * high_penalty_count)):
        prior = "destroy_high_penalty_classes"
    if congested_slots:
        prior = "destroy_congested_slots"

    scores = strategy_scores or {}
    scored = [s for s in strategies if s in scores]
    if scored:
        best_scored = max(scored, key=lambda s: float(scores.get(s, 0.0)))
        # If scorer has a clear winner, prefer it over prior.
        if float(scores.get(best_scored, 0.0)) > float(scores.get(prior, 0.0)) * 1.15:
            return best_scored

    return prior


def build_lns_hints(
    best_hints: dict[str, set[Any]],
    *,
    keep_fraction: float,
    seed: int | None,
    strategy: str,
    feedback: dict[str, Any] | None = None,
) -> dict[str, set[Any]]:
    strategy = str(strategy or "destroy_random").strip().lower()
    if strategy == "destroy_teacher_schedule":
        return destroy_teacher_schedule(
            best_hints,
            keep_fraction=keep_fraction,
            seed=seed,
            feedback=feedback,
        )
    if strategy == "destroy_day_block":
        return destroy_day_block(
            best_hints,
            keep_fraction=keep_fraction,
            seed=seed,
            feedback=feedback,
        )
    if strategy == "destroy_high_penalty_classes":
        return destroy_high_penalty_classes(
            best_hints,
            keep_fraction=keep_fraction,
            seed=seed,
            feedback=feedback,
        )
    if strategy == "destroy_congested_slots":
        return destroy_congested_slots(
            best_hints,
            keep_fraction=keep_fraction,
            seed=seed,
            feedback=feedback,
        )
    return destroy_random(best_hints, keep_fraction=keep_fraction, seed=seed)


def destroy_random(
    best_hints: dict[str, set[Any]],
    *,
    keep_fraction: float,
    seed: int | None,
) -> dict[str, set[Any]]:
    rng = random.Random(0 if seed is None else int(seed))
    out = _empty_hints()
    keep_fraction = max(0.0, min(1.0, float(keep_fraction)))
    for family in out.keys():
        for key in best_hints.get(family, set()):
            if rng.random() <= keep_fraction:
                out[family].add(key)
    return out


def destroy_teacher_schedule(
    best_hints: dict[str, set[Any]],
    *,
    keep_fraction: float,
    seed: int | None,
    feedback: dict[str, Any] | None = None,
) -> dict[str, set[Any]]:
    """Proxy strategy that drops a full (section,subject) cluster from x hints.

    We do not carry teacher-id in persisted hints, so this approximates teacher
    schedule destruction by removing one dense subject cluster.
    """
    rng = random.Random(0 if seed is None else int(seed))
    out = destroy_random(best_hints, keep_fraction=keep_fraction, seed=seed)

    teacher_hotspots = list((feedback or {}).get("teacher_hotspots", []))
    x_keys_by_teacher = (feedback or {}).get("x_keys_by_teacher", {})

    if teacher_hotspots and x_keys_by_teacher:
        victim_teacher = teacher_hotspots[0]
        out["x"].difference_update(set(x_keys_by_teacher.get(victim_teacher, [])))
        return out

    grouped: dict[tuple[Any, Any], set[Any]] = defaultdict(set)
    for key in list(out["x"]):
        sec_id, subj_id, _slot_id = key
        grouped[(sec_id, subj_id)].add(key)
    if grouped:
        victim = rng.choice(list(grouped.keys()))
        out["x"].difference_update(grouped[victim])

    return out


def destroy_day_block(
    best_hints: dict[str, set[Any]],
    *,
    keep_fraction: float,
    seed: int | None,
    feedback: dict[str, Any] | None = None,
) -> dict[str, set[Any]]:
    """Destroy one random day block from lab hints, random fallback otherwise."""
    rng = random.Random(0 if seed is None else int(seed))
    out = destroy_random(best_hints, keep_fraction=keep_fraction, seed=seed)

    section_hotspots = list((feedback or {}).get("section_hotspots", []))
    x_keys_by_section = (feedback or {}).get("x_keys_by_section", {})
    if section_hotspots and x_keys_by_section:
        victim_section = section_hotspots[0]
        out["x"].difference_update(set(x_keys_by_section.get(victim_section, [])))

    # lab_start key shape: (section_id, subject_id, day, start_idx)
    labs_by_day: dict[int, set[Any]] = defaultdict(set)
    for key in list(out["lab_start"]):
        _sec, _subj, day, _start = key
        labs_by_day[int(day)].add(key)

    if labs_by_day:
        victim_day = rng.choice(sorted(labs_by_day.keys()))
        out["lab_start"].difference_update(labs_by_day[victim_day])

    return out


def destroy_high_penalty_classes(
    best_hints: dict[str, set[Any]],
    *,
    keep_fraction: float,
    seed: int | None,
    feedback: dict[str, Any] | None = None,
) -> dict[str, set[Any]]:
    """Bias destruction toward late lab starts (higher objective penalty proxy)."""
    rng = random.Random(0 if seed is None else int(seed))
    out = _empty_hints()
    keep_fraction = max(0.0, min(1.0, float(keep_fraction)))

    for family in ("x", "z", "combined_x"):
        for key in best_hints.get(family, set()):
            if rng.random() <= keep_fraction:
                out[family].add(key)

    # lab_start includes start index so we can bias pruning of late starts.
    for key in best_hints.get("lab_start", set()):
        _sec, _subj, _day, start_idx = key
        keep_p = keep_fraction * (0.6 if int(start_idx) >= 4 else 1.0)
        if rng.random() <= keep_p:
            out["lab_start"].add(key)

    # Drop late/high-penalty theory keys if available from feedback.
    for key in (feedback or {}).get("high_penalty_x_keys", []):
        if key in out["x"] and rng.random() < 0.75:
            out["x"].discard(key)

    return out


def destroy_congested_slots(
    best_hints: dict[str, set[Any]],
    *,
    keep_fraction: float,
    seed: int | None,
    feedback: dict[str, Any] | None = None,
) -> dict[str, set[Any]]:
    """Destroy assignments concentrated in overloaded slots."""
    rng = random.Random(0 if seed is None else int(seed))
    out = destroy_random(best_hints, keep_fraction=keep_fraction, seed=seed)

    congested_slots = list((feedback or {}).get("congested_slots", []) or [])
    if not congested_slots:
        return out

    x_by_slot = (feedback or {}).get("x_keys_by_slot", {}) or {}
    victim_slots = congested_slots[: max(1, min(3, len(congested_slots)))]
    for slot_id in victim_slots:
        out["x"].difference_update(set(x_by_slot.get(slot_id, [])))

    # Also relax a subset of lab placements on congested days.
    slot_day_by_slot = (feedback or {}).get("slot_day_by_slot", {}) or {}
    congested_days = set()
    for slot_id in victim_slots:
        if slot_id in slot_day_by_slot:
            try:
                congested_days.add(int(slot_day_by_slot[slot_id]))
            except Exception:
                pass

    if congested_days:
        for key in list(out["lab_start"]):
            _sec, _subj, day, _start = key
            if int(day) in congested_days and rng.random() < 0.7:
                out["lab_start"].discard(key)

    return out


def _empty_hints() -> dict[str, set[Any]]:
    return {
        "x": set(),
        "z": set(),
        "lab_start": set(),
        "combined_x": set(),
    }
