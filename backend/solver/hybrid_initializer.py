from __future__ import annotations

import logging
import random
import time
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from solver.context import SolverContext

logger = logging.getLogger(__name__)


@dataclass
class _TheoryTask:
    section_id: Any
    subject_id: Any
    teacher_id: Any
    needed: int
    slot_ids: list[Any]


def _build_theory_tasks(ctx: SolverContext) -> list[_TheoryTask]:
    slot_ids_by_pair: dict[tuple[Any, Any], list[Any]] = defaultdict(list)
    for (sec_id, subj_id, slot_id), _var in ctx.x.items():
        slot_ids_by_pair[(sec_id, subj_id)].append(slot_id)

    tasks: list[_TheoryTask] = []
    for section in ctx.sections:
        track = str(getattr(section, "track", "CORE") or "CORE")
        for subj_id, sessions_override in ctx.section_required.get(section.id, []):
            teacher_id = ctx.assigned_teacher_by_section_subject.get((section.id, subj_id))
            if teacher_id is None:
                continue
            if (section.id, subj_id) not in slot_ids_by_pair:
                continue
            total_sessions = int(ctx.sessions_for(subj_id, track=track, override=sessions_override) or 0)
            locked = int(ctx.locked_theory_sessions_by_sec_subj.get((section.id, subj_id), 0) or 0)
            needed = max(0, total_sessions - locked)
            if needed <= 0:
                continue
            slots = sorted(slot_ids_by_pair[(section.id, subj_id)], key=lambda sid: ctx.slot_info.get(sid, (99, 99)))
            tasks.append(
                _TheoryTask(
                    section_id=section.id,
                    subject_id=subj_id,
                    teacher_id=teacher_id,
                    needed=needed,
                    slot_ids=slots,
                )
            )

    tasks.sort(key=lambda t: len(t.slot_ids))
    return tasks


def _fitness(candidate: dict[tuple[Any, Any], set[Any]], tasks: list[_TheoryTask]) -> int:
    score = 0
    for t in tasks:
        score += min(len(candidate.get((t.section_id, t.subject_id), set())), t.needed)
    return score


def _day(slot_info: dict[Any, tuple[int, int]], slot_id: Any) -> int:
    return int(slot_info.get(slot_id, (0, 0))[0])


def _build_random_candidate(
    ctx: SolverContext,
    tasks: list[_TheoryTask],
    rng: random.Random,
) -> dict[tuple[Any, Any], set[Any]]:
    chosen: dict[tuple[Any, Any], set[Any]] = defaultdict(set)

    section_used = set(ctx.locked_section_slots)
    teacher_used = set(ctx.locked_teacher_slots)

    task_order = list(tasks)
    rng.shuffle(task_order)
    task_order.sort(key=lambda t: len(t.slot_ids))

    for t in task_order:
        pair = (t.section_id, t.subject_id)
        slots = list(t.slot_ids)
        rng.shuffle(slots)
        for slot_id in slots:
            if len(chosen[pair]) >= t.needed:
                break
            sec_key = (t.section_id, slot_id)
            tch_key = (t.teacher_id, slot_id)
            if sec_key in section_used or tch_key in teacher_used:
                continue
            chosen[pair].add(slot_id)
            section_used.add(sec_key)
            teacher_used.add(tch_key)

    return chosen


def _tournament_select(
    population: list[dict[tuple[Any, Any], set[Any]]],
    tasks: list[_TheoryTask],
    rng: random.Random,
    k: int = 3,
) -> dict[tuple[Any, Any], set[Any]]:
    sample = [population[rng.randrange(len(population))] for _ in range(max(1, k))]
    sample.sort(key=lambda c: _fitness(c, tasks), reverse=True)
    return sample[0]


def _day_block_crossover(
    a: dict[tuple[Any, Any], set[Any]],
    b: dict[tuple[Any, Any], set[Any]],
    ctx: SolverContext,
) -> dict[tuple[Any, Any], set[Any]]:
    out: dict[tuple[Any, Any], set[Any]] = defaultdict(set)
    keys = set(a.keys()) | set(b.keys())
    for key in keys:
        for sid in a.get(key, set()):
            if _day(ctx.slot_info, sid) % 2 == 0:
                out[key].add(sid)
        for sid in b.get(key, set()):
            if _day(ctx.slot_info, sid) % 2 == 1:
                out[key].add(sid)
    return out


