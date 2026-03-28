# Solver Architecture - Timetable Generation Engine

> A deeply technical and production-aligned guide to how the timetable engine models, validates, solves, optimizes, and scales real academic scheduling workloads.

---

## 1. 🧠 Introduction

Timetable generation is an **NP-hard optimization problem**. The search space grows combinatorially with sections, subjects, teachers, rooms, and slot combinations, so brute-force enumeration is not practical for real institutions.

Our system is built as a hybrid optimization stack:

- **Google OR-Tools CP-SAT Solver** for deterministic constraint satisfaction and objective minimization.
- **Custom Genetic Algorithm (GA) hybrid initializer** for warm-start hint generation on large instances.
- **Hybrid optimization workflow** that combines multi-seed solve, adaptive LNS, and guided warm-starts.

> "Our system combines deterministic optimization with evolutionary techniques to generate high-quality timetables at scale."

---

## 2. 🏗️ High-Level Architecture

```plaintext
User Input -> Validation -> Calculation Engine -> Solver Engine -> Output Timetable
```

### Stage Breakdown

- **User Input**
  - Admin submits program scope (year-wise or global), time budget, and solver options.
  - Input includes optional controls: multi-seed restarts, LNS rounds, hybrid initialization, extended solve.

- **Validation**
  - Structural and feasibility checks run before CP-SAT model creation.
  - Detects impossible configurations (missing assignments, room incompatibility, invalid elective mappings, slot/window deficits).

- **Calculation Engine**
  - Computes transparent pre-solve metrics (teacher overload, section shortages, room bottlenecks, utilization).
  - Generates actionable bottleneck messages for operators.

- **Solver Engine**
  - Builds CP-SAT model: variables, hard constraints, soft penalties, objective.
  - Executes multi-phase optimization (multi-seed, LNS, optional extended improve pass).

- **Output Timetable**
  - Extracts selected decisions, assigns rooms, writes entries and conflicts, persists run telemetry and diagnostics.

---

## 3. ⚙️ Solver Pipeline (STEP-BY-STEP)

### Step 1: Data Loading

The solver context loads all scheduling entities for the selected scope:

- Sections, subjects, teachers, rooms, time slots
- Section time windows and teacher time windows
- Curriculum mappings, elective blocks, combined groups
- Fixed timetable entries and special allotments

Then preprocessing builds reduced candidate domains:

- Slot pruning by window feasibility
- Teacher blocked-slot pruning
- Duration-fit pruning for block classes
- Combined and elective candidate slot precomputation

Result: the model starts with a significantly reduced variable space before search begins.

### Step 2: Pre-Solve Validation

Before model solve, the engine runs deterministic feasibility checks:

- Missing references and inactive entities
- Teacher assignment completeness
- Section window completeness and validity
- Room exclusivity and room-type compatibility
- Combined/elective domain collapse checks
- Capacity deficits (teacher, room type, section)

This stage prevents wasting CP-SAT runtime on structurally impossible inputs.

### Step 3: Variable Creation

The model uses binary decision variables. Core families include:

```plaintext
x[section, subject, slot]            # theory placement
lab_start[section, subject, day, i]  # multi-slot lab start variable
combined_x[group, slot]              # shared theory for combined groups
z[block, batch, slot]                # elective block batch timing
```

Conceptually, this corresponds to patterns like:

```plaintext
x[class, day, period, room]
start[class, day, period]  (for multi-slot classes)
```

Multi-slot subjects are modeled through start variables and contiguous expansion semantics.

### Step 4: Constraint Building

Hard constraints are encoded as strict equations/inequalities:

- Teacher no-overlap
- Section no-overlap
- Room slot uniqueness
- Weekly session satisfaction
- Teacher off-day and workload boundaries
- Contiguous block constraints for labs/long classes
- Room capacity and compatibility constraints
- Elective and combined synchronization constraints

Soft constraints are represented using penalty variables:

- Section and teacher internal gaps
- Subject day spread
- Daily load variance
- Slot congestion and overload
- Late-slot and Friday-last penalties

### Step 5: Objective Function

The objective is **penalty-based minimization** with weighted priorities:

- Minimize section and teacher gaps
- Minimize day/slot imbalance and clustering
- Penalize teacher overload and congested slots
- Prefer earlier slots and avoid poor placement patterns

The weighted objective is solved as a single minimization target, with tiered terms ensuring high-priority quality signals dominate lower-priority refinements.

### Step 6: Solve Execution

The engine configures CP-SAT with production parameters:

- Adaptive time budgeting based on model size
- Multi-threaded search workers
- Presolve and symmetry handling enabled
- Optional random-seed diversification

Execution modes:

- Standard single solve
- Multi-seed restarts (dry candidate solves)
- LNS-guided iterative improvement
- Optional extended improve pass if feasible but not optimal

### Step 7: Result Extraction

After a feasible/optimal solution:

- Selected variables are decoded into timetable entries
- Room assignment is resolved (including elective/combined semantics)
- Conflicts/warnings are persisted for operator visibility
- Run-level metrics are saved (objective, bounds, timing, telemetry)

Final output is returned as a structured timetable payload suitable for UI rendering and reporting.

---

## 4. 🧬 Genetic Algorithm (GA) Integration

### Why GA?

At large scale, pure CP-SAT from a cold start can spend substantial time finding high-quality incumbents. A GA-style initializer helps produce useful candidate hints early.

### GA Components

#### 🧬 Chromosome

A chromosome represents a **candidate timetable assignment** for theory tasks:

- Mapping: (section, subject) -> set of chosen slots

#### 🧬 Gene

