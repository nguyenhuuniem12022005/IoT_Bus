import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

from app.config import Settings, get_settings
from app.core.logging import configure_logging
from app.core.security import seed_users
from app.database import create_indexes
from app.mqtt_bridge.client import MQTTBridge
from app.mqtt_bridge.handlers import MessageHandler
from app.routers import alerts, audit, auth, buses, commands, health, ws
from app.services.alert_service import AlertService
from app.services.command_service import CommandService
from app.services.state_service import StateService
from app.services.ws_manager import WSManager
from app.services.video_service import VideoService

logger = logging.getLogger(__name__)


def wire_services(application: FastAPI, db: Any, settings: Settings) -> None:
    state = application.state
    state.db, state.settings = db, settings
    state.ws = WSManager()
    state.states = StateService(db, state.ws, settings)
    state.alerts = AlertService(db, state.states)
    state.commands = CommandService(db, state.ws, settings.command_timeout_s)
    state.video = VideoService(state.commands, db, settings, state.ws)
    state.handler = MessageHandler(db, state.states, state.alerts, state.commands, state.ws, state.video)


async def background(application: FastAPI) -> None:
    state = application.state
    delay = 1
    while True:
        try:
            if not state.ready:
                await state.db.command("ping")
                await create_indexes(state.db, state.settings)
                await seed_users(state.db, state.settings, only_empty=True)
                await state.states.restore()
                state.bridge.start()
                state.ready = True
            await state.states.expire()
            await state.commands.expire()
            delay = 1
        except Exception:
            logger.warning("Storage unavailable; retrying in %ss", delay)
            delay = min(delay * 2, 30)
        await asyncio.sleep(delay)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri, serverSelectionTimeoutMS=2000,
                               connectTimeoutMS=2000, socketTimeoutMS=5000)
    wire_services(application, client[settings.mongodb_db], settings)
    application.state.bridge = MQTTBridge(settings, application.state.handler, asyncio.get_running_loop())
    application.state.commands.bridge = application.state.bridge
    application.state.ready = False
    task = asyncio.create_task(background(application))
    try:
        yield
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await application.state.video.close()
        await application.state.bridge.stop()
        await application.state.ws.close()
        client.close()


def create_app() -> FastAPI:
    application = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    settings = get_settings()
    application.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins.split(","),
        allow_credentials=False, allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type"])

    @application.exception_handler(PyMongoError)
    async def storage_error(request: Request, exc: PyMongoError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": "Cơ sở dữ liệu tạm mất kết nối. Vui lòng thử lại."})

    for module in (auth, buses, alerts, commands, audit, health, ws):
        application.include_router(module.router)
    application.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
    return application


app = create_app()
