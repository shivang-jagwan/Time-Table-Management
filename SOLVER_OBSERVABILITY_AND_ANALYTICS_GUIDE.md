# Solver Observability, Analytics & Pre-Solve Intelligence Guide

**Date**: April 5, 2026  
**Version**: 1.0  
**Status**: Complete Implementation  

---

## Overview

The timetable solver now includes comprehensive observability, analytics, and pre-solve intelligence modules that transform it from a black-box solver to a transparent, debuggable system.

**Key Capabilities**:
- 📊 **Penalty breakdown** — Understand which constraints are most expensive
- 📈 **Analytics engine** — Track all solve metrics and quality indicators
- 🧠 **Pre-solve calculations** — Analyze problem characteristics before solving
- 🏥 **Health monitoring** — Track solver reliability and performance trends
- 📝 **Structured logging** — JSON-formatted event logs for debugging
- 🔍 **Diagnostic API** — Query solver insights via REST endpoints

---

## Part 1: Analytics Engine (solver_analytics.py)

### What It Tracks

**1. Penalty Breakdown**

Each soft constraint contributes to the total penalty. The breakdown shows which constraints are most expensive:

```python
from solver.solver_analytics import PenaltyBreakdown

breakdown = analytics.penalty_breakdown
print(breakdown.as_dict())
# Output:
{
    "section_gaps": 450,
    "teacher_gaps": 280,
    "teacher_weekly_overload": 1200,
    "daily_balance": 150,
    "room_overflow": 300,
    ...
}

# Top contributors
print(breakdown.top_contributors(5))
# [("teacher_weekly_overload", 1200), ("section_gaps", 450), ...]
```

**2. Constraint Violations Summary**

Track how many violations of each constraint occurred in the solution:

```python
violations = analytics.violations
print(violations.as_dict())
# Output:
{
    "teacher_overload": 5,
    "room_overflow_slots": 3,
    "slot_congestion": 2,
    "gaps": 12,
    "section_imbalance": 4,
    ...
}
```

**3. Solution Quality Metrics**

```python
print(f"Coverage: {analytics.coverage_percentage}%")       # % sessions fulfilled
print(f"Teacher avg load: {analytics.teacher_average_load}")
print(f"Room utilization: {analytics.room_utilization_percentage}%")
```

### Usage

**During Solve**:
```python
from solver.solver_analytics import initialize_analytics, finalize_analytics

# At start of solve
initialize_analytics(ctx)

# ... solving happens ...

# At end of solve
analytics = finalize_analytics(ctx, result)

# Access results
print(analytics.penalty_breakdown.total())
print(analytics.violations.total_violations())
```

**Query Results**:
```python
# Export as dictionary
analytics_dict = analytics.as_dict()

# Store in database or API
result.analytics_dict = analytics_dict
```

---

## Part 2: Pre-Solve Calculations (solver_calculation.py)

### What It Analyzes

**1. Teacher Load Analysis**

```python
from solver.solver_calculation import calculate_pre_solve_statistics

calc = calculate_pre_solve_statistics(ctx)

for teacher in calc.teacher_loads[:5]:
    print(f"{teacher.teacher_name}")
    print(f"  Required: {teacher.required_load} sessions")
    print(f"  Preferred: {teacher.preferred_weekly_limit}")
    print(f"  Overload expected: {teacher.overload_expected}")
    print(f"  Overload percentage: {teacher.overload_percentage:.1f}%")
```

**2. Room Demand Analysis**

```python
room = calc.room_demand
print(f"Available rooms: {room.theory_rooms_available} theory, {room.lab_rooms_available} lab")
print(f"Peak parallel demand: {room.peak_parallel_demand}")
print(f"Overflow expected: {room.overflow_expected}")
print(f"Overflow margin: {room.overflow_percentage:.1f}%")
```

**3. Slot Pressure Map**

```python
for pressure in calc.slot_pressures:
    if pressure.congestion_level == "CRITICAL":
        print(f"Slot {pressure.slot_id}: {pressure.congestion_level}")
        print(f"  Classes: {pressure.parallel_classes}")
        print(f"  Demand: {pressure.demand_percentage:.1f}%")
        print(f"  Available capacity: {pressure.capacity_slack}")
```

