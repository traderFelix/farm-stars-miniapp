from fastapi import APIRouter, Depends, HTTPException, Query, status

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


async def _create_withdrawal(user_id: int, payload: WithdrawalCreateRequest) -> WithdrawalCreateResponse:
    return await create_withdrawal_for_user(user_id, payload)


async def _get_my_withdrawals(user_id: int, limit: int) -> WithdrawalListResponse:
    return await get_my_withdrawals_for_user(user_id=user_id, limit=limit)


@router.get("/eligibility", response_model=WithdrawalEligibilityResponse)
async def get_withdrawal_eligibility(
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalEligibilityResponse:
    return await get_withdrawal_eligibility_for_user(user_id)


@router.post("", response_model=WithdrawalCreateResponse)
async def create_withdrawal(
        payload: WithdrawalCreateRequest,
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalCreateResponse:
    try:
        return await _create_withdrawal(user_id, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create withdrawal: {e}",
        )


@router.get("/my", response_model=WithdrawalListResponse)
async def get_my_withdrawals(
        limit: int = Query(20, ge=1, le=100),
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalListResponse:
    try:
        return await _get_my_withdrawals(user_id=user_id, limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get my withdrawals: {e}",
        )


@router.get("/bot/eligibility/{user_id}", response_model=WithdrawalEligibilityResponse)
async def bot_get_withdrawal_eligibility(
        user_id: int,
) -> WithdrawalEligibilityResponse:
    return await get_withdrawal_eligibility_for_user(user_id)


@router.get("/bot/my/{user_id}", response_model=WithdrawalListResponse)
async def bot_get_my_withdrawals(
        user_id: int,
        limit: int = Query(20, ge=1, le=100),
) -> WithdrawalListResponse:
    try:
        return await _get_my_withdrawals(user_id=user_id, limit=limit)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get my withdrawals: {e}",
        )


@router.post("/bot/create/{user_id}", response_model=WithdrawalCreateResponse)
async def bot_create_withdrawal(
        user_id: int,
        payload: WithdrawalCreateRequest,
) -> WithdrawalCreateResponse:
    try:
        return await _create_withdrawal(user_id, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create withdrawal: {e}",
        )