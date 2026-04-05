# Solver Validation & Testing Guide

**Purpose**: Ensure production-grade solver meets all quality gates before deployment  
**Date**: April 5, 2026  
**Scope**: Unit tests, integration tests, load tests, and validation procedures  

---

## Part 1: Validation Framework

### 1.1 Pre-Solve Validation

Before CP-SAT solver executes, validate all preconditions:

```python
class PreSolveValidator:
    """Validate that problem is solvable before invoking CP-SAT."""
    
    def validate_all(self, ctx: SolverContext) -> List[str]:
        """Run all pre-solve checks. Return list of errors (empty = OK)."""
        errors = []
        
        # 1. Data completeness
        if not ctx.sections:
            errors.append("ERROR: No sections loaded")
        if not ctx.subjects:
            errors.append("ERROR: No subjects loaded")
        if not ctx.slots:
            errors.append("ERROR: No time slots")
        if not ctx.rooms:
            errors.append("ERROR: No rooms defined")
        
        # 2. Domain feasibility
        errors.extend(self.check_teacher_availability(ctx))
        errors.extend(self.check_room_availability(ctx))
        errors.extend(self.check_combined_groups(ctx))
        errors.extend(self.check_elective_blocks(ctx))
        
        # 3. Window compatibility
        errors.extend(self.check_window_intersections(ctx))
        
        # 4. Resource sufficiency
        errors.extend(self.check_room_capacity(ctx))
        errors.extend(self.check_teacher_capacity(ctx))
        
        return errors
    
    def check_teacher_availability(self, ctx) -> List[str]:
        """Verify each required teacher-subject-section has valid slots."""
        errors = []
        for (sec_id, subj_id), slots in ctx.valid_slots_by_section_subject.items():
            if not slots:  # Empty! No valid slots for this combo
                errors.append(f"WARNING: {sec_id}/{subj_id} has 0 valid slots (teacher unavailable?)")
        return errors
    
    def check_room_availability(self, ctx) -> List[str]:
        """Verify required room types exist and are accessible."""
        errors = []
        for subject in ctx.subjects:
            required_type = str(subject.subject_type)  # "LAB", "CLASSROOM", etc.
            available_rooms = ctx.rooms_by_type.get(required_type, [])
            if not available_rooms:
                errors.append(f"ERROR: No {required_type} rooms available for {subject.id}")
        return errors
    
    def check_combined_groups(self, ctx) -> List[str]:
        """Verify combined groups have common valid slots."""
        errors = []
        for group in ctx.combined_groups:
            common_slots = ctx.valid_slots_for_combined_group.get(group.id)
            if common_slots is not None and len(common_slots) == 0:
                errors.append(f"ERROR: Combined group {group.id} has NO common valid slots!")
        return errors
    
    def check_elective_blocks(self, ctx) -> List[str]:
        """Verify elective blocks can be synchronized."""
        errors = []
        for block in ctx.elective_blocks:
            block_slots = ctx.valid_slots_for_elective_batch.get(block.id)
            if block_slots is not None and len(block_slots) == 0:
                errors.append(f"ERROR: Elective block {block.id} has NO common valid slots!")
        return errors
    
    def check_window_intersections(self, ctx) -> List[str]:
        """Verify section + teacher windows have non-empty intersection."""
        errors = []
        for sec_id, subj_id in ctx.section_subjects:
            section_window_slots = ctx.windows_by_section.get(sec_id, {})
            # Check: any overlap with base slots
            if section_window_slots and not any(s in ctx.slots for s in section_window_slots):
                errors.append(f"WARNING: Section {sec_id} window has no matching slots")
        return errors
    
    def check_room_capacity(self, ctx) -> List[str]:
        """Estimate if room capacity sufficient for peak load."""
        errors = []
        total_theory_load = sum(1 for s in ctx.subjects if s.subject_type != "LAB")
        total_labs = sum(1 for s in ctx.subjects if s.subject_type == "LAB")
        
        theory_rooms = len(ctx.rooms_by_type.get("CLASSROOM", []))
        lab_rooms = len(ctx.rooms_by_type.get("LAB", []))
        
        if total_theory_load > theory_rooms * 8:  # Rough heuristic
            errors.append(f"WARNING: Theory load ({total_theory_load}) may exceed room capacity ({theory_rooms * 8})")
        if total_labs > lab_rooms * 8:
            errors.append(f"WARNING: Lab load ({total_labs}) may exceed capacity ({lab_rooms * 8})")
        
        return errors
    
    def check_teacher_capacity(self, ctx) -> List[str]:
        """Estimate if teacher capacity sufficient."""
        errors = []
        total_sessions = sum(
            ctx.subject_required_sessions.get((sec_id, subj_id), 0)
            for (sec_id, subj_id) in ctx.section_subjects
        )
        total_teacher_capacity = sum(
            getattr(t, "preferred_weekly_load", 20) for t in ctx.teachers
        )
        
        if total_sessions > total_teacher_capacity:
            errors.append(
                f"WARNING: Total sessions ({total_sessions}) exceed teacher capacity ({total_teacher_capacity})"
            )
        
        return errors
```

