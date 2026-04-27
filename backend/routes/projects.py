"""Project configuration endpoints used by onboarding/new-project flows."""

from __future__ import annotations

from fastapi import APIRouter, Query

from routes.schemas import ProjectConfigOption, ProjectConfigResponse
from service.project_config import get_project_config

router = APIRouter(tags=["projects"])


@router.get("/config")
async def get_projects_config(
    industry: str = Query(default=""),
    business_model: str = Query(default=""),
) -> dict:
    payload = get_project_config(industry=industry, business_model=business_model)
    response = ProjectConfigResponse(
        industry_options=[ProjectConfigOption(value=item.value, label=item.label) for item in payload["industry_options"]],
        business_model_options=[
            ProjectConfigOption(value=item.value, label=item.label) for item in payload["business_model_options"]
        ],
        north_star_metric_options=[
            ProjectConfigOption(value=item.value, label=item.label) for item in payload["north_star_metric_options"]
        ],
        growth_stage_milestone_options=[
            ProjectConfigOption(value=item.value, label=item.label) for item in payload["growth_stage_milestone_options"]
        ],
    )
    return response.model_dump(mode="json")
