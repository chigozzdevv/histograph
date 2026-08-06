from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from temporalio.client import (
    Client,
    Schedule,
    ScheduleActionStartWorkflow,
    ScheduleAlreadyRunningError,
    ScheduleOverlapPolicy,
    SchedulePolicy,
    ScheduleSpec,
    ScheduleState,
    ScheduleUpdate,
)
from temporalio.common import WorkflowIDConflictPolicy

from histograph.api.config import Settings
from histograph.workflows import (
    RunWorkflow,
    RunWorkflowInput,
    ScheduledRunWorkflow,
    ScheduledRunWorkflowInput,
)


class Orchestrator(Protocol):
    async def start_run(self, run_id: str) -> str: ...

    async def cancel_run(self, workflow_id: str) -> None: ...

    async def create_schedule(
        self,
        schedule_id: str,
        cron_expression: str,
        timezone: str,
        overlap_policy: str,
    ) -> None: ...

    async def delete_schedule(self, schedule_id: str) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class TemporalOrchestrator:
    client: Client
    task_queue: str

    @classmethod
    async def connect(cls, settings: Settings) -> "TemporalOrchestrator":
        client = await Client.connect(
            settings.temporal_address,
            namespace=settings.temporal_namespace,
        )
        return cls(client=client, task_queue=settings.temporal_task_queue)

    async def start_run(self, run_id: str) -> str:
        workflow_id = f"histograph/run/{run_id}"
        await self.client.start_workflow(
            RunWorkflow.run,
            RunWorkflowInput(run_id=run_id),
            id=workflow_id,
            task_queue=self.task_queue,
            id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
            execution_timeout=timedelta(hours=3),
        )
        return workflow_id

    async def cancel_run(self, workflow_id: str) -> None:
        await self.client.get_workflow_handle(workflow_id).cancel(
            reason="Histograph run cancellation requested"
        )

    async def create_schedule(
        self,
        schedule_id: str,
        cron_expression: str,
        timezone: str,
        overlap_policy: str,
    ) -> None:
        policy = {
            "skip": ScheduleOverlapPolicy.SKIP,
            "queue": ScheduleOverlapPolicy.BUFFER_ALL,
            "replace": ScheduleOverlapPolicy.CANCEL_OTHER,
        }[overlap_policy]
        schedule = Schedule(
            action=ScheduleActionStartWorkflow(
                ScheduledRunWorkflow.run,
                ScheduledRunWorkflowInput(schedule_id=schedule_id),
                id=f"histograph/schedule/{schedule_id}",
                task_queue=self.task_queue,
                execution_timeout=timedelta(hours=3),
            ),
            spec=ScheduleSpec(cron_expressions=[cron_expression], time_zone_name=timezone),
            policy=SchedulePolicy(overlap=policy),
            state=ScheduleState(note="Histograph protected-question schedule"),
        )
        try:
            await self.client.create_schedule(schedule_id, schedule)
        except ScheduleAlreadyRunningError:
            handle = self.client.get_schedule_handle(schedule_id)
            await handle.update(lambda _: ScheduleUpdate(schedule=schedule))

    async def delete_schedule(self, schedule_id: str) -> None:
        await self.client.get_schedule_handle(schedule_id).delete()

    async def close(self) -> None:
        await self.client.close()
