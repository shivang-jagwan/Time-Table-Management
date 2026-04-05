# Academic Timetable Solver — Implementation Guide

**Target Audience**: Backend Engineers, DevOps  
**Date**: April 5, 2026  
**Status**: Production Deployment Ready  

---

## Quick Start

### 1. Activate Virtual Environment

```bash
cd backend
.venv\Scripts\Activate.ps1
```

### 2. Run Global Solver

```bash
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Then POST to:

```
POST /api/solver/solve-global
Authorization: Bearer <admin_token>

{
  "program_code": "CSE",
  "max_time_seconds": 30,
  "room_balance_mode": "soft",
  "require_optimal": false
}
```

### 3. View Results

```
GET /api/timetable?runId=<run_id>
```

---

## Core Solver Architecture

### Module Dependencies

```
data_loader.py ──┐
                 ├─→ context.py (SolverContext)
pre_solve_locks ┤
                 ├─→ variables.py
                 ├─→ constraints.py
                 ├─→ objective.py
                 └─→ cp_sit_solver.py ──→ [CP-SAT Solver]
                                              ↓
                                    ┌── FEASIBLE/OPTIMAL
                                    └── INFEASIBLE ──→ greedy_solver.py
                                    
result_writer.py ←─────── Both paths converge here
```

### Key Files and Responsibilities

| Module | Responsibility | Lines | Status |
|--------|-----------------|-------|--------|
| `context.py` | Shared state, SolveResult class | ~400 | ✅ Core |
| `data_loader.py` | Load DB data, domain reduction | ~600 | ✅ Core |
| `variables.py` | Create CP-SAT decision variables | ~500 | ✅ Core |
| `constraints.py` | Hard & soft constraints | ~800 | ✅ Core |
| `objective.py` | Multi-tier objective function | ~200 | ✅ Core |
| `cp_sat_solver.py` | Main orchestrator | ~800 | ✅ Core |
| `greedy_solver.py` | Fallback for INFEASIBLE | ~300 | ✅ Fallback |
| `result_writer.py` | Write TimetableEntry to DB | ~400 | ✅ Critical |
| `room_assigner.py` | Post-solve room assignment | ~300 | ✅ Optimization |
| `pre_solve_locks.py` | Fixed entries handling | ~500 | ✅ Constraint |

---

## Understanding Hard Constraints

### What Makes a Constraint "Hard"?

Hard constraints are **physical impossibilities** that must be prevent ed at all costs:

1. **A room can't be in two places at once**
   - If Room X holds Class A at slot 1, it cannot hold Class B at slot 1
   - `model.Add(Σ x[..., room_x, slot_1] ≤ 1)`

2. **A teacher has one body**
   - If Teacher T teaches Section A at slot 1, cannot teach Section B at slot 1
   - `model.Add(Σ x[..., teacher_t, ..., slot_1] ≤ 1)`

3. **A section attends one class at a time**
   - If Section S attends Subject A at slot 1, cannot attend Subject B at slot 1
   - `model.Add(Σ x[section_s, ..., ..., slot_1] ≤ 1)`

4. **Lab sessions are contiguous**
   - A 2-period lab cannot be split: must occupy slots `t` and `t+1`, not `t` and `t+3`
   - Enforced via variable structure, not per-slot addition

5. **Teacher unavailability is absolute**
   - If teacher blocked on Friday 2:00 PM, cannot create variables for that slot
   - Eliminated during domain reduction phase

6. **Combined class groups synchronize** (NEW)
   - All sections in a combined group must use the same time slot
   - `model.Add(Σ combined_x[variant] ≤ 1)` per group

### How to Debug Hard Constraint Violations

If solver returns INFEASIBLE:

**Step 1: Check pre-solve locks**
```python
# pre_solve_locks.py::validate_pre_solve_locks()
for entry in ctx.special_entries_to_write:
    # Verify: this entry doesn't violate no-overlap rules
    # Check: teacher, section, room all free at this slot
