"""
Internal admin review routes for verification submissions.
"""

from fastapi import APIRouter, Depends

from app.core.admin_auth import require_internal_admin
from app.modules.auth.schemas import RejectVerificationRequest
from app.modules.auth.service import auth_service

router = APIRouter()


@router.post("/user-verifications/{submission_id}/approve")
async def approve_user_verification(
    submission_id: str,
    reviewer: str = Depends(require_internal_admin),
):
    result = await auth_service.approve_verification_submission(
        submission_id=submission_id,
        reviewer=reviewer,
    )
    return {"ok": True, "data": result}


@router.post("/user-verifications/{submission_id}/reject")
async def reject_user_verification(
    submission_id: str,
    payload: RejectVerificationRequest,
    reviewer: str = Depends(require_internal_admin),
):
    result = await auth_service.reject_verification_submission(
        submission_id=submission_id,
        reviewer=reviewer,
        reason=payload.reason,
    )
    return {"ok": True, "data": result}