A gene represents a **single class placement choice**, typically one slot assignment inside a section-subject schedule.

### 🔁 GA Steps

1. **Initialization**
   - Build a population of random feasible-biased candidates.
2. **Selection (Tournament Selection)**
   - Select parent candidates using tournament winners.
3. **Crossover (Day-block / Class-block)**
   - Combine parent slot sets using day-based partition crossover.
4. **Mutation (slot swap and candidate perturbation)**
   - Perform slot-level swaps to diversify candidates.
5. **Fitness Evaluation**
   - Score candidates and keep stronger offspring.
   - Conflict repair step removes invalid overlaps before evaluation.

### 🎯 Fitness Function

Current production fitness emphasizes **coverage quality**:

- Maximizes satisfied required theory sessions
- Uses conflict repair to enforce no-overlap safety in candidate hints

In practice, this gives CP-SAT a better initialization point without replacing exact optimization.

---

## 5. 🔄 Hybrid GA + CP-SAT Approach

```plaintext
GA -> Generate initial solution hints
   ->
CP-SAT -> Enforce all hard constraints + optimize objective
   ->
Final optimized timetable
```

### How It Works in Production

- GA-like hybrid initializer builds warm-start hints for core decision variables.
- CP-SAT consumes these hints and performs exact constrained optimization.
- LNS rounds further improve incumbents by destroying/rebuilding difficult neighborhoods.
- A lightweight hybrid repair hook exists in the pipeline as an extension point for deeper GA-CP iterative repair.

This hybridization balances exploration (evolutionary candidate diversity) and exploitation (exact CP search).

---

## 6. ⚡ Optimization Techniques

### 1. Multi-Seed Solving

- Runs multiple candidate solves with different seeds and initialization modes.
- Maintains a top solution pool and selects best objective candidate.

### 2. LNS (Large Neighborhood Search)

- Iteratively improves best-known solutions.
- Chooses adaptive destroy strategies (teacher-centric, day-block, high-penalty classes, congested slots).
- Re-solves repaired neighborhoods under focused budgets.

### 3. Load Balancing

- Penalizes uneven daily distributions and slot congestion.
- Encourages smoother utilization across days and periods.

### 4. Constraint Relaxation

- Handles hard-to-satisfy workloads via controlled/penalized mechanisms (for example teacher overload penalties when strict limits are relaxed by policy).
- Supports extended solve and operator-guided retries for infeasible or suboptimal outcomes.

### 5. Parallel Execution

- Parallel dry candidate solves during multi-seed restart phase.
- Parallel CP-SAT worker threads within each solve.

```plaintext
Parallelism Layer A: Candidate-level (multi-seed ThreadPool)
Parallelism Layer B: Solver-level (CP-SAT num_search_workers)
```

---

## 7. 🧠 Scalability Strategy

The system is designed to handle large institutional datasets (for example 70+ sections, 100+ teachers, dense elective/lab constraints).

### Techniques

- **Batch solving (year-wise decomposition)**
  - Program-global solves are partitioned by academic year and optionally sub-chunked by section groups.
- **Global teacher tracking**
  - Teacher slot occupancy is carried across batches to avoid cross-year collisions.
- **Incremental solving**
  - Batches append into the same run, preserving already-committed occupancy and conflicts.

Additional scaling controls:

- Adaptive per-batch time budgets from remaining global budget
- Candidate slot pruning before variable creation
- Bounded hybrid and LNS iteration counts for predictable latency

---

## 8. 📊 Diagnostics & Monitoring

The engine emits operator-grade observability at multiple layers.

### What is monitored

- **Fitness and candidate quality**
  - GA warm-start candidate quality (coverage-driven fitness)
- **Objective and penalties**
  - Objective score, best bound, optimality gap
- **Conflict reports**
  - Structured conflict entities (validation failures, room assignment warnings, infeasibility details)
- **Solve performance**
  - Wall time, branch count, conflict count, status transitions
- **LNS telemetry**
  - Iteration strategy, baseline vs candidate objective, gain, acceptance, EMA strategy score

### Monitoring flow

```plaintext
Pre-solve Metrics -> Capacity/Feasibility Warnings -> Solve Stats -> LNS Telemetry -> Persisted Run Reports
```

These diagnostics support both rapid debugging and long-term quality tuning.

---

## 9. 🧪 Failure Handling

When solving fails or becomes infeasible, the system follows a controlled recovery path.

### If infeasible

- Return deterministic conflict details and reason summary.
- Persist infeasibility diagnostics for UI and operators.

### Retry and recovery options

- **Relax constraints**
  - Use policy-guided relaxation modes where applicable.
- **Retry solving**
  - Increase budget, change seeds, enable hybrid hints, run LNS iterations.
- **Actionable suggestions**
  - Use capacity analysis and bottleneck messages (teacher overload, room shortage, section window shortage) to drive data fixes.

This avoids opaque failures and turns infeasibility into actionable remediation steps.

---

## 10. 💡 Real-World Strength

This is not a toy scheduler. The architecture is engineered for production academic complexity:

- Works on real college datasets
- Handles electives, lab blocks, combined classes, fixed entries, and special allotments
- Supports tenant-aware isolation and persistent run history
- Provides explainable diagnostics to operations teams
- Balances strict feasibility with practical quality optimization

The result is a robust timetable platform suitable for institutional deployment.

---

## 11. 🏁 Conclusion

This solver architecture combines exact constraint programming, evolutionary warm-starting, and adaptive optimization loops into a practical production engine.

> "This architecture ensures scalable, flexible, and optimized timetable generation for real-world institutions."
