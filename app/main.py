import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.controllers import chat_controller
from app.routes import chat_route
from app.services import example_service

logging.basicConfig(level=logging.INFO)
for name in ("httpx", "httpx2"):
    logging.getLogger(name).setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    chat_controller.load_schema()
    example_service.load_examples()
    yield


app = FastAPI(title="Chat With Database", lifespan=lifespan)

app.include_router(chat_route.router)