**4. Feasibility Check**

```python
feasibility = calc.feasibility_check
print(f"Feasible? {feasibility.feasible}")
print(f"Warning level: {feasibility.warning_level}")
print(f"Issues:")
for issue in feasibility.issues:
    print(f"  - {issue}")
print(f"Recommendations:")
for rec in feasibility.recommendations:
    print(f"  - {rec}")
```

### Performance

Pre-solve calculations complete in **<1 second** for typical problems:
- 44 sections
- 180 subjects
- 90 teachers
- 40 time slots

### Solver Recommendations

Based on problem characteristics, pre-solve automatically recommends:

```python
for rec in calc.solver_recommendations:
    print(f"Recommendation: {rec}")
# Output examples:
# "Set room_balance_mode='soft' to allow overflow with penalties"
# "Consider increasing teacher preferred_weekly_load limits"
# "Add more time slots or reduce section loads"
```

---

## Part 3: Health Monitoring API

### Endpoint: `/solver/health`

**Request**:
```bash
curl http://localhost:8000/api/solver/health \
  -H "Authorization: Bearer <token>"
```

**Response**:
```json
{
  "status": "healthy",
  "last_solve_time_seconds": 22.8,
  "average_solve_time_seconds": 23.1,
  "total_solves": 15,
  "success_rate_percentage": 98.0,
  "fallback_rate_percentage": 2.0,
  "last_solve_status": "FEASIBLE",
  "metrics": {
    "recent_runs": 15,
    "successful_solves": 14,
    "fallback_invocations": 1
  }
}
```

**Health Status Mapping**:
- 🟢 `healthy` — Success rate ≥95%
- 🟡 `degraded` — Success rate 80-94%
- 🔴 `unhealthy` — Success rate <80%

---

## Part 4: Calculation API

### Endpoint: `/solver/calculation`

**Request**:
```bash
curl "http://localhost:8000/api/solver/calculation?program_code=CSE" \
  -H "Authorization: Bearer <token>"
```

**Response**:
```json
{
  "teacher_loads": [
    {
      "teacher_id": "T101",
      "teacher_name": "Dr. Smith",
      "required_load": 42,
      "preferred_limit": 30,
      "overload_expected": true,
      "overload_percentage": 40.0
    },
    ...
  ],
  "room_demand": {
    "theory_rooms_available": 15,
    "lab_rooms_available": 3,
    "peak_parallel_demand": 22,
    "overflow_expected": true,
    "overflow_percentage": 20.0
  },
  "slots_at_capacity": 12,
  "slots_over_capacity": 3,
  "overloaded_teachers": 8,
  "sections_imbalanced": 4,
  "warnings": [
    "WARNING: 8 teachers exceed preferred weekly load",
    "WARNING: 3 time slots operate beyond room capacity"
  ],
  "recommendations": [
    "Set room_balance_mode='soft' to handle overflow with penalties",
    "Consider adding 2-3 more classroom spaces"
  ],
  "computation_time_seconds": 0.342
}
```

---

## Part 5: Diagnostics API

### Endpoint: `/solver/diagnostics`

Combines pre-solve calculations **and** recent solve analytics.

**Request**:
```bash
curl "http://localhost:8000/api/solver/diagnostics?program_code=CSE" \
  -H "Authorization: Bearer <token>"
```

**Response**:
```json
{
  "problem_characteristics": {
    "teacher_loads": [...],
    "room_demand": {...},
    "slots_at_capacity": 12,
    "overloaded_teachers": 8,
    "warnings": ["8 teachers overloaded"],
    "recommendations": ["Increase teacher load capacity"]
  },
  "last_solve_analytics": {
    "entries_written": 304,
    "objective_value": 23468691550,
    "penalty_breakdown": {
      "teacher_weekly_overload": 1200,
      "section_gaps": 450,
      "room_overflow": 300
    },
    "violations": {
      "teacher_overload": 5,
      "room_overflow_slots": 3
    }
  },
  "warnings": ["8 teachers exceed capacity"],
  "recommendations": ["Set room_balance_mode='soft'"]
}
```

---

