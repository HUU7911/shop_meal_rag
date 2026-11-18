from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user, require_login
from app.schemas.feedback_schema import FeedbackRequest, FeedbackResponse

router = APIRouter()

CurrentUserDep = Annotated[CurrentUser, Depends(get_current_user)]


@router.post(
    "/feedback",
    response_model=FeedbackResponse,
    response_model_by_alias=True,
)
async def submit_feedback(
    body: FeedbackRequest,
    user: CurrentUserDep,
) -> FeedbackResponse:
    """Gửi feedback cho câu trả lời của chatbot."""
    require_login(user)
    # TODO(Member 01): FeedbackService.submit(user.user_id, body).
    # Service phải xác minh message thuộc conversation của user.
    raise NotImplementedError