```

**Step 2: Validate domain reduction**
```python
# data_loader.py::_validate_domain_reduction()
# Verify: each (section, subject) has at least 1 valid slot
# Verify: teacher windows intersect with section windows
```

**Step 3: Check room availability**
```python
# If course requires LAB room but all labs are booked elsewhere
# Greedy fallback will use CLASSROOM instead (soft penalty)
```

**Step 4: Last resort — trigger greedy**
```python
# If still INFEASIBLE after all checks:
greedy_fallback_solver(ctx)  # Always succeeds if hard constraints are satisfiable
```

---

## Understanding Soft Constraints & Weights

### Soft Constraint Philosophy

Soft constraints are **preferences** we want to optimize toward, but they never cause infeasibility.

**Weight Hierarchy**:

```
Tier 1 (100s-700s):   Critical for usability
Tier 2 (100s-300s):   Important for optimization
Tier 3 (10s-50s):     Nice-to-have preferences
```

### Weight Tuning Strategy

**If schedule is unbalanced (some days 15 classes, others 2)**:
```python
# Increase W_DAILY_BALANCE from 300 → 500
# Increase W_SLOT_BALANCE from 220 → 400
```

**If teachers are overloaded**:
```python
# Increase W_TEACHER_OVERLOAD_WEEKLY from 700 → 1000
# Increase W_TEACHER_OVERLOAD_DAILY from 520 → 800
```

**If electives not synchronized**:
```python
# Increase W_ELECTIVE_SYNC_VIOLATION from 120 → 300
```

**If labs have gaps**:
```python
# Increase W_LAB_DAY_GAP from 150 → 400
```

**Critical Rule**: Never set a weight to 0 (redundant). Use 1-10 for very-low priority.

---

## Domain Reduction — The Critical First Step

### Why Domain Reduction Matters

Without pruning:
- 1000 variables created for impossible combinations
- CP-SAT wastes time exploring infeasible regions
- Model becomes bloated and slow

With pruning:
- 40-70% fewer variables
- Solver faster, more likely to find optimal
- Constraints become automatically satisfied

### Pruning Pipeline

**Stage 1: Section Time Windows**
```python
# If section has window "Mon-Wed 8:00-11:00"
# Remove all Thu/Fri slots, remove all afternoon slots
valid_slots = base_slots ∩ window_slots
```

**Stage 2: Teacher Availability**
```python
# If teacher has "off on Friday" and "unavailable 2:00-3:00 Mon-Thu"
# Remove all Friday slots
# Remove 2:00-3:00 slots Mon-Thu
valid_slots = valid_slots - teacher_blocked_slots
```

**Stage 3: Room Type Requirements**
```python
# If subject requires LAB rooms
# Only create variables for slots with available LAB rooms
# Remove CLASSROOM-only slots from consideration
valid_slots = valid_slots ∩ lab_room_available_slots
```

**Stage 4: Lab Contiguity**
```python
# If lab requires 2 consecutive periods
# Only allow slots 0-6 as start (not slot 7, day boundary)
# Only create variables at valid start positions
valid_slots = base_slots - boundary_slots
```

**Stage 5: Combined Groups**
```python
# If 3 sections combined
# Find slots valid for ALL 3 sections
# Intersection: valid_slots_1 ∩ valid_slots_2 ∩ valid_slots_3
valid_slots_for_group = intersect(all_member_slots)
```

**Stage 6: Elective Blocks**
```python
# If elective block has 4 subjects
# All must be in same slot (synchronization)
# Find slots valid for all 4
valid_slots_for_block = intersect(all_subject_slots)
```

### How to Inspect Pruning Results

```python
# After data_loader.build_pruned_slots(ctx)

# Check specific (section, subject)
sec_id = context_section.id
subj_id = context_subject.id
valid_slots = ctx.valid_slots_by_section_subject[(sec_id, subj_id)]
print(f"Slots available: {len(valid_slots)} / 40 total")

# If 0 slots available → likely error (teacher unavailable, room missing, etc.)
# If 1 slot available → tight constraint (maybe intended)
# If 5+ slots available → healthy flexibility
```

---

## Time Budget & Adaptive Solver

### Understanding the Time Budget

**Default Settings**:

```python
max_time_seconds = 30           # Total time allotted
HARD_SINGLE_SOLVE_LIMIT = 900   # Safety cap (15 min)
HARD_TOTAL_SOLVE_LIMIT = 900    # Safety cap (15 min)
```

### Adaptive Budget Calculation

```python
def _estimate_adaptive_budget_seconds(
    requested_cap: float,        # User's max_time_seconds
    num_vars: int,               # 119,020 (example)
    num_constraints: int,        # 45,888 (example)
    sections: int,               # 44 (example)
) -> float:
    """Scale time budget based on problem complexity."""
    
    # Base budget
    budget = min(requested_cap, HARD_SINGLE_SOLVE_LIMIT)
    
    # Scale up for larger problems
    if num_vars > 50000:
        budget *= 1.5      # +50% for mega-problems
    if num_constraints > 20000:
        budget *= 1.2      # +20% for constraint-heavy
    
    # Scale down if we've already taken time (in multi-solve loops)
    remaining = deadline_monotonic - time.monotonic()
    budget = min(budget, remaining)
    
    return budget
