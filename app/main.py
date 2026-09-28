import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.models.connection_model import ensure_connections_schema, init_default_connection
from app.models.history_model import ensure_chat_history_schema
from app.routes import chat_route, connection_route
from app.services import example_service

logging.basicConfig(level=logging.INFO)
for name in ("httpx", "httpx2"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _ensure_schema(ensure, label: str) -> None:
    try:
        ensure()
    except Exception as e:
        logger.warning("%s storage is off: %s", label, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_default_connection()
    example_service.load_examples()

    _ensure_schema(ensure_chat_history_schema, "Chat history")
    _ensure_schema(ensure_connections_schema, "Saved connections")

    yield


app = FastAPI(title="Chat With Database", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_route.router)
app.include_router(connection_route.router)
