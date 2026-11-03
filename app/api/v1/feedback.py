from fastapi import APIRouter, Depends

from app.core.security import CurrentUser, get_current_user
from app.schemas.feedback_schema import FeedbackRequest, FeedbackResponse

router = APIRouter()


@router.post("/feedback", response_model=FeedbackResponse, response_model_by_alias=True)
async def submit_feedback(body: FeedbackRequest, user: CurrentUser = Depends(get_current_user)):
    """TODO(Member 01): FeedbackService.submit(...) – kiểm tra message thuộc conversation của user."""
    raise NotImplementedError
