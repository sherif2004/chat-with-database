from fastapi import APIRouter, HTTPException

from app.controllers import chat_controller
from app.views.chat_view import ChatRequest, ChatResponse

router = APIRouter()


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest):

    try:
        return chat_controller.chat_with_database(request.question)

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"SQL execution error: {e}")
