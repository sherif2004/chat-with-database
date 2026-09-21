from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.controllers import chat_controller
from app.routes import chat_route


@asynccontextmanager
async def lifespan(app: FastAPI):
    chat_controller.load_schema()
    yield


app = FastAPI(title="Chat With Database", lifespan=lifespan)

app.include_router(chat_route.router)
