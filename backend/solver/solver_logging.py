"""Structured logging for solver events — comprehensive observability.

Provides structured, JSON-friendly logging for all solver phases and events.
Enables tracking, debugging, and monitoring of solver execution.
"""

from __future__ import annotations

import json
import logging
import time
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class SolverPhase(Enum):
    """Solver execution phases."""
    
    INITIALIZATION = "initialization"
    DATA_LOAD = "data_load"
    DOMAIN_REDUCTION = "domain_reduction"
    VARIABLE_CREATION = "variable_creation"
    CONSTRAINT_ADDITION = "constraint_addition"
    OBJECTIVE_SETUP = "objective_setup"
    CP_SAT_SOLVE = "cp_sat_solve"
    RESULT_WRITING = "result_writing"
    FALLBACK = "fallback"
    COMPLETION = "completion"


class SolverEvent(Enum):
    """Solver event types."""
    
    SOLVE_START = "solve_start"
    SOLVE_END = "solve_end"
    PHASE_START = "phase_start"
    PHASE_END = "phase_end"
    FALLBACK_TRIGGERED = "fallback_triggered"
    TIMEOUT_REACHED = "timeout_reached"
    ERROR_OCCURRED = "error_occurred"
    WARNING_ISSUED = "warning_issued"
    CALCULATION_COMPLETE = "calculation_complete"


def log_structured(
    event: SolverEvent | str,
    level: int = logging.INFO,
    **context: Any,
) -> None:
    """Log a structured event with context."""
    
    log_entry = {
        "event": event.value if isinstance(event, SolverEvent) else event,
        "timestamp": time.time(),
        **context,
    }
    
    # Log as JSON for easy parsing
    logger.log(level, json.dumps(log_entry))


def log_solve_start(
    program_id: str,
    sections_count: int,
    subjects_count: int,
    teachers_count: int,
    slots_count: int,
    **extra: Any,
) -> None:
    """Log solver start."""
    
    log_structured(
        SolverEvent.SOLVE_START,
        logging.INFO,
        program_id=str(program_id),
        sections_count=sections_count,
        subjects_count=subjects_count,
        teachers_count=teachers_count,
        slots_count=slots_count,
        **extra,
    )


def log_solve_end(
    status: str,
    entries_written: int,
    solve_time_seconds: float,
    objective_value: int | None = None,
    **extra: Any,
) -> None:
    """Log solver completion."""
    
    log_structured(
        SolverEvent.SOLVE_END,
        logging.INFO,
        status=status,
        entries_written=entries_written,
        solve_time_seconds=round(solve_time_seconds, 2),
        objective_value=objective_value,
        **extra,
    )


def log_phase_start(phase: SolverPhase) -> None:
    """Log phase start."""
    
    log_structured(
        SolverEvent.PHASE_START,
        logging.DEBUG,
        phase=phase.value,
    )


def log_phase_end(phase: SolverPhase, duration_seconds: float) -> None:
    """Log phase completion."""
    
    log_structured(
        SolverEvent.PHASE_END,
        logging.DEBUG,
        phase=phase.value,
        duration_seconds=round(duration_seconds, 3),
    )


def log_fallback_triggered(reason: str, **context: Any) -> None:
    """Log greedy fallback activation."""
    
    log_structured(
        SolverEvent.FALLBACK_TRIGGERED,
        logging.WARNING,
        reason=reason,
        **context,
    )


def log_timeout_reached(elapsed_seconds: float, budget_seconds: float) -> None:
    """Log timeout."""
    
    log_structured(
        SolverEvent.TIMEOUT_REACHED,
        logging.WARNING,
        elapsed_seconds=round(elapsed_seconds, 2),
        budget_seconds=round(budget_seconds, 2),
    )


def log_error(message: str, phase: SolverPhase | None = None, **context: Any) -> None:
    """Log error."""
    
    log_structured(
        SolverEvent.ERROR_OCCURRED,
        logging.ERROR,
        message=message,
        phase=phase.value if phase else None,
        **context,
    )


def log_warning(message: str, **context: Any) -> None:
    """Log warning."""
    
    log_structured(
        SolverEvent.WARNING_ISSUED,
        logging.WARNING,
        message=message,
        **context,
    )


def log_calculation_complete(
    computation_time_seconds: float,
    overloaded_teachers: int,
    slots_at_capacity: int,
    **context: Any,
) -> None:
    """Log pre-solve calculation completion."""
    
    log_structured(
        SolverEvent.CALCULATION_COMPLETE,
        logging.INFO,
        computation_time_seconds=round(computation_time_seconds, 3),
        overloaded_teachers=overloaded_teachers,
        slots_at_capacity=slots_at_capacity,
        **context,
    )


def create_diagnostic_report(analytics: Any, calculations: Any) -> dict[str, Any]:
    """Create comprehensive diagnostic report."""
    
    return {
        "analytics": analytics.as_dict() if hasattr(analytics, "as_dict") else analytics,
        "calculations": calculations.as_dict() if hasattr(calculations, "as_dict") else calculations,
        "timestamp": time.time(),
    }
