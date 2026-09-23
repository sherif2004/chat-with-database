from fastapi import APIRouter

from app.models.workflow_model import get_workflow, set_workflow
from app.views.settings_view import SetWorkflowRequest, WorkflowSetting

router = APIRouter()


@router.get("/settings/workflow", response_model=WorkflowSetting)
def read_workflow(session_id: str):
    return WorkflowSetting(workflow=get_workflow(session_id))


@router.put("/settings/workflow", response_model=WorkflowSetting)
def update_workflow(request: SetWorkflowRequest):
    set_workflow(request.session_id, request.workflow)
    return WorkflowSetting(workflow=request.workflow)