def _slot_swap_mutation(
    candidate: dict[tuple[Any, Any], set[Any]],
    tasks_by_key: dict[tuple[Any, Any], _TheoryTask],
    rng: random.Random,
) -> None:
    if not candidate:
        return
    key = rng.choice(list(candidate.keys()))
    task = tasks_by_key.get(key)
    if task is None:
        return
    current = candidate.get(key, set())
    available = [sid for sid in task.slot_ids if sid not in current]
    if not current or not available:
        return
    remove_sid = rng.choice(list(current))
    add_sid = rng.choice(available)
    current.remove(remove_sid)
    current.add(add_sid)


def _repair_conflicts(
    candidate: dict[tuple[Any, Any], set[Any]],
    tasks_by_key: dict[tuple[Any, Any], _TheoryTask],
    ctx: SolverContext,
) -> None:
    section_used = set(ctx.locked_section_slots)
    teacher_used = set(ctx.locked_teacher_slots)

    # Deterministic pass: keep slots in chronological order and drop conflicts.
    for key in sorted(candidate.keys(), key=lambda x: str(x)):
        task = tasks_by_key.get(key)
        if task is None:
            candidate[key] = set()
            continue
        kept: set[Any] = set()
        ordered = sorted(candidate.get(key, set()), key=lambda sid: ctx.slot_info.get(sid, (99, 99)))
        for slot_id in ordered:
            sec_key = (task.section_id, slot_id)
            tch_key = (task.teacher_id, slot_id)
            if sec_key in section_used or tch_key in teacher_used:
                continue
            kept.add(slot_id)
            section_used.add(sec_key)
            teacher_used.add(tch_key)
        candidate[key] = kept


def generate_hybrid_hints(
    ctx: SolverContext,
    *,
    seed: int | None,
    population_size: int,
    generations: int,
    deadline_monotonic: float | None = None,
) -> dict[Any, int]:
    """Generate optional warm-start hints using a lightweight GA over theory slots.

    This keeps runtime bounded and safe for production while still providing
    meaningful CP-SAT hints on large instances.
    
    PHASE 10 CRITICAL FIX: Added deadline_monotonic parameter.
    GA now respects time budget and will terminate early if deadline exceeded.
    """
    # Early exit if deadline already exceeded
    if deadline_monotonic is not None:
        remaining = max(0.0, float(deadline_monotonic) - time.monotonic())
        if remaining <= 0.0:
            logger.warning("[solver] Hybrid GA: deadline exceeded at start, returning empty hints")
            return {}
    
    tasks = _build_theory_tasks(ctx)
    if not tasks:
        return {}

    rng = random.Random(seed if seed is not None else 0)
    population: list[dict[tuple[Any, Any], set[Any]]] = [
        _build_random_candidate(ctx, tasks, rng) for _ in range(max(4, population_size))
    ]

    tasks_by_key = {(t.section_id, t.subject_id): t for t in tasks}

    # Adaptive generation count: reduce if near deadline
    max_generations = max(1, generations)
    if deadline_monotonic is not None:
        remaining = max(0.0, float(deadline_monotonic) - time.monotonic())
        # If < 2 seconds remaining, do max 2 generations; < 5 seconds, max 5 generations
        if remaining < 2.0:
            max_generations = min(max_generations, 1)
        elif remaining < 5.0:
            max_generations = min(max_generations, 2)
    
    gen_completed = 0
    for gen_idx in range(max_generations):
        # PHASE 10 CRITICAL: Check deadline before each generation
        if deadline_monotonic is not None:
            remaining = max(0.0, float(deadline_monotonic) - time.monotonic())
            if remaining <= 0.5:  # Leave 500ms buffer
                logger.warning(
                    "[solver] Hybrid GA: deadline approaching (%.1fs left), terminating after %d/%d generations",
                    remaining,
                    gen_idx,
                    max_generations,
                )
                break
        
        new_population: list[dict[tuple[Any, Any], set[Any]]] = []
        while len(new_population) < len(population):
            p1 = _tournament_select(population, tasks, rng)
            p2 = _tournament_select(population, tasks, rng)
            child = _day_block_crossover(p1, p2, ctx)
            if rng.random() < 0.35:
                _slot_swap_mutation(child, tasks_by_key, rng)
            _repair_conflicts(child, tasks_by_key, ctx)
            new_population.append(child)
        population = new_population
        gen_completed += 1

    best = max(population, key=lambda c: _fitness(c, tasks))

    hints: dict[Any, int] = {}
    selected_by_key = {k: set(v) for k, v in best.items()}
    for (sec_id, subj_id, slot_id), var in ctx.x.items():
        if slot_id in selected_by_key.get((sec_id, subj_id), set()):
            hints[var] = 1

    return hints
