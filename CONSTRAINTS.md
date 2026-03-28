# Constraint System - Smart Timetable Engine

> A technical guide to how constraints are modeled, validated, and optimized in our timetable generation system.

---

## 1. Introduction

Timetable generation is a classic Constraint Satisfaction Problem (CSP) with a strong optimization layer.

Our engine is built using:

- Google OR-Tools (CP-SAT Solver) for exact combinatorial search
- Custom optimization and validation logic for domain-specific academic rules

At runtime, the pipeline enforces constraints in two stages:

- Pre-solve validation: data integrity, eligibility, and feasibility checks
- CP-SAT model solving: hard feasibility plus soft objective minimization

---

## 2. Hard vs Soft Constraints

### Hard Constraints (Must Satisfy)

These constraints are non-negotiable.
If any hard constraint is violated, the timetable is invalid and solver output is rejected.

### Soft Constraints (Optimization Goals)

These constraints are quality preferences.
They can be violated, but each violation adds penalty to the objective, and the solver minimizes total penalty.

---

## 3. HARD CONSTRAINTS (DETAILED)

### 1. Teacher Conflict Constraint

Name: Teacher No-Overlap

Description: A teacher cannot teach more than one class in the same slot.

Enforcement: CP-SAT enforces per-(teacher, slot) occupancy with $\sum vars \le 1$.

Why it matters: Prevents physically impossible schedules and preserves teaching continuity.

---

### 2. Room Conflict Constraint

Name: Room Slot Uniqueness

Description: A room cannot host multiple classes at the same time.

Enforcement: Per-(room, slot) hard cap with fixed/special/locked occupancy included.

Why it matters: Avoids room double-booking and campus-level operational clashes.

---

### 3. Section Conflict Constraint

Name: Section No-Overlap

Description: A section can attend at most one class at any given slot.

Enforcement: For each (section, slot), all class variables sum to at most 1.

Why it matters: Ensures students are never assigned to two simultaneous classes.

---

### 4. Subject Weekly Requirement

Name: Weekly Session Satisfaction

Description: Each section-subject pair must meet required weekly session count.

Enforcement: Solver sets equality on start variables, for example $\sum starts = required - locked$.

Why it matters: Guarantees academic coverage for syllabus completion.

---

### 5. Room Type Constraint

Name: Room Compatibility Constraint

Description: Subjects must be assigned only to compatible room types (especially labs).

Enforcement: Candidate room sets are filtered by subject type and allowed-room mapping.

Example: Microprocessor practical sessions can be restricted to Micro lab only.

Why it matters: Preserves infrastructure correctness and practical delivery quality.

---

### 6. Teacher Availability Constraint

Name: Teacher Availability and Off-Day Constraint

Description: Teachers cannot be scheduled in blocked or unavailable windows.

Enforcement:

- Weekly off-day is a hard zero-assignment day.
- Strict teacher windows prune disallowed slots before variable creation.
- Locked slots from fixed or special classes are also blocked.

Why it matters: Aligns timetables with human availability and institutional workload rules.

---

### 7. Variable-Length Class Constraint

Name: Contiguous Block Scheduling Constraint

Description: Classes with duration greater than 1 must occupy continuous slot blocks.

Enforcement:

- Solver uses start variables and expands them to covered contiguous slots.
- Invalid or non-contiguous starts are not created.

Why it matters: Essential for labs and long sessions that cannot be fragmented.

---

### 8. Exclusive Room Constraint

Name: Exclusive Room Ownership Constraint

Description: Certain rooms are reserved for specific subjects only.

Enforcement:

- Pre-solve validation checks exclusive mappings.
- Conflicting exclusive claims are rejected before solve.

Why it matters: Protects specialized assets and avoids policy-level misuse.

---

### 9. Slot Capacity Constraint (VERY IMPORTANT)

Name: Global Slot Capacity Constraint

Description: Total classes in a slot must not exceed available room capacity.

Enforcement:

- Hard cap on slot load $\le$ active non-special room count.
- Separate theory and lab room demand accounting.

