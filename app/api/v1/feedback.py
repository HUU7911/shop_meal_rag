from fastapi import APIRouter, Depends

from app.core.dependencies import CurrentUserDep, FeedbackServiceDep, enforce_rate_limit
from app.core.security import require_login
from app.schemas.feedback_schema import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
    dependencies=[Depends(enforce_rate_limit)],
)
async def submit_feedback(
    body: FeedbackRequest, user: CurrentUserDep, service: FeedbackServiceDep
) -> FeedbackResponse:
    """Gửi feedback cho câu trả lời của chatbot (service xác minh message thuộc conversation của user)."""
    require_login(user)
    feedback_id = await service.submit(user.user_id, body)
    return FeedbackResponse(feedback_id=feedback_id)
