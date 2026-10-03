"""Reliable, permission-aware execution for code-first Agent Workers."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from typing import Any

from .spec import ApprovalPolicy, Run, RunStatus, Worker
from .store import SQLiteStore


class ActivLayerError(Exception):
    """Base error for the public runtime."""


class PermissionDenied(ActivLayerError):
    pass


class WorkerNotRegistered(ActivLayerError):
    pass


class Runtime:
    """Register workers, start durable runs, and advance them safely."""

    def __init__(self, database: str = "activlayer.db") -> None:
        self.store = SQLiteStore(database)
        self._workers: dict[tuple[str, str], Worker] = {}

    def register(self, worker: Worker) -> Worker:
        key = (worker.name, worker.version)
        if key in self._workers:
            raise ValueError(f"Worker already registered: {worker.name}@{worker.version}")
        self._workers[key] = worker
        return worker

    def start(
        self,
        worker: Worker,
        input: dict[str, Any],
        *,
        permissions: set[str] | frozenset[str] = frozenset(),
        run_id: str | None = None,
        execute: bool = True,
    ) -> Run:
        if (worker.name, worker.version) not in self._workers:
            self.register(worker)
        run = Run(
            id=run_id or uuid.uuid4().hex,
            worker=worker.name,
            worker_version=worker.version,
            status=RunStatus.PENDING,
            current_step=0,
            state={"input": input, "outputs": {}, "attempts": {}},
            permissions=frozenset(permissions),
        )
        self.store.create_run(run)
        self.store.append_event(
            run.id,
            "run.created",
            {"worker": worker.name, "version": worker.version},
        )
        return self.execute(run.id) if execute else run

    def execute(self, run_id: str) -> Run:
        run = self.store.get_run(run_id)
        worker = self._workers.get((run.worker, run.worker_version))
        if worker is None:
            raise WorkerNotRegistered(f"Register {run.worker}@{run.worker_version} before resuming")
        if run.status == RunStatus.SUCCEEDED:
            return run

        run = replace(run, status=RunStatus.RUNNING, error=None)
        self.store.save_run(run)

        while run.current_step < len(worker.steps):
            step = worker.steps[run.current_step]
            permission = step.tool.permission
            if permission and permission not in run.permissions:
                message = f"Step '{step.name}' requires permission '{permission}'"
                run = replace(run, status=RunStatus.FAILED, error=message)
                self.store.save_run(run)
                self.store.append_event(
                    run.id,
                    "permission.denied",
                    {"step": step.name, "permission": permission},
                )
                raise PermissionDenied(message)

            if step.tool.approval == ApprovalPolicy.REQUIRED and not self.store.is_approved(
                run.id, step.name
            ):
                run = replace(run, status=RunStatus.WAITING_APPROVAL)
                self.store.save_run(run)
                self.store.append_event(
                    run.id,
                    "approval.requested",
                    {"step": step.name, "tool": step.tool.name},
                )
                return run

            attempts = run.state["attempts"].get(step.name, 0)
            try:
                state_view = {
                    "input": run.state["input"],
                    "outputs": run.state["outputs"],
                }
                arguments = dict(step.arguments(state_view))
                self.store.append_event(
                    run.id,
                    "step.started",
                    {"step": step.name, "tool": step.tool.name, "attempt": attempts + 1},
                )
                output = step.tool.function(**arguments)
                run.state["outputs"][step.save_as or step.name] = output
                run.state["attempts"][step.name] = attempts + 1
                run = replace(run, current_step=run.current_step + 1)
                self.store.save_run(run)
                self.store.append_event(
                    run.id,
                    "step.succeeded",
                    {"step": step.name, "tool": step.tool.name},
                )
            except Exception as error:  # noqa: BLE001
                attempts += 1
                run.state["attempts"][step.name] = attempts
                self.store.append_event(
                    run.id,
                    "step.failed",
                    {"step": step.name, "attempt": attempts, "error": type(error).__name__},
                )
                if attempts >= step.max_attempts:
                    run = replace(run, status=RunStatus.FAILED, error=str(error))
                    self.store.save_run(run)
                    return run
                self.store.save_run(run)
                time.sleep(min(0.05 * (2 ** (attempts - 1)), 0.5))

        run = replace(run, status=RunStatus.SUCCEEDED)
        self.store.save_run(run)
        self.store.append_event(run.id, "run.succeeded", {"steps": len(worker.steps)})
        return run

    def approve(self, run_id: str, *, actor: str, reason: str = "") -> Run:
        run = self.store.get_run(run_id)
        worker = self._workers.get((run.worker, run.worker_version))
        if worker is None:
            raise WorkerNotRegistered(f"Register {run.worker}@{run.worker_version} before approval")
        if run.status != RunStatus.WAITING_APPROVAL:
            raise ActivLayerError("Run is not waiting for approval")
        step = worker.steps[run.current_step]
        self.store.approve(run.id, step.name, actor, reason)
        self.store.append_event(
            run.id,
            "approval.granted",
            {"step": step.name, "actor": actor, "reason": reason},
        )
        return self.execute(run.id)