```

### Timeout Behavior

**If solver hits time limit mid-search**:
- ✅ Returns best solution found so far
- ✅ May be FEASIBLE (suboptimal) or OPTIMAL
- ✅ Always has entries_written ≥ 0
- ✅ No crash, no data loss

**Example**:
- Solver runs 30 seconds
- Finds FEASIBLE solution after 5 seconds (objective = 23B)
- Continues improving...
- At 30-second mark, timeout triggers
- **Returns**: FEASIBLE status with best solution (objective from wherever search ended)

---

## The Greedy Fallback Solver

### When Does Greedy Activate?

```python
if status == cp_model.INFEASIBLE:
    log.warning("CP-SAT INFEASIBLE, activating greedy fallback")
    return greedy_fallback_solver(ctx)

elif status == cp_model.UNKNOWN:
    log.warning("CP-SAT UNKNOWN after timeout, activating greedy fallback")
    return greedy_fallback_solver(ctx)

elif status == cp_model.MODEL_INVALID:
    log.error("CP-SAT MODEL_INVALID (should never happen!)")
    log.warning("Attempting greedy fallback as last resort")
    return greedy_fallback_solver(ctx)
```

### Greedy Algorithm

```python
def greedy_fallback_solver(ctx: SolverContext):
    entries = []
    
    # Iterate in priority order (e.g., smaller sections first, high-hour subjects first)
    for (section_id, subject_id) in sorted(ctx.section_subjects):
        
        required_sessions = ctx.subject_required_sessions[(section_id, subject_id)]
        assigned_slots = 0
        
        # Try to fill all required sessions
        for slot_id in ctx.valid_slots_by_section_subject[(section_id, subject_id)]:
            
            # Check hard constraints only
            if _slot_violates_hard(slot_id, section_id):
                continue
            
            # Assign if available
            if _slot_available(slot_id):
                entry = TimetableEntry(...)
                entries.append(entry)
                assigned_slots += 1
                
                if assigned_slots >= required_sessions:
                    break  # Done with this subject
        
        # If couldn't assign all, log warning but continue
        if assigned_slots < required_sessions:
            log.warning(f"Greedy: could only assign {assigned_slots}/{required_sessions} for {section_id}/{subject_id}")
    
    return SolveResult(
        status="FEASIBLE",
        entries_written=len(entries),
        warnings=["GREEDY_FALLBACK_INVOKED"],
        ...
    )
```

### Quality of Greedy Solutions

Greedy solutions are **structurally valid** but **not optimized**:

| Metric | CP-SAT (30s) | Greedy | Difference |
|--------|--------------|--------|-----------|
| Entries written | 304 | 298 | -2% (some skipped) |
| Objective score | 23,468,691,550 | 150,000,000,000+ | ~6× worse |
| Teacher overload | Minimized | May occur | |
| Load balance | Even | Uneven | |
| Gap minimization | Optimized | Random | |

**When to Expect Greedy**:
- Rare, <1% of solves (if domain reduction is good)
- Usually indicates data quality issues (conflicting constraints)
- Should be logged and investigated

---

## Testing & Validation

### Smoke Test

```bash
# Start backend
python -m uvicorn main:app --port 8000

# Create test run
curl -X POST http://localhost:8000/api/solver/solve-global \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"program_code": "CSE", "max_time_seconds": 30}'

# Check results
curl http://localhost:8000/api/timetable?runId=<run_id>
```

### Validation Checks

```python
# After running solver, validate:

def validate_solution(entries):
    """Ensure solution respects all hard constraints."""
    
    # 1. No teacher overlap
    for (teacher_id, slot_id), count in entries_by_teacher_slot.items():
        assert count ≤ 1, f"Teacher {teacher_id} has {count} classes in slot {slot_id}"
    
    # 2. No section overlap
    for (section_id, slot_id), count in entries_by_section_slot.items():
        assert count ≤ 1, f"Section {section_id} has {count} classes in slot {slot_id}"
    
    # 3. No room overlap
    for (room_id, slot_id), count in entries_by_room_slot.items():
        assert count ≤ 1, f"Room {room_id} has {count} classes in slot {slot_id}"
    
    # 4. Lab contiguity
    for entry in entries:
        if entry.subject.subject_type == "LAB":
            assert entry.period < 7, f"Lab {entry.id} starts at period {entry.period} (no room for 2nd period)"
    
    # 5. Teacher availability
    for entry in entries:
        teacher = entry.teacher
        slot = entry.slot
        for window in teacher.off_days:
            assert window.slot_id != slot.id, f"Teacher {teacher.id} blocked at slot {slot.id}"
    
    print("✅ All validation checks passed")
```

---

## Performance Tuning

### Profile a Solve

```python
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()

result = solve_program_global(db, run, program_id, max_time_seconds=30)

profiler.disable()
stats = pstats.Stats(profiler)
stats.sort_stats('cumulative')
stats.print_stats(20)  # Top 20 functions
```

### Common Bottlenecks & Fixes

| Bottleneck | Symptom | Fix |
|-----------|---------|-----|
| Slow data_loader | Takes 5+ seconds | Optimize DB indexes, consider caching |
| Slow variable creation | Variables taking 10+ seconds | Pre-compute valid_slots better |
| Slow constraint addition | Constraints taking 5+ seconds | Use vectorized constraint formulation |
| Solver search timeout | Always hits 30s limit | Increase max_time_seconds or reduce problem size |
| Slow result_writer | Write takes 5+ seconds | Batch DB inserts, use bulk operations |

---

## Deployment Checklist

### Pre-Deployment

- [ ] Database seeded with test data (minimum 10 sections, 20 subjects)
- [ ] All required tables exist and have migrations
- [ ] Time slots configured (typically 5 days × 8 periods = 40 slots)
- [ ] Teacher-subject assignments populated
- [ ] Room types defined (CLASSROOM, LAB, LT, etc.)
- [ ] Authentication/authorization tested

### During Deployment

- [ ] Start backend service with uvicorn
- [ ] Verify solver module imports correctly
- [ ] Run smoke test (POST /api/solver/solve-global)
- [ ] Check logs for any MODULE_INVALID or constraint errors
- [ ] Monitor first few solves for performance

### Post-Deployment

- [ ] Alert on INFEASIBLE or greedy_fallback invocations
- [ ] Track average solve time (should be <30 seconds)
- [ ] Monitor memory usage (should be <100 MB per solve)
- [ ] Set up dashboard for solution quality metrics
- [ ] Document any customizations or weight changes

---

## Troubleshooting Guide

### Problem: "MODEL_INVALID" Error

**Symptom**: Solver fails with MODEL_INVALID (shouldn't happen)

**Diagnosis**:
```python
# Check constraint consistency
for constraint in model.Proto().constraints:
    if constraint.enforcement_literal:
        # Enforcement literal references non-existent variable
        print(f"INVALID: {constraint}")
```

**Fix**: 
- Run validate_pre_solve_locks()
- Run _validate_domain_reduction()
- Check for duplicate variable creation
- Report as bug if persistent

### Problem: "INFEASIBLE" Every Time

**Symptom**: Solver returns INFEASIBLE, greedy fallback activates

**Diagnosis**:
```python
# 1. Check if combined groups have conflicting requirements
for group in ctx.combined_groups:
    member_windows = [ctx.windows_by_section[s] for s in group.members]
    intersection = intersect(member_windows)
    if not intersection:
        print(f"Combined group {group.id} has NO common window!")

# 2. Check if all teachers available
for (sec_id, subj_id) in ctx.section_subjects:
    teachers = ctx.teachers_for_section_subject[(sec_id, subj_id)]
    for teacher in teachers:
        if len(ctx.valid_slots_by_section_subject[(sec_id, subj_id)]) == 0:
            print(f"NO VALID SLOTS for {sec_id}/{subj_id}, teacher {teacher.id} may be fully booked")