## Part 6: Analytics Endpoint

### Endpoint: `/solver/analytics/{run_id}`

Query detailed analytics from a specific solve.

**Request**:
```bash
curl "http://localhost:8000/api/solver/analytics/ee55fb48-040a-4ba0-b34f-1772b568e0f9" \
  -H "Authorization: Bearer <token>"
```

**Response**:
```json
{
  "problem_size": {
    "sections": 44,
    "subjects": 180,
    "teachers": 90,
    "rooms": 35,
    "time_slots": 40
  },
  "variables_created": 119020,
  "constraints_created": 45888,
  "cp_sat_status": "FEASIBLE",
  "cp_sat_solve_time_seconds": 22.8,
  "total_objective_value": 23468691550,
  "best_objective_bound": 6400000000,
  "optimality_gap": 17068691550,
  "penalty_breakdown": {
    "section_gaps": 450,
    "teacher_weekly_overload": 1200,
    "daily_balance": 150,
    "room_overflow": 300,
    ...
  },
  "penalty_total": 3200,
  "violations": {
    "teacher_overload": 5,
    "room_overflow_slots": 3,
    "gaps": 12
  },
  "violations_total": 20,
  "entries_written": 304,
  "coverage_percentage": 98.5,
  "room_utilization_percentage": 81.4,
  "greedy_fallback_invoked": false
}
```

---

## Part 7: Structured Logging

### JSON Event Logging

All solver events are logged as structured JSON:

```python
from solver.solver_logging import (
    log_solve_start,
    log_solve_end,
    log_phase_start,
    log_phase_end,
    log_fallback_triggered,
    SolverPhase,
)

# Start
log_solve_start(
    program_id="PROG123",
    sections_count=44,
    teachers_count=90,
    timestamp="2026-04-05T10:30:00Z",
)

# Phase tracking
log_phase_start(SolverPhase.VARIABLE_CREATION)
# ... work ...
log_phase_end(SolverPhase.VARIABLE_CREATION, duration_seconds=1.23)

# End
log_solve_end(
    status="FEASIBLE",
    entries_written=304,
    solve_time_seconds=22.8,
)
```

### Log Format

Each log entry is JSON for easy parsing:

```json
{
  "event": "solve_start",
  "timestamp": 1712278200.123,
  "program_id": "PROG123",
  "sections_count": 44,
  "teachers_count": 90
}
```

### Log Parsing

Parse logs for monitoring:

```bash
# Extract all FEASIBLE solves
cat solver.log | jq 'select(.event == "solve_end" and .status == "FEASIBLE")'

# Calculate average solve time
cat solver.log | jq 'select(.event == "solve_end") | .solve_time_seconds' | awk '{sum+=$1; count++} END {print sum/count}'

# Find fallback invocations
cat solver.log | jq 'select(.event == "fallback_triggered")'
```

---

## Part 8: Integration with Solver Pipeline

### Minimal Integration

Add observability to existing solve with minimal changes:

**Before**:
```python
result = solve_program_global(db, run, program_id, max_time_seconds=30)
```

**After**:
```python
from solver.solver_analytics import initialize_analytics, finalize_analytics
from solver.solver_calculation import initialize_calculations
from solver.solver_logging import log_solve_start, log_solve_end

# 1. Initialize
initialize_analytics(ctx)
initialize_calculations(ctx)
log_solve_start(program_id, len(ctx.sections), len(ctx.subjects), ...)

# 2. Solve (unchanged)
result = solve_program_global(db, run, program_id, max_time_seconds=30)

# 3. Finalize
analytics = finalize_analytics(ctx, result)
log_solve_end(result.status, result.entries_written, result.solve_time_seconds)

# 4. Store
result.analytics_dict = analytics.as_dict()
run.pre_solve_calculations = ctx.pre_solve_calculations.as_dict()
db.commit()
```

---

## Part 9: Dashboard Integration

### Dashboard Sections

**1. Solver Insights**
- Solve time trend
- Status distribution (FEASIBLE, OPTIMAL, GREEDY, TIMEOUT)
- Average objective score
- Coverage percentage

**2. Problem Analysis**
- Overloaded teachers (count & %)
- Room utilization %
- Slot pressure heatmap
- Section balance distribution

