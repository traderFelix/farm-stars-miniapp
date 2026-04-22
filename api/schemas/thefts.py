from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


TheftState = Literal["idle", "active", "protected"]
TheftRole = Literal["attacker", "victim", "protector"]
TheftResult = Literal["stolen", "defended", "expired", "protected"]


class TheftActivitySnapshot(BaseModel):
    state: Literal["active", "finished"]
    kind: Literal["attack", "defense", "protection"]
    result: Optional[TheftResult] = None
    role: TheftRole
    my_progress: int = 0
    target_views: int = 0
    opponent_progress: int = 0
    opponent_target_views: int = 0
    seconds_left: int = 0
    amount: float = 0
    opponent_name: Optional[str] = None


class TheftRecentResult(BaseModel):
    result: TheftResult
    role: TheftRole
    finished_at: str
    amount: float = 0
    opponent_name: Optional[str] = None


class TheftStatusResponse(BaseModel):
    state: TheftState
    message: str = ""
    theft_id: Optional[int] = None
    protection_attempt_id: Optional[int] = None
    role: Optional[TheftRole] = None
    amount: float = 0
    my_progress: int = 0
    target_views: int = 0
    opponent_progress: int = 0
    opponent_target_views: int = 0
    seconds_left: int = 0
    opponent_name: Optional[str] = None
    protected_until: Optional[str] = None
    can_attack: bool = True
    can_protect: bool = True
    last_result: Optional[TheftRecentResult] = None


class TheftActionResponse(BaseModel):
    ok: bool
    message: str
    status: TheftStatusResponse