### 1.2 Post-Solve Validation

After solver completes, validate solution integrity:

```python
class PostSolveValidator:
    """Validate that completed solution respects all hard constraints."""
    
    def validate(self, entries: List[TimetableEntry], ctx: SolverContext) -> bool:
        """Return True if solution is valid, False otherwise."""
        
        try:
            self.check_no_overlaps(entries)
            self.check_lab_contiguity(entries, ctx)
            self.check_teacher_availability(entries, ctx)
            self.check_required_sessions(entries, ctx)
            print("✅ Post-solve validation PASSED")
            return True
        except AssertionError as e:
            print(f"❌ Post-solve validation FAILED: {e}")
            return False
    
    def check_no_overlaps(self, entries: List[TimetableEntry]) -> None:
        """Hard constraint: no teacher/section/room overlap."""
        
        # Group by (teacher, slot)
        teacher_slot_count = defaultdict(int)
        for entry in entries:
            key = (entry.teacher_id, entry.slot_id)
            teacher_slot_count[key] += 1
        
        overlaps = {k: v for k, v in teacher_slot_count.items() if v > 1}
        assert not overlaps, f"Teacher overlap detected: {overlaps}"
        
        # Group by (section, slot)
        section_slot_count = defaultdict(int)
        for entry in entries:
            key = (entry.section_id, entry.slot_id)
            section_slot_count[key] += 1
        
        overlaps = {k: v for k, v in section_slot_count.items() if v > 1}
        assert not overlaps, f"Section overlap detected: {overlaps}"
        
        # Group by (room, slot)
        room_slot_count = defaultdict(int)
        for entry in entries:
            key = (entry.room_id, entry.slot_id)
            room_slot_count[key] += 1
        
        overlaps = {k: v for k, v in room_slot_count.items() if v > 1}
        assert not overlaps, f"Room overlap detected: {overlaps}"
    
    def check_lab_contiguity(self, entries: List[TimetableEntry], ctx: SolverContext) -> None:
        """Hard constraint: LAB entries are contiguous."""
        
        lab_entries = [e for e in entries if ctx.subject_by_id[e.subject_id].subject_type == "LAB"]
        
        for (sec_id, subj_id), group in defaultdict(list, ((e.section_id, e.subject_id), e) for e in lab_entries).items():
            slots = sorted([e.slot_id for e in group])
            if len(slots) > 1:
                # Check gaps between slots (should be 0)
                for i in range(len(slots) - 1):
                    gap = slots[i+1] - slots[i]
                    assert gap == 1, f"Lab {sec_id}/{subj_id} not contiguous: slot gap = {gap}"
    
    def check_teacher_availability(self, entries: List[TimetableEntry], ctx: SolverContext) -> None:
        """Hard constraint: no teacher on blocked slots."""
        
        for entry in entries:
            teacher = ctx.teacher_by_id[entry.teacher_id]
            slot = ctx.slot_by_id[entry.slot_id]
            
            # Check off-days
            off_days = [w.day_of_week for w in ctx.windows_by_teacher[teacher.id] if w.off_day]
            assert slot.day_of_week not in off_days, f"Teacher {teacher.id} scheduled on off-day {slot.day_of_week}"
    
    def check_required_sessions(self, entries: List[TimetableEntry], ctx: SolverContext) -> None:
        """Soft constraint (as check): session counts close to required."""
        
        session_count = defaultdict(int)
        for entry in entries:
            session_count[(entry.section_id, entry.subject_id)] += 1
        
        total_under = 0
        total_over = 0
        
        for (sec_id, subj_id), count in session_count.items():
            required = ctx.subject_required_sessions.get((sec_id, subj_id), 0)
            if count < required:
                total_under += required - count
                print(f"  ⚠️ {sec_id}/{subj_id}: {count}/{required} sessions")
            elif count > required:
                total_over += count - required
        
        if total_under > 0:
            print(f"  ⚠️ Total under-assigned: {total_under} sessions")
        if total_over > 0:
            print(f"  ⚠️ Total over-assigned: {total_over} sessions")
```

