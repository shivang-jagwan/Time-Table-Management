# Solver

OR-Tools CP-SAT model and constraints live here.

## Academic-year solver

The solver is scoped by academic year:

- One solve per `(program_id, academic_year_id)` schedules all active sections for that year.

Key consequences:

- Cross-year teacher clashes are enforced by the global teacher no-overlap constraint (not DB-driven slot blocking).
- `timetable_entries.academic_year_id` is still populated per entry (from the section) so year identity is preserved.
- Rooms remain post-processing (greedy assignment with WARN conflicts when no free room exists).

## API

- `POST /api/solver/generate` (JSON body: `{ "program_code": "...", "academic_year_number": 3, "seed": 42 }`)
- `POST /api/solver/solve` (JSON body: `{ "program_code": "...", "academic_year_number": 3, "seed": 42, "max_time_seconds": 60, "relax_teacher_load_limits": false, "require_optimal": true }`)

## Program-wide solver (all years)

As of this update, the solver also supports a true program-wide mode:

- One solve schedules **all active sections for a program across all academic years** in a single CP-SAT model.
- This removes academic year from the solve scope (it is inferred from each section).

### Endpoints

- `POST /api/solver/generate-global` (JSON body: `{ "program_code": "...", "seed": 42 }`)
- `POST /api/solver/solve-global` (JSON body: `{ "program_code": "...", "seed": 42, "max_time_seconds": 300, "relax_teacher_load_limits": false, "require_optimal": true }`)