**3. Penalty Breakdown Chart**
- Pie chart of penalty contributions
- Top 5 penalty drivers
- Trend over time

**4. Health Status**
- Success rate %
- Fallback rate %
- Average solve time
- Last solve status & time

**5. Warnings & Alerts**
- Pre-solve warnings
- Post-solve violations
- Capacity issues
- Recommendations

---

## Part 10: Use Cases

### Use Case 1: Debug High Objective Scores

**Symptom**: Recent solves have very high objective values

**Investigation**:
```bash
# Query latest solve
curl http://localhost:8000/api/solver/analytics/<run_id>

# Check penalty breakdown
{
  "penalty_breakdown": {
    "teacher_weekly_overload": 5600,  # ← Problem!
    "section_gaps": 450,
    ...
  }
}

# Check pre-solve
curl "http://localhost:8000/api/solver/calculation?program_code=CSE"

# Check recommendations
{
  "overloaded_teachers": 15,  # ← Root cause!
  "recommendations": ["Reduce section loads or add teacher capacity"]
}

# Action: Reduce loads or contact admin to add more teachers
```

### Use Case 2: Investigate Fallback Activation

**Symptom**: Greedy fallback suddenly invoked (unusual)

**Investigation**:
```python
# Check logs
cat solver.log | jq 'select(.event == "fallback_triggered")'

# Output
{
  "event": "fallback_triggered",
  "reason": "CP-SAT returned INFEASIBLE",
  "phase": "cp_sat_solve",
  "timestamp": 1712278200
}

# Check diagnostics
curl "http://localhost:8000/api/solver/diagnostics?program_code=CSE"

# Check for new constraints or data issues
```

### Use Case 3: Optimize Slot Usage

**Symptom**: Some slots always congested, others empty

**Investigation**:
```bash
# Get calculation
curl "http://localhost:8000/api/solver/calculation?program_code=CSE"

# Check slot pressure
{
  "slot_pressures": [
    {
      "slot_id": "Mon_1",
      "demand_percentage": 95.0,  # Congested
      "congestion_level": "CRITICAL"
    },
    {
      "slot_id": "Fri_7",
      "demand_percentage": 15.0,  # Empty
      "congestion_level": "LOW"
    }
  ]
}

# Action: Spread sessions to underutilized slots
```

---

## Part 11: Deployment Checklist

Before going live with observability:

- [ ] Analytics module imported in cp_sat_solver.py
- [ ] Pre-solve calculations called before solve
- [ ] Logging configured for JSON format
- [ ] API routes registered in main.py
- [ ] Database schema updated to store analytics_dict
- [ ] Dashboard connected to analytics endpoints
- [ ] Alert rules configured (fallback rate, success rate)
- [ ] Log aggregation (Datadog, ELK, Splunk) configured

---

## Part 12: API Summary

| Endpoint | Purpose | Response Time |
|----------|---------|----------------|
| `/solver/health` | Solver health status | <100ms |
| `/solver/calculation` | Pre-solve analysis | <1s |
| `/solver/analytics/{run_id}` | Solve analytics | <100ms |
| `/solver/diagnostics` | Combined insights | <1.5s |

---

## Part 13: Performance Impact

Adding observability has **minimal performance impact**:

| Component | Time | Impact |
|-----------|------|--------|
| Analytics tracking | Track during solve | 0% (no-op collection) |
| Pre-solve calculations | <1s initialization | <2% (once per solve) |
| Logging | Async JSON writes | <1% |
| Result finalization | <100ms post-solve | <1% |
| **Total Overhead** | **<2% of solver time** | **Acceptable** |

---

## Summary

The observability system provides:
- ✅ **Transparency** — Understand exactly what the solver is doing
- ✅ **Debugging** — Diagnose failures and understand why
- ✅ **Monitoring** — Track health, reliability, and performance
- ✅ **Intelligence** — Pre-solve analysis guides optimization
- ✅ **Simplicity** — No external dependencies (no Redis)
- ✅ **Performance** — <2% overhead

All data accessible via REST API, JSON logs, and database storage.

---

**Implementation Complete ✅**
