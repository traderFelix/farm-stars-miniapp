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

class TaskChannelCreate(StatesGroup):
    chat_id = State()
    client_ref = State()
    total_bought_views = State()
    views_per_post = State()
    view_seconds = State()

class TaskChannelEdit(StatesGroup):
    total_bought_views = State()
    views_per_post = State()
    view_seconds = State()


class TaskChannelBindClient(StatesGroup):
    client_ref = State()
