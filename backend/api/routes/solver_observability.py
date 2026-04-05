"""Solver observability API endpoints — insights, health checks, and analytics.

Provides:
- /solver/calculation — Pre-solve analysis and problem characteristics
- /solver/health — solver health status and metrics
- /solver/analytics — Analytics from most recent solve
- /solver/diagnostics — Detailed solver diagnostics
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.deps import get_db, get_tenant_id
from core.db import SessionLocal
from models.academic_year import AcademicYear
from models.program import Program
from models.timetable_run import TimetableRun
from solver.context import SolverContext
from solver.solver_analytics import SolverAnalytics
from solver.solver_calculation import (
    PreSolveCalculations,
    calculate_pre_solve_statistics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/solver", tags=["solver-observability"])


# ────── Response Models ────────────────────────────────────────────────────


class CalculationResponse(BaseModel):
    """Pre-solve calculation data."""
    
    teacher_loads: list[dict] = []
    room_demand: dict | None = None
    slots_at_capacity: int = 0
    slots_over_capacity: int = 0
    overloaded_teachers: int = 0
    sections_imbalanced: int = 0
    warnings: list[str] = []
    recommendations: list[str] = []
    computation_time_seconds: float = 0.0


class HealthCheckResponse(BaseModel):
    """Solver health status."""
    
    status: str                           # "healthy", "degraded", "unhealthy"
    last_solve_time_seconds: float | None = None
    average_solve_time_seconds: float | None = None
    total_solves: int = 0
    fallback_rate_percentage: float = 0.0
    success_rate_percentage: float = 0.0
    last_solve_status: str | None = None
    last_solve_timestamp: str | None = None
    metrics: dict[str, Any] = {}


class AnalyticsResponse(BaseModel):
    """Complete solve analytics."""
    
    problem_size: dict[str, int] = {}
    variables_created: int = 0
    constraints_created: int = 0
    cp_sat_status: str = ""
    cp_sat_solve_time_seconds: float = 0.0
    total_objective_value: int = 0
    penalty_breakdown: dict[str, int] = {}
    penalty_total: int = 0
    violations: dict[str, int] = {}
    violations_total: int = 0
    entries_written: int = 0
    coverage_percentage: float = 0.0
    room_utilization_percentage: float = 0.0
    greedy_fallback_invoked: bool = False


class DiagnosticsResponse(BaseModel):
    """Detailed solver diagnostics."""
    
    problem_characteristics: dict[str, Any] = {}
    last_solve_analytics: dict[str, Any] = {}
    warnings: list[str] = []
    recommendations: list[str] = []


# ─────── Endpoints ────────────────────────────────────────────────────────


@router.get("/calculation", response_model=CalculationResponse)
def get_solver_calculation(
    program_code: str,
    academic_year_id: str | None = None,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> CalculationResponse:
    """
    Pre-solve calculation and problem analysis.
    
    Provides insights into:
    - Teacher load analysis
    - Room demand vs capacity
    - Slot pressure map
    - Section imbalance
    - Feasibility check
    
    Completes in <1 second. No solving involved.
    """
    try:
        # Load program
        program = db.query(Program).filter(
            Program.code == program_code,
            Program.tenant_id == tenant_id,
            Program.is_active.is_(True),
        ).first()
        
        if not program:
            raise HTTPException(status_code=404, detail=f"Program {program_code} not found")
        
        # Create minimal context for calculation
        ctx = SolverContext(
            db=db,
            run=None,  # No run needed for pre-solve
            program_id=program.id,
            academic_year_id=academic_year_id,
            tenant_id=tenant_id,
        )
        
        # Load data
        from solver.data_loader import load_all, build_pruned_slots
        load_all(ctx)
        build_pruned_slots(ctx)
        
        # Calculate
        calc = calculate_pre_solve_statistics(ctx)
        
        # Format response
        return CalculationResponse(
            teacher_loads=[
                {
                    "teacher_id": t.teacher_id,
                    "teacher_name": t.teacher_name,
                    "required_load": t.required_load,
                    "preferred_limit": t.preferred_weekly_limit,
                    "overload_expected": t.overload_expected,
                    "overload_percentage": round(t.overload_percentage, 1),
                }
                for t in calc.teacher_loads[:10]  # Top 10
            ],
            room_demand=calc.room_demand.as_dict() if calc.room_demand else None,
            slots_at_capacity=calc.slots_at_capacity,
            slots_over_capacity=calc.slots_over_capacity,
            overloaded_teachers=calc.overloaded_teachers_count,
            sections_imbalanced=calc.sections_imbalanced,
            warnings=calc.data_quality_warnings,
            recommendations=calc.solver_recommendations,
            computation_time_seconds=round(calc.computation_time_seconds, 3),
        )
    
    except Exception as e:
        logger.error(f"Pre-solve calculation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health", response_model=HealthCheckResponse)
def get_solver_health(
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> HealthCheckResponse:
    """
    Solver health status and metrics.
    
    Tracks solver reliability:
    - Last solve time and status
    - Success/fallback rates
    - Performance trends
    """
    try:
        # Query recent solves from this tenant
        recent_runs = (
            db.query(TimetableRun)
            .filter(TimetableRun.tenant_id == tenant_id)
            .order_by(TimetableRun.created_at.desc())
            .limit(20)
            .all()
        )
        
        if not recent_runs:
            return HealthCheckResponse(
                status="healthy",
                total_solves=0,
                metrics={"no_solves": True},
            )
        
        # Calculate metrics
        last_run = recent_runs[0]
        solve_times = [
            getattr(run, "solve_time_seconds", 0)
            for run in recent_runs
            if hasattr(run, "solve_time_seconds")
        ]
        
        successful = sum(1 for run in recent_runs if run.status in ("FEASIBLE", "OPTIMAL"))
        fallback_used = sum(1 for run in recent_runs if "GREEDY_FALLBACK" in (getattr(run, "warnings", []) or []))
        
        avg_solve_time = sum(solve_times) / len(solve_times) if solve_times else None
        success_rate = (successful / len(recent_runs) * 100) if recent_runs else 0.0
        fallback_rate = (fallback_used / len(recent_runs) * 100) if recent_runs else 0.0
        
        # Determine health status
        if success_rate >= 95:
            health_status = "healthy"
        elif success_rate >= 80:
            health_status = "degraded"
        else:
            health_status = "unhealthy"
        
        return HealthCheckResponse(
            status=health_status,
            last_solve_time_seconds=getattr(last_run, "solve_time_seconds", None),
            average_solve_time_seconds=avg_solve_time,
            total_solves=len(recent_runs),
            success_rate_percentage=round(success_rate, 1),
            fallback_rate_percentage=round(fallback_rate, 1),
            last_solve_status=last_run.status,
            last_solve_timestamp=last_run.created_at.isoformat() if last_run.created_at else None,
            metrics={
                "recent_runs": len(recent_runs),
                "successful_solves": successful,
                "fallback_invocations": fallback_used,
            },
        )
    
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return HealthCheckResponse(
            status="unhealthy",
            metrics={"error": str(e)},
        )


@router.get("/analytics/{run_id}", response_model=AnalyticsResponse)
def get_solve_analytics(
    run_id: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> AnalyticsResponse:
    """
    Analytics from a specific solve run.
    
    Provides detailed breakdown of:
    - Problem size and complexity
    - CP-SAT solver statistics
    - Penalty contribution by constraint type
    - Solution quality metrics
    - Fallback information
    """
    try:
        # Fetch run
        run = db.query(TimetableRun).filter(
            TimetableRun.id == run_id,
            TimetableRun.tenant_id == tenant_id,
        ).first()
        
        if not run:
            raise HTTPException(status_code=404, detail=f"Run {run_id} not found")
        
        # Extract analytics from run (stored as JSON in database)
        analytics_dict = getattr(run, "analytics_dict", {})
        
        if not analytics_dict:
            # No analytics stored; provide basic info
            analytics_dict = {
                "problem_size": {},
                "variables_created": 0,
                "cp_sat_status": run.status,
                "entries_written": getattr(run, "entries_count", 0),
            }
        
        return AnalyticsResponse(**analytics_dict)
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Analytics retrieval error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics", response_model=DiagnosticsResponse)
def get_solver_diagnostics(
    program_code: str,
    db: Session = Depends(get_db),
    tenant_id: str = Depends(get_tenant_id),
) -> DiagnosticsResponse:
    """
    Combined diagnostics: pre-solve calculations + recent solve analytics.
    
    For debugging and understanding solver behavior:
    - Problem characteristics (what's hard about this schedule?)
    - Recent solve outcomes (how did solver handle it?)
    - Warnings and recommendations
    """
    try:
        # Get pre-solve calculations
        program = db.query(Program).filter(
            Program.code == program_code,
            Program.tenant_id == tenant_id,
        ).first()
        
        if not program:
            raise HTTPException(status_code=404, detail=f"Program {program_code} not found")
        
        ctx = SolverContext(db=db, run=None, program_id=program.id, tenant_id=tenant_id)
        from solver.data_loader import load_all, build_pruned_slots
        load_all(ctx)
        build_pruned_slots(ctx)
        
        calc = calculate_pre_solve_statistics(ctx)
        
        # Get recent solve
        recent_run = (
            db.query(TimetableRun)
            .filter(TimetableRun.program_id == program.id, TimetableRun.tenant_id == tenant_id)
            .order_by(TimetableRun.created_at.desc())
            .first()
        )
        
        recent_analytics = {}
        if recent_run and hasattr(recent_run, "analytics_dict"):
            recent_analytics = getattr(recent_run, "analytics_dict", {})
        
        return DiagnosticsResponse(
            problem_characteristics=calc.as_dict(),
            last_solve_analytics=recent_analytics,
            warnings=calc.data_quality_warnings,
            recommendations=calc.solver_recommendations,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
