from dataclasses import dataclass


@dataclass(frozen=True)
class RunWorkflowInput:
    run_id: str


@dataclass(frozen=True)
class ScheduledRunWorkflowInput:
    schedule_id: str


@dataclass(frozen=True)
class CreateScheduledRunInput:
    schedule_id: str
    workflow_run_id: str


@dataclass(frozen=True)
class PlanResult:
    action_required: bool
    selected_test_count: int


@dataclass(frozen=True)
class ExecutionSummary:
    passed: int
    failed: int
    warnings: int
    errors: int
