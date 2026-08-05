from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

from histograph_workflows.models import (
    CreateScheduledRunInput,
    RunWorkflowInput,
    ScheduledRunWorkflowInput,
)
from histograph_workflows.run_workflow import RunWorkflow


@workflow.defn(name="histograph.scheduled-run.v1")
class ScheduledRunWorkflow:
    @workflow.run
    async def run(self, request: ScheduledRunWorkflowInput) -> None:
        run_id = await workflow.execute_activity(
            "create_scheduled_run",
            CreateScheduledRunInput(
                schedule_id=request.schedule_id,
                workflow_run_id=workflow.info().run_id,
            ),
            result_type=str,
            start_to_close_timeout=timedelta(minutes=2),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )
        await workflow.execute_child_workflow(
            RunWorkflow.run,
            RunWorkflowInput(run_id=run_id),
            id=f"histograph/run/{run_id}",
            task_queue=workflow.info().task_queue,
            execution_timeout=timedelta(hours=3),
        )
