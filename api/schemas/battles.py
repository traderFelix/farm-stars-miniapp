from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel


BattleState = Literal["idle", "waiting", "active"]
BattleResult = Literal["won", "lost", "draw"]


class BattleRecentResult(BaseModel):
    result: BattleResult
    finished_at: str
    delta: float
    stake_amount: float
    opponent_name: Optional[str] = None


class BattleStatusResponse(BaseModel):
    state: BattleState
    battle_id: Optional[int] = None
    target_views: int = 20
    entry_fee: float = 1.0
    duration_seconds: int = 300
    seconds_left: int = 0
    my_progress: int = 0
    opponent_progress: int = 0
    opponent_name: Optional[str] = None
    current_balance: float = 0
    total_completed_views: int = 0
    can_join: bool = True
    can_cancel: bool = False
    can_open_tasks: bool = False
    hold_seconds_min: int = 5
    hold_seconds_max: int = 8
    message: str = ""
    last_result: Optional[BattleRecentResult] = None
