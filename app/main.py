import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.models.audit_model import ensure_audit_schema
from app.models.connection_model import ensure_connections_schema, init_default_connection
from app.models.history_model import ensure_chat_history_schema
from app.models.user_model import ensure_users_schema, seed_admin
from app.routes import admin_route, auth_route, chat_route, connection_route, conversation_route
from app.config import settings
from app.services import example_service
from app.services.auth_service import hash_password, is_valid_email, normalize_email

logging.basicConfig(level=logging.INFO)
for name in ("httpx", "httpx2"):
    logging.getLogger(name).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)


def _ensure_schema(ensure, label: str) -> None:
    try:
        ensure()
    except Exception as e:
        logger.warning("%s storage is off: %s", label, e)


def _seed_admin() -> None:
    if not (settings.admin_email and settings.admin_password):
        logger.warning("ADMIN_EMAIL / ADMIN_PASSWORD not set: no admin account is seeded.")
        return

    email = normalize_email(settings.admin_email)

    if not is_valid_email(email):
        raise ValueError("ADMIN_EMAIL is not a valid email address")

    seed_admin(email, hash_password(settings.admin_password))


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_default_connection()
    example_service.load_examples()

    _ensure_schema(ensure_users_schema, "Accounts")
    _ensure_schema(_seed_admin, "Admin seed")
    _ensure_schema(ensure_audit_schema, "Change log")
    _ensure_schema(ensure_chat_history_schema, "Chat history")
    _ensure_schema(ensure_connections_schema, "Saved connections")

    yield


app = FastAPI(title="Chat With Database", lifespan=lifespan)

_ALLOWED_ORIGINS = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]


@app.middleware("http")
async def reject_cross_site_writes(request: Request, call_next):
    """Cookie sessions make state-changing requests forgeable from another
    site. Browsers always send Origin on those, so refuse any that is not ours.
    Requests without an Origin (curl, server-to-server) carry no browser
    cookies to abuse and pass."""

    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        if origin is not None and origin not in _ALLOWED_ORIGINS:
            return JSONResponse({"detail": "Cross-site request blocked."}, status_code=403)

    return await call_next(request)


app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(admin_route.router)
app.include_router(auth_route.router)
app.include_router(chat_route.router)
app.include_router(connection_route.router)
app.include_router(conversation_route.router)
