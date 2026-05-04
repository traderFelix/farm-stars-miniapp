from aiogram.fsm.state import StatesGroup, State

class CampaignCreate(StatesGroup):
    key = State()
    amount = State()
    title = State()
    post_url = State()


class PromoCreate(StatesGroup):
    code = State()
    amount = State()
    total_uses = State()
    title = State()
    scope = State()
    partner_ref = State()
    partner_channel_chat_id = State()

class AddWinners(StatesGroup):
    usernames = State()

class DeleteWinner(StatesGroup):
    username = State()

class UserLookup(StatesGroup):
    user = State()

class AdminAdjust(StatesGroup):
    amount = State()

class AdminRefundFee(StatesGroup):
    waiting_manual_data = State()


class PartnerViewsAccrualCreate(StatesGroup):
    partner_ref = State()
    channel_chat_id = State()
    views_promised = State()


class TaskChannelCreate(StatesGroup):
    chat_id = State()
    owner_type = State()
    client_ref = State()
    total_bought_views = State()
    views_per_post = State()
    view_seconds = State()

class TaskChannelEdit(StatesGroup):
    views_per_post = State()
    view_seconds = State()


class TaskChannelAddViews(StatesGroup):
    amount = State()


class TaskChannelBindClient(StatesGroup):
    owner_type = State()
    client_ref = State()


class TaskChannelManualPost(StatesGroup):
    post_url = State()


class SubscriptionTaskCreate(StatesGroup):
    chat_id = State()
    owner_type = State()
    client_ref = State()
    channel_url = State()
    instant_reward = State()
    daily_reward_total = State()
    daily_claim_days = State()
    max_subscribers = State()


class SubscriptionTaskBindClient(StatesGroup):
    owner_type = State()
    client_ref = State()