Why it matters: Prevents mathematically infeasible overloading of campus infrastructure.

---

### 10. Elective Block Constraint

Name: Elective Parallel-Block Constraint

Description: Multiple electives for the same learner group must be synchronized in the same time block.

Enforcement:

- Batch-specific elective variables force parallel timing.
- Validation ensures section-to-elective-block mapping exists.

Why it matters: Solves one of the hardest real university scheduling challenges, elective coexistence without cross-conflicts.

---

## 4. SOFT CONSTRAINTS (DETAILED)

### 1. Gap Minimization

Name: Internal Gap Penalty

Description: Penalizes unnecessary idle gaps inside section and teacher daily spans.

Implementation: Span-based and gap Boolean penalties in objective.

Why it matters: Produces compact and practical daily timetables.

---

### 2. Load Balancing (CRITICAL)

Name: Daily and Slot-Level Balance

Description: Spreads classes across days and avoids over-congested slots.

Implementation: Penalizes load deviation and slot overload terms.

Why it matters: Avoids timetable clustering and improves overall schedule quality.

---

### 3. Teacher Load Balance

Name: Teacher Weekly Overload Penalty

Description: Allows overflow only when necessary, but penalizes it strongly.

Implementation: Overflow variable above max_per_week contributes high objective penalty.

Why it matters: Keeps schedules feasible without silently overloading faculty.

---

### 4. Room Utilization Optimization

Name: Room Utilization Smoothing

Description: Improves usage distribution across room-time grid.

Implementation: Slot-load deviation and anti-congestion penalties.

Why it matters: Better utilization of limited infrastructure.

---

### 5. Preferred Time Slots

Name: Time Preference Penalty

Description: Prefers earlier slots and discourages Friday last-slot assignments.

Implementation: Late-slot weighted penalty plus Friday last-slot penalty.

Why it matters: Improves timetable usability for students and faculty.

---

### 6. Section Continuity

Name: Section Continuity Optimization

Description: Tries to keep section schedules compact with fewer internal breaks.

Implementation: Hard max-gap guard plus soft compactness penalties.

Why it matters: Better classroom rhythm and reduced idle periods.

---

## 5. Constraint Implementation Logic

The solver model is built using:

- Binary decision variables for class starts and placements
- Linear constraints for feasibility checks and combinational logic

Typical variable families:

- $x(section, subject, slot)$ for theory starts
- $lab\_start(section, subject, day, start)$ for lab blocks
- $combined\_x(group, slot)$ for combined classes
- $z(block, batch, slot)$ for elective batches

Hard constraints are added as strict equations or inequalities, for example:

- $\sum teacher\_slot\_terms \le 1$
- $\sum room\_slot\_terms \le 1$
- $\sum start\_vars = required\_sessions$

Soft constraints are encoded with penalty variables and weighted objective terms.

The solver minimizes total penalty while strictly satisfying all hard constraints.

---

## 6. Optimization Strategy

Our engine uses layered optimization for quality and robustness:

- Multi-seed solving: tries multiple seeded candidate runs
- LNS (Large Neighborhood Search): destroys and repairs selected schedule neighborhoods
- Load balancing objective terms: daily balance plus slot congestion controls
- Constraint relaxation fallback models teacher overload through penalized overflow variables.
- Optional extended solve pass runs when a feasible solution exists but can still be improved.
- Global decomposition (program-wide): solves in batches while carrying teacher occupancy across batches

---

## 7. Real-World Mapping

These constraints directly map to real institutional constraints:

- Teacher availability windows and weekly off-days
- Limited labs and room-type compatibility
- Elective synchronization for parallel choices
- Combined classes across sections
- Fixed commitments and special allotments
- Room scarcity and peak-slot congestion

This is why the solver behaves like an academic operations engine, not just a toy scheduler.

---

## 8. Conclusion

The constraint framework combines strict feasibility checks with strong optimization objectives.

This constraint system enables the generation of realistic, conflict-free, and optimized timetables for large-scale institutions.
