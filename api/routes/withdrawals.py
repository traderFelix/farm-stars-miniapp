from fastapi import APIRouter, Depends, HTTPException, status

from api.dependencies.auth import get_current_user_id
from api.schemas.withdrawals import (
    WithdrawalEligibilityResponse,
    WithdrawalCreateRequest,
    WithdrawalCreateResponse,
    WithdrawalListResponse,
)
from api.services.withdrawals import (
    get_withdrawal_eligibility_for_user,
    create_withdrawal_for_user,
    get_my_withdrawals_for_user,
)

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])


@router.get(
    "/eligibility",
    response_model=WithdrawalEligibilityResponse,
)
async def get_withdrawal_eligibility(
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalEligibilityResponse:
    return await get_withdrawal_eligibility_for_user(user_id)


@router.post(
    "",
    response_model=WithdrawalCreateResponse,
)
async def create_withdrawal(
        payload: WithdrawalCreateRequest,
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalCreateResponse:
    try:
        return await create_withdrawal_for_user(user_id, payload)
    except ValueError as e:
        # бизнес-ошибки (валидация, ограничения)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        # неожиданные ошибки
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create withdrawal: {e}",
        )


@router.get(
    "/my",
    response_model=WithdrawalListResponse,
)
async def get_my_withdrawals(
        limit: int = 20,
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalListResponse:
    try:
        return await get_my_withdrawals_for_user(user_id=user_id, limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get my withdrawals: {e}",
        )
