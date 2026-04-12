from pydantic import BaseModel


class ReferralMeResponse(BaseModel):
    user_id: int
    invited_count: int
    reward_percent: float
    invite_link: str
    share_text: str
