from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import WEEKDAY_LABELS, AppConfig, Weekday
from app.linkedin.connector import ConnectionWorker
from app.scheduler import JobScheduler, WorkerManager
from app.storage.db import StorageRepository

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

storage = StorageRepository()
worker_manager = WorkerManager()
job_scheduler: JobScheduler | None = None
event_loop: asyncio.AbstractEventLoop | None = None


def _build_worker(stop_requested):
    config = AppConfig.load()
    return ConnectionWorker(
        config=config,
        storage=storage,
        stop_requested=stop_requested,
    )


def _trigger_scheduled_run() -> None:
    if worker_manager.is_running:
        logger.warning("Execução agendada ignorada: worker já em execução.")
        return
    if event_loop is None:
        logger.error("Event loop indisponível para execução agendada.")
        return
    config = AppConfig.load()
    if not config.is_ready():
        logger.warning("Execução agendada ignorada: configuração incompleta.")
        return
    worker_manager.execute_in_background(event_loop, _build_worker)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global job_scheduler, event_loop
    event_loop = asyncio.get_running_loop()
    job_scheduler = JobScheduler(run_callback=_trigger_scheduled_run)
    job_scheduler.start()
    job_scheduler.refresh(AppConfig.load())
    yield
    job_scheduler.shutdown()


app = FastAPI(title="LinkedIn Auto Connect", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


def _build_status_context(config: AppConfig, message: str = "", error: str = "") -> dict:
    latest_run = storage.get_latest_run()
    recent_runs = storage.get_recent_runs()
    return {
        "config": config,
        "weekday_options": list(Weekday),
        "weekday_labels": WEEKDAY_LABELS,
        "message": message,
        "error": error,
        "is_running": worker_manager.is_running,
        "latest_run": latest_run,
        "recent_runs": recent_runs,
        "total_invites": storage.total_invites(),
        "invites_today": storage.count_invites_today(),
        "invites_week": storage.count_invites_this_week(),
        "next_run": job_scheduler.next_run_time() if job_scheduler else None,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    config = AppConfig.load()
    return templates.TemplateResponse(
        request,
        "index.html",
        _build_status_context(config),
    )


@app.post("/config")
async def save_config(
    request: Request,
    li_at_cookie: Annotated[str, Form()] = "",
    weekdays: Annotated[list[int], Form()] = [],
    run_time: Annotated[str, Form()] = "09:00",
    search_url: Annotated[str, Form()] = "",
    note_template: Annotated[str, Form()] = "",
    daily_limit: Annotated[int, Form()] = 15,
    weekly_limit: Annotated[int, Form()] = 100,
    delay_min_seconds: Annotated[int, Form()] = 20,
    delay_max_seconds: Annotated[int, Form()] = 60,
    scheduler_enabled: Annotated[str | None, Form()] = None,
) -> HTMLResponse:
    current = AppConfig.load()
    cookie_value = li_at_cookie.strip() or current.li_at_cookie

    try:
        config = AppConfig(
            li_at_cookie=cookie_value,
            weekdays=weekdays,
            run_time=run_time,
            search_url=search_url,
            note_template=note_template,
            daily_limit=daily_limit,
            weekly_limit=weekly_limit,
            delay_min_seconds=delay_min_seconds,
            delay_max_seconds=delay_max_seconds,
            scheduler_enabled=scheduler_enabled == "on",
        )
        config.save()
        if job_scheduler:
            job_scheduler.refresh(config)
        return templates.TemplateResponse(
            request,
            "index.html",
            _build_status_context(config, message="Configurações salvas com sucesso."),
        )
    except Exception as error:
        logger.exception("Erro ao salvar configuração")
        return templates.TemplateResponse(
            request,
            "index.html",
            _build_status_context(current, error=str(error)),
            status_code=400,
        )


@app.post("/run")
async def run_now(request: Request) -> RedirectResponse | HTMLResponse:
    config = AppConfig.load()
    if not config.is_ready():
        return templates.TemplateResponse(
            request,
            "index.html",
            _build_status_context(
                config,
                error="Preencha cookie, URL de busca e mensagem antes de executar.",
            ),
            status_code=400,
        )

    if worker_manager.is_running:
        return templates.TemplateResponse(
            request,
            "index.html",
            _build_status_context(config, error="Já existe uma execução em andamento."),
            status_code=409,
        )

    worker_manager.execute_in_background(asyncio.get_running_loop(), _build_worker)
    return RedirectResponse(url="/?started=1", status_code=303)


@app.post("/stop")
async def stop_run() -> RedirectResponse:
    worker_manager.request_stop()
    return RedirectResponse(url="/", status_code=303)


@app.get("/status")
async def status() -> dict:
    config = AppConfig.load()
    latest_run = storage.get_latest_run()
    return {
        "is_running": worker_manager.is_running,
        "scheduler_enabled": config.scheduler_enabled,
        "next_run": job_scheduler.next_run_time() if job_scheduler else None,
        "total_invites": storage.total_invites(),
        "invites_today": storage.count_invites_today(),
        "invites_week": storage.count_invites_this_week(),
        "latest_run": latest_run,
    }
