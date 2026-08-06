from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import is_cancelled_exception

from histograph.workflows.models import ExecutionSummary, PlanResult, RunWorkflowInput

_ACTIVITY_TIMEOUT = timedelta(minutes=10)
_RUN_TIMEOUT = timedelta(hours=2)
_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2,
    maximum_interval=timedelta(minutes=1),
    maximum_attempts=5,
    non_retryable_error_types=[
        "AuthenticationError",
        "AuthorizationError",
        "ConfigurationError",
        "SemanticFailure",
    ],
)


@workflow.defn(name="histograph.run.v1")
class RunWorkflow:
    @workflow.run
    async def run(self, request: RunWorkflowInput) -> None:
        try:
            plan = await workflow.execute_activity(
                "plan_run",
                request,
                result_type=PlanResult,
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
            if plan.action_required:
                return
            summary = await workflow.execute_activity(
                "execute_selected_tests",
                request,
                result_type=ExecutionSummary,
                start_to_close_timeout=_RUN_TIMEOUT,
                heartbeat_timeout=timedelta(minutes=2),
                retry_policy=_RETRY_POLICY,
            )
            await workflow.execute_activity(
                "report_run",
                args=[request, summary],
                start_to_close_timeout=_ACTIVITY_TIMEOUT,
                retry_policy=_RETRY_POLICY,
            )
        except BaseException as error:
            if is_cancelled_exception(error):
                await workflow.execute_activity(
                    "cancel_run",
                    request,
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
                raise
            if isinstance(error, Exception):
                await workflow.execute_activity(
                    "fail_run",
                    args=[request, type(error).__name__, str(error)[:4000]],
                    start_to_close_timeout=timedelta(minutes=2),
                    retry_policy=RetryPolicy(maximum_attempts=3),
                )
            raise
