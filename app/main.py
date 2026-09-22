import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.controllers import chat_controller
from app.models.history_model import ensure_chat_history_schema
from app.routes import chat_route
from app.services import example_service

logging.basicConfig(level=logging.INFO)
for name in ("httpx", "httpx2"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    chat_controller.load_schema()
    example_service.load_examples()

    try:
        ensure_chat_history_schema()
    except Exception as e:
        logger.warning("Chat history storage is off: %s", e)

    yield


app = FastAPI(title="Chat With Database", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_route.router)
