from pydantic import BaseModel, Field

from app.models.workflow_model import Workflow


class WorkflowSetting(BaseModel):
    workflow: Workflow


class SetWorkflowRequest(BaseModel):
    session_id: str = Field(min_length=1)
    workflow: Workflow
