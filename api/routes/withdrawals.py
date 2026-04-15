import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from api.dependencies.auth import get_current_user_id
from api.dependencies.internal import require_internal_token
from api.security.request_fingerprint import build_request_fingerprint
from api.schemas.withdrawals import (
    WithdrawalEligibilityResponse,
    WithdrawalCreateRequest,
    WithdrawalCreateResponse,
    WithdrawalListResponse,
    WithdrawalPreviewRequest,
    WithdrawalPreviewResponse,
)
from api.services.withdrawals import (
    get_withdrawal_eligibility_for_user,
    create_withdrawal_for_user,
    get_my_withdrawals_for_user,
    preview_withdrawal_for_user,
)

router = APIRouter(prefix="/withdrawals", tags=["withdrawals"])
logger = logging.getLogger(__name__)

WITHDRAWALS_SERVICE_UNAVAILABLE_DETAIL = "Не удалось обработать вывод. Попробуй еще раз чуть позже."


async def _create_withdrawal(
        user_id: int,
        payload: WithdrawalCreateRequest,
        *,
        request: Optional[Request] = None,
) -> WithdrawalCreateResponse:
    return await create_withdrawal_for_user(
        user_id,
        payload,
        fingerprint=build_request_fingerprint(request) if request is not None else None,
    )


async def _preview_withdrawal(
        user_id: int,
        payload: WithdrawalPreviewRequest,
        *,
        request: Optional[Request] = None,
) -> WithdrawalPreviewResponse:
    return await preview_withdrawal_for_user(
        user_id,
        payload,
        fingerprint=build_request_fingerprint(request) if request is not None else None,
    )


async def _get_my_withdrawals(user_id: int, limit: int) -> WithdrawalListResponse:
    return await get_my_withdrawals_for_user(user_id=user_id, limit=limit)


def _raise_withdrawals_service_error(action: str, exc: Exception) -> None:
    logger.exception("Withdrawals route failed during %s", action)
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=WITHDRAWALS_SERVICE_UNAVAILABLE_DETAIL,
    ) from exc


@router.get("/eligibility", response_model=WithdrawalEligibilityResponse)
async def get_withdrawal_eligibility(
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalEligibilityResponse:
    return await get_withdrawal_eligibility_for_user(user_id)


@router.post("", response_model=WithdrawalCreateResponse)
async def create_withdrawal(
        payload: WithdrawalCreateRequest,
        request: Request,
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalCreateResponse:
    try:
        return await _create_withdrawal(user_id, payload, request=request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        _raise_withdrawals_service_error("create withdrawal", e)


@router.post("/preview", response_model=WithdrawalPreviewResponse)
async def preview_withdrawal(
        payload: WithdrawalPreviewRequest,
        request: Request,
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalPreviewResponse:
    try:
        return await _preview_withdrawal(user_id, payload, request=request)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        _raise_withdrawals_service_error("preview withdrawal", e)


@router.get("/my", response_model=WithdrawalListResponse)
async def get_my_withdrawals(
        limit: int = Query(20, ge=1, le=100),
        user_id: int = Depends(get_current_user_id),
) -> WithdrawalListResponse:
    try:
        return await _get_my_withdrawals(user_id=user_id, limit=limit)
    except Exception as e:
        _raise_withdrawals_service_error("get my withdrawals", e)


@router.get("/bot/eligibility/{user_id}", response_model=WithdrawalEligibilityResponse)
async def bot_get_withdrawal_eligibility(
        user_id: int,
        _: None = Depends(require_internal_token),
) -> WithdrawalEligibilityResponse:
    return await get_withdrawal_eligibility_for_user(user_id)


@router.post("/bot/preview/{user_id}", response_model=WithdrawalPreviewResponse)
async def bot_preview_withdrawal(
        user_id: int,
        payload: WithdrawalPreviewRequest,
        _: None = Depends(require_internal_token),
) -> WithdrawalPreviewResponse:
    try:
        return await _preview_withdrawal(user_id, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        _raise_withdrawals_service_error("bot preview withdrawal", e)


@router.get("/bot/my/{user_id}", response_model=WithdrawalListResponse)
async def bot_get_my_withdrawals(
        user_id: int,
        limit: int = Query(20, ge=1, le=100),
        _: None = Depends(require_internal_token),
) -> WithdrawalListResponse:
    try:
        return await _get_my_withdrawals(user_id=user_id, limit=limit)
    except Exception as e:
        _raise_withdrawals_service_error("bot get my withdrawals", e)


@router.post("/bot/create/{user_id}", response_model=WithdrawalCreateResponse)
async def bot_create_withdrawal(
        user_id: int,
        payload: WithdrawalCreateRequest,
        _: None = Depends(require_internal_token),
) -> WithdrawalCreateResponse:
    try:
        return await _create_withdrawal(user_id, payload)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        _raise_withdrawals_service_error("bot create withdrawal", e)