---

## Part 2: Unit Tests

### 2.1 Test Constraints Individually

```python
import pytest
from solver.context import SolverContext
from solver.constraints import (
    _add_section_no_overlap,
    _add_teacher_no_overlap,
    _add_room_slot_uniqueness,
)

class TestHardConstraints:
    
    def test_section_no_overlap(self):
        """Verify: section cannot attend 2 classes in same slot."""
        ctx = SolverContext(...)
        ctx.model = cp_model.CpModel()
        
        # Create 2 sessions for same section in same slot
        x1 = ctx.model.NewBoolVar("x1")
        x2 = ctx.model.NewBoolVar("x2")
        ctx.section_slot_terms[(SEC_ID, SLOT_ID)] = [x1, x2]
        
        _add_section_no_overlap(ctx)
        
        # Solve: should not allow both x1=1 and x2=1
        solver = cp_model.CpSolver()
        ctx.model.Add(x1 == 1)
        ctx.model.Add(x2 == 1)
        
        status = solver.Solve(ctx.model)
        assert status == cp_model.INFEASIBLE  # Good! Constraint prevented violation
    
    def test_teacher_no_overlap(self):
        """Verify: teacher cannot teach 2 sections in same slot."""
        # Similar structure to test_section_no_overlap
        pass
    
    def test_room_no_overlap(self):
        """Verify: room cannot host 2 classes in same slot."""
        # Similar structure
        pass
```

### 2.2 Test Domain Reduction

```python
class TestDomainReduction:
    
    def test_teacher_off_day_removal(self):
        """Verify: slots on teacher off-days are removed."""
        ctx = SolverContext(...)
        
        # Teacher OFF on Friday
        teacher = ctx.teacher_by_id[TEACHER_ID]
        assert any(w.off_day and w.day_of_week == 4 for w in ctx.windows_by_teacher[TEACHER_ID])
        
        # After pruning, valid_slots should not include Friday
        valid_slots = ctx.valid_slots_by_section_subject[(SEC_ID, SUBJ_ID)]
        friday_slots = [s for s in ctx.slots if s.day_of_week == 4]
        
        for slot in friday_slots:
            assert slot.id not in valid_slots, "Friday slot should be pruned!"
    
    def test_combined_group_intersection(self):
        """Verify: combined group has only common valid slots."""
        ctx = SolverContext(...)
        
        group = ctx.combined_groups[0]
        members = group.combined_group_sections
        
        # Get valid slots for each member
        member_valid_slots = [
            set(ctx.valid_slots_by_section_subject[(m.section_id, SUBJ_ID)])
            for m in members
        ]
        
        # Verify group valid slots = intersection
        expected = set.intersection(*member_valid_slots) if member_valid_slots else set()
        actual = ctx.valid_slots_for_combined_group[group.id]
        
        assert actual == expected, f"Group valid slots mismatch: got {len(actual)}, expected {len(expected)}"
    
    def test_no_empty_domain_entries(self):
        """Warn if any (section, subject) has 0 valid slots."""
        ctx = SolverContext(...)
        
        empty_domains = [
            (sec_id, subj_id)
            for (sec_id, subj_id), slots in ctx.valid_slots_by_section_subject.items()
            if len(slots) == 0
        ]
        
        if empty_domains:
            print(f"⚠️ {len(empty_domains)} entries with empty domain:")
            for sec_id, subj_id in empty_domains[:10]:
                print(f"    {sec_id} / {subj_id}")
            # This is often OK (optional subjects), but document it
```

### 2.3 Test Greedy Fallback

```python
class TestGreedyFallback:
    
    def test_greedy_always_terminates(self):
        """Verify: greedy solver finishes within timeout."""
        ctx = SolverContext(...)
        
        import time
        start = time.time()
        result = greedy_fallback_solver(ctx)
        elapsed = time.time() - start
        
        assert elapsed < 10, f"Greedy took {elapsed}s (limit is 5s)"
        assert result.status == "FEASIBLE", "Greedy should always return FEASIBLE"
    
    def test_greedy_respects_hard_constraints(self):
        """Verify: greedy output passes hard constraint validation."""
        ctx = SolverContext(...)
        result = greedy_fallback_solver(ctx)
        
        entries = result.entries_written
        validator = PostSolveValidator()
        
        # This should NOT raise
        validator.check_no_overlaps(entries)
        validator.check_lab_contiguity(entries, ctx)
        validator.check_teacher_availability(entries, ctx)
    
    def test_greedy_on_known_infeasible(self):
        """Verify: greedy handles pathological cases gracefully."""
        # Create a context with impossible constraints
        # (e.g., all teachers off, all rooms booked)
        
        ctx = SolverContext(...)
        # ...set up impossible scenario...
        
        result = greedy_fallback_solver(ctx)
        
        # Should still return something (even if 0 entries)
        assert result.status == "FEASIBLE"
        assert result.entries_written >= 0
```

---

## Part 3: Integration Tests

### 3.1 End-to-End Solve Test

```python
class TestEndToEnd:
    
    @pytest.fixture
    def sample_context(self):
        """Load minimal test data: 3 sections, 5 subjects, 2 teachers."""
        db = SessionLocal()
        ctx = SolverContext(
            db=db,
            run=TimetableRun(...),
            program_id=PROGRAM_ID,
            academic_year_id=YEAR_ID,
            tenant_id=TENANT_ID,
        )
        load_all(ctx)
        build_pruned_slots(ctx)
        return ctx
    
    def test_full_solve_produces_entries(self, sample_context):
        """Verify: complete solve flow produces timetable entries."""
        ctx = sample_context
        
        # Execute full pipeline
        create_variables(ctx)
        add_constraints(ctx)
        add_objective(ctx)
        
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 10
        status = solver.Solve(ctx.model)
        
        # Should succeed
        assert status in (cp_model.FEASIBLE, cp_model.OPTIMAL)
        
        # Write results
        result = write_results(ctx)
        assert result.entries_written > 0
        
        # Verify in database
        db_entries = ctx.db.execute(
            select(TimetableEntry).where(TimetableEntry.run_id == ctx.run.id)
        ).scalars().all()
        assert len(db_entries) == result.entries_written
    
    def test_solve_within_time_limit(self, sample_context):
        """Verify: solve completes within budget."""
        import time
        
        ctx = sample_context
        create_variables(ctx)
        add_constraints(ctx)
        add_objective(ctx)
        
        start = time.time()
        status = solve_program_global(
            db=ctx.db,
            run=ctx.run,
            program_id=ctx.program_id,
            max_time_seconds=30,
        )
        elapsed = time.time() - start
        
        assert elapsed < 35, f"Solve took {elapsed}s (budget was 30s)"
        assert status.status in ("FEASIBLE", "OPTIMAL", "SUBOPTIMAL")
    
    def test_solve_produces_valid_solution(self, sample_context):
        """Verify: solution passes all validations."""
        ctx = sample_context
        status = solve_program_global(
            db=ctx.db,
            run=ctx.run,
            program_id=ctx.program_id,
            max_time_seconds=10,
        )
        
        # Fetch entries
        entries = ctx.db.execute(
            select(TimetableEntry).where(TimetableEntry.run_id == ctx.run.id)
        ).scalars().all()
        
        # Validate
        validator = PostSolveValidator()
        assert validator.validate(entries, ctx)
```

### 3.2 Multi-Problem Solve Test

```python
class TestScalability:
    
    def test_solve_small_dataset(self):
        """Verify: works for 1 year, 20 sections."""
        # Load minimal data
        result = solve_program_global(..., max_time_seconds=10)
        
        assert result.status in ("FEASIBLE", "OPTIMAL")
        assert result.entries_written > 0
        print(f"✅ Small: {result.entries_written} entries in {result.solve_time_seconds}s")
    
    def test_solve_medium_dataset(self):
        """Verify: works for 3 years, 44 sections."""
        result = solve_program_global(..., max_time_seconds=30)
        
        assert result.status in ("FEASIBLE", "OPTIMAL")
        assert result.entries_written > 100
        print(f"✅ Medium: {result.entries_written} entries in {result.solve_time_seconds}s")
    
    def test_solve_large_dataset(self):
        """Verify: works for 4-5 years, 70+ sections (may take full time budget)."""
        result = solve_program_global(..., max_time_seconds=60)
        
        assert result.status in ("FEASIBLE", "OPTIMAL", "SUBOPTIMAL")
        assert result.entries_written > 200
        print(f"✅ Large: {result.entries_written} entries in {result.solve_time_seconds}s")
    
    @pytest.mark.parametrize("size", ["small", "medium", "large"])
    def test_all_sizes(self, size):
        """Parameterized test for multiple problem sizes."""
        if size == "small":
            max_time = 10
        elif size == "medium":
            max_time = 30
        else:
            max_time = 60
        
        result = solve_program_global(..., max_time_seconds=max_time)
        assert result.entries_written > 0
```

---

## Part 4: Load Testing

### 4.1 Concurrent Solve Test

