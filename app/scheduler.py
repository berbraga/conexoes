from __future__ import annotations

import asyncio
import logging
import threading
from typing import Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.config import AppConfig, WEEKDAY_LABELS, Weekday

logger = logging.getLogger(__name__)


class JobScheduler:
    def __init__(self, run_callback: Callable[[], None]) -> None:
        self._scheduler = BackgroundScheduler(timezone="America/Sao_Paulo")
        self._run_callback = run_callback
        self._job_id = "linkedin_connect_job"
        self._lock = threading.Lock()

    def start(self) -> None:
        if not self._scheduler.running:
            self._scheduler.start()
            logger.info("Scheduler iniciado.")

    def shutdown(self) -> None:
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("Scheduler encerrado.")

    def refresh(self, config: AppConfig) -> None:
        with self._lock:
            if self._scheduler.get_job(self._job_id):
                self._scheduler.remove_job(self._job_id)

            if not config.scheduler_enabled or not config.weekdays:
                logger.info("Agendamento desabilitado.")
                return

            hour, minute = map(int, config.run_time.split(":"))
            day_of_week = ",".join(str(day) for day in config.weekdays)

            self._scheduler.add_job(
                self._run_callback,
                trigger=CronTrigger(
                    day_of_week=day_of_week,
                    hour=hour,
                    minute=minute,
                    timezone="America/Sao_Paulo",
                ),
                id=self._job_id,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

            days_label = ", ".join(WEEKDAY_LABELS[Weekday(day)] for day in config.weekdays)
            logger.info("Job agendado para %s às %s.", days_label, config.run_time)

    def next_run_time(self) -> str | None:
        job = self._scheduler.get_job(self._job_id)
        if job and job.next_run_time:
            return job.next_run_time.strftime("%d/%m/%Y %H:%M")
        return None


class WorkerManager:
    def __init__(self) -> None:
        self._stop_event = threading.Event()
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running

    def request_stop(self) -> None:
        self._stop_event.set()

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def reset_stop(self) -> None:
        self._stop_event.clear()

    async def execute(self, worker_factory: Callable) -> None:
        with self._lock:
            if self._running:
                raise RuntimeError("Já existe uma execução em andamento.")
            self._running = True
            self.reset_stop()

        try:
            worker = worker_factory(stop_requested=self.should_stop)
            await worker.run()
        finally:
            with self._lock:
                self._running = False
                self.reset_stop()

    def execute_in_background(self, loop: asyncio.AbstractEventLoop, worker_factory: Callable) -> None:
        asyncio.run_coroutine_threadsafe(self.execute(worker_factory), loop)
