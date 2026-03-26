from __future__ import annotations

import random
from collections import defaultdict
from typing import Any

from solver.context import SolverContext
from solver.hybrid_initializer import generate_hybrid_hints


def build_initialization_modes(
    *,
    num_candidates: int,
    include_hybrid: bool,
) -> list[str]:
    """Build a deterministic initialization mode sequence for multi-start runs."""
    modes: list[str] = ["heuristic"]
    if include_hybrid:
        modes.append("hybrid")

    while len(modes) < max(1, int(num_candidates)):
        modes.append("random")
    return modes[: max(1, int(num_candidates))]


def generate_initial_hints(
    ctx: SolverContext,
    *,
    mode: str,
    seed: int | None,
    hybrid_population_size: int,
    hybrid_generations: int,
) -> dict[str, set[Any]]:
    """Generate structured warm-start hints by mode.

    Returns sets keyed by variable family so callers can re-apply hints to
    rebuilt models in later solve passes.
    """
    mode = str(mode or "heuristic").strip().lower()
    if mode == "hybrid":
        return _hybrid_hints(
            ctx,
            seed=seed,
            population_size=hybrid_population_size,
            generations=hybrid_generations,
        )
    if mode == "random":
        return _random_hints(ctx, seed=seed)
    if mode == "ga":
        # GA mode currently reuses the existing hybrid generator.
        return _hybrid_hints(
            ctx,
            seed=seed,
            population_size=hybrid_population_size,
            generations=hybrid_generations,
        )
    return _heuristic_hints(ctx)


def _empty_hints() -> dict[str, set[Any]]:
    return {
        "x": set(),
        "z": set(),
        "lab_start": set(),
        "combined_x": set(),
    }


def _heuristic_hints(ctx: SolverContext) -> dict[str, set[Any]]:
    hints = _empty_hints()

    # Simple earliest-slot greedy assignment respecting section/teacher slot usage.
    section_used: set[tuple[Any, Any]] = set(ctx.locked_section_slots)
    teacher_used: set[tuple[Any, Any]] = set(ctx.locked_teacher_slots)

    x_keys = sorted(
        ctx.x.keys(),
        key=lambda k: (
            str(k[0]),
            str(k[1]),
            ctx.slot_info.get(k[2], (99, 99))[0],
            ctx.slot_info.get(k[2], (99, 99))[1],
        ),
    )
    selected_count: dict[tuple[Any, Any], int] = defaultdict(int)

    for sec_id, subj_id, slot_id in x_keys:
        teacher_id = ctx.assigned_teacher_by_section_subject.get((sec_id, subj_id))
        if teacher_id is None:
            continue

        required = _required_sessions(ctx, sec_id, subj_id)
        if selected_count[(sec_id, subj_id)] >= required:
            continue

        if (sec_id, slot_id) in section_used:
            continue
        if (teacher_id, slot_id) in teacher_used:
            continue

        hints["x"].add((sec_id, subj_id, slot_id))
        selected_count[(sec_id, subj_id)] += 1
        section_used.add((sec_id, slot_id))
        teacher_used.add((teacher_id, slot_id))

    return hints


def _random_hints(ctx: SolverContext, *, seed: int | None) -> dict[str, set[Any]]:
    hints = _empty_hints()
    rng = random.Random(0 if seed is None else int(seed))

    section_used: set[tuple[Any, Any]] = set(ctx.locked_section_slots)
    teacher_used: set[tuple[Any, Any]] = set(ctx.locked_teacher_slots)

    by_pair: dict[tuple[Any, Any], list[Any]] = defaultdict(list)
    for sec_id, subj_id, slot_id in ctx.x.keys():
        by_pair[(sec_id, subj_id)].append(slot_id)

    pairs = list(by_pair.keys())
    rng.shuffle(pairs)

    for sec_id, subj_id in pairs:
        teacher_id = ctx.assigned_teacher_by_section_subject.get((sec_id, subj_id))
        if teacher_id is None:
            continue

        required = _required_sessions(ctx, sec_id, subj_id)
        candidate_slots = list(by_pair[(sec_id, subj_id)])
        rng.shuffle(candidate_slots)

        count = 0
        for slot_id in candidate_slots:
            if count >= required:
                break
            if (sec_id, slot_id) in section_used:
                continue
            if (teacher_id, slot_id) in teacher_used:
                continue

            hints["x"].add((sec_id, subj_id, slot_id))
            section_used.add((sec_id, slot_id))
            teacher_used.add((teacher_id, slot_id))
            count += 1

    return hints


def _hybrid_hints(
    ctx: SolverContext,
    *,
    seed: int | None,
    population_size: int,
    generations: int,
) -> dict[str, set[Any]]:
    hints = _empty_hints()
    var_hints = generate_hybrid_hints(
        ctx,
        seed=seed,
        population_size=int(population_size),
        generations=int(generations),
    )

    x_var_to_key = {var: key for key, var in ctx.x.items()}
    for var, val in var_hints.items():
        if int(val) != 1:
            continue
        key = x_var_to_key.get(var)
        if key is not None:
            hints["x"].add(key)

    return hints


def _required_sessions(ctx: SolverContext, section_id: Any, subject_id: Any) -> int:
    section = next((s for s in ctx.sections if s.id == section_id), None)
    track = str(getattr(section, "track", "CORE") or "CORE")
    override = None
    for sid, sessions_override in ctx.section_required.get(section_id, []):
        if sid == subject_id:
            override = sessions_override
            break

    total = int(ctx.sessions_for(subject_id, track=track, override=override) or 0)
    locked = int(ctx.locked_theory_sessions_by_sec_subj.get((section_id, subject_id), 0) or 0)
    return max(0, total - locked)