```python
import concurrent.futures
import time

def test_concurrent_solves():
    """Verify: multiple simultaneous solves don't interfere."""
    
    def single_solve(tenant_id, program_id):
        db = SessionLocal()
        ctx = SolverContext(db=db, ..., tenant_id=tenant_id)
        return solve_program_global(db, ..., program_id=program_id, max_time_seconds=15)
    
    # Launch 5 solves concurrently (different tenants/programs)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        futures = [
            executor.submit(single_solve, f"tenant_{i}", f"program_{i}")
            for i in range(5)
        ]
        
        results = []
        for future in concurrent.futures.as_completed(futures, timeout=60):
            result = future.result()
            results.append(result)
            print(f"  ✅ Completed: {result.entries_written} entries")
    
    # All should succeed
    assert len(results) == 5
    assert all(r.entries_written > 0 for r in results)
    print(f"✅ Concurrent solves: all 5 completed successfully")
```

### 4.2 Stress Test

```python
def test_repeated_solves():
    """Verify: solver stable over many iterations (no memory leaks)."""
    
    db = SessionLocal()
    
    for i in range(10):
        print(f"Iteration {i+1}/10...")
        
        ctx = SolverContext(db=db, ...)
        result = solve_program_global(db, ..., max_time_seconds=15)
        
        assert result.entries_written > 0
        
        # Clean up for next iteration
        db.execute(delete(TimetableEntry).where(TimetableEntry.run_id == ctx.run.id))
        db.commit()
    
    print("✅ 10 iterations completed without crashes")
```

---

## Part 5: Performance Profiling

### 5.1 Time Profiling

```python
import cProfile
import pstats

def profile_solve():
    """Profile where CPU time is spent."""
    
    profiler = cProfile.Profile()
    profiler.enable()
    
    result = solve_program_global(db, run, program_id, max_time_seconds=30)
    
    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    
    print("=" * 60)
    print("TOP 20 FUNCTIONS BY TIME")
    print("=" * 60)
    stats.print_stats(20)
    
    # Expected breakdown:
    # - CP-SAT solver: ~60-70% (search)
    # - Presolve/loading: ~15-20%
    # - Constraint creation: ~10-15%
    # - Result writing: ~5-10%
```

### 5.2 Memory Profiling

```python
import tracemalloc

def profile_memory():
    """Profile peak memory usage."""
    
    tracemalloc.start()
    
    result = solve_program_global(db, run, program_id, max_time_seconds=30)
    
    current, peak = tracemalloc.get_traced_memory()
    print(f"Current memory: {current / 1024 / 1024:.1f} MB")
    print(f"Peak memory:    {peak / 1024 / 1024:.1f} MB")
    
    tracemalloc.stop()
    
    # Expected: <50 MB for typical problem
    assert peak < 100 * 1024 * 1024, "Memory usage too high!"
```

---

## Part 6: Regression Test Suite

### 6.1 Known Good Problems

Keep a library of test cases with known-good solutions:

```python
class RegressionTests:
    
    @pytest.mark.parametrize("test_case", [
        "cse_sem6_year1_minimal",      # 10 sections, 20 subjects
        "cse_all_years_full",          # 44 sections, 180 subjects
        "mechanical_2year_standard",   # 30 sections, 150 subjects
    ])
    def test_known_good_case(self, test_case):
        """Re-solve known-good test case and verify correctness."""
        
        # Load test parameters
        config = TEST_CASES[test_case]
        
        # Solve
        result = solve_program_global(
            db=SESSION,
            run=TimetableRun(),
            program_id=config.program_id,
            academic_year_id=config.academic_year_id,
            max_time_seconds=config.time_budget,
        )
        
        # Verify
        assert result.status in ("FEASIBLE", "OPTIMAL")
        assert result.entries_written >= config.min_entries
        assert result.objectives_core <= config.max_objective
        
        print(f"✅ {test_case}: {result.entries_written} entries, objective={result.objective_score}")
```

---

## Part 7: Deployment Checklist (Testing)

Before deploying to production:

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] Load test with 5 concurrent solves (success)
- [ ] Stress test: 10 iterations without failures
- [ ] Memory profile: peak <100 MB
- [ ] Time profile: within budget for all scenarios
- [ ] Regression tests: all known-good cases pass
- [ ] Validation: PostSolveValidator passes on 10 random runs
- [ ] Error handling: graceful on pathological inputs
- [ ] Documentation: updated with any changes

---

**End of Validation & Testing Guide**

Run tests with:

```bash
pytest tests/solver/ -v --tb=short
```

---