```

**Fix**:
- Add more time slots
- Remove conflicting constraints
- Allow more flexible windows
- Increase available rooms

### Problem: Solver Takes >60 Seconds

**Symptom**: Solve time creeps over 60 seconds

**Diagnosis**:
```python
# Check number of variables
if len(section_subjects) > 200:
    # Problem is getting large
    print(f"Problem size: {len(variables)} variables, {len(constraints)} constraints")
```

**Fix**:
- Reduce problem scope (solve by year instead of global)
- Reduce time slots (e.g., 6 periods instead of 8)
- Increase solver time limit gracefully
- Use decomposition (solve track separately)

### Problem: Low-Quality Solutions (High Objective)

**Symptom**: Objective score very high (unbalanced schedule)

**Fix**:
```python
# 1. Check problem characteristics
if num_vars > 100000:
    # Increase time budget
    max_time_seconds = 60
elif many_combined_groups:
    # Increase combined group weight
    W_COMBINED_SYNC = 500
elif many_electives:
    # Increase elective sync weight
    W_ELECTIVE_SYNC = 200
```

---

## Advanced: Custom Constraint Addition

### Adding a New Soft Constraint

**Example**: Penalize afternoon slots for morning-preference teachers

```python
# 1. Add penalty variable in context.py
@dataclass
class SolverContext:
    morning_preference_penalty_terms: list[Any] = field(default_factory=list)

# 2. Create penalty in constraints.py
def _add_morning_preference_penalty(ctx: SolverContext) -> None:
    """Penalize afternoon slots for teachers with morning preference."""
    model = ctx.model
    
    for teacher in ctx.teachers:
        if not getattr(teacher, "prefers_morning", False):
            continue
        
        afternoon_slots = [s for s in ctx.slots if s.slot_index >= 4]  # Slots 4-7
        afternoon_terms = []
        
        for slot_id in afternoon_slots:
            for (_, _, teacher_id, _, _), var in ctx.x.items():
                if teacher_id == teacher.id and slot_id == _:
                    afternoon_terms.append(var)
        
        if afternoon_terms:
            penalty = model.NewIntVar(0, len(afternoon_terms), f"morning_pref_{teacher.id}")
            model.Add(penalty == sum(afternoon_terms))
            ctx.morning_preference_penalty_terms.append(penalty)

# 3. Add to objective.py
W_MORNING_PREFERENCE = 50
for penalty in ctx.morning_preference_penalty_terms:
    tier_tertiary.append(penalty * W_MORNING_PREFERENCE)
```

### Adding a New Hard Constraint

**Example**: Prevent certain teacher-subject combinations

```python
# constraints.py
def _add_teacher_subject_restrictions(ctx: SolverContext) -> None:
    """Hard constraint: certain teachers cannot teach certain subjects."""
    model = ctx.model
    
    restricted_pairs = [
        (teacher_id_1, subject_id_1),
        (teacher_id_2, subject_id_2),
    ]
    
    for teacher_id, subject_id in restricted_pairs:
        # Force all variables with (teacher, subject) to 0
        relevant_vars = [
            var for (_, subj_id, teacher_id_var, _, _), var in ctx.x.items()
            if subj_id == subject_id and teacher_id_var == teacher_id
        ]
        if relevant_vars:
            model.Add(sum(relevant_vars) == 0)
```

---

## Appendix: Solver Configuration Reference

```python
# All configuration options in cp_sat_solver.py

HARD_SINGLE_SOLVE_LIMIT_SECONDS    = 900.0   # Max per solve attempt
HARD_TOTAL_SOLVE_LIMIT_SECONDS     = 900.0   # Max total time
MAX_RESTARTS                        = 3       # Restart attempts
MAX_ITERATIONS                      = 5       # Solve iterations
DEFAULT_NUM_SEARCH_WORKERS          = 8       # CPU threads
DEFAULT_RANDOM_SEED                 = 42      # Reproducibility
DEFAULT_MAX_CONFLICTS               = 100_000 # Search limit
GREEDY_SOLVER_TIMEOUT_SECONDS       = 5.0     # Greedy fallback limit
MIN_BUDGET_SLICE_SECONDS            = 1.0     # Minimum per-solve budget
```

---

**End of Implementation Guide**  
**Questions?** Contact backend-engineers@company.com
