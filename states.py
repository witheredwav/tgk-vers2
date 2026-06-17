from aiogram.fsm.state import State, StatesGroup


class UserFSM(StatesGroup):
    waiting_key = State()


class AdminFSM(StatesGroup):
    choose_type = State()
    send_content = State()


class BroadcastFSM(StatesGroup):
    collecting = State()   # админ присылает контент (можно несколько сообщений)
    confirm = State()      # подтверждение перед отправкой
