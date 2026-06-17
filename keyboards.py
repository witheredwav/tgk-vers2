from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from config import CHANNEL_LINK, WORKS_CHANNEL_LINK, DM_LINK

# ─── ПОЛЬЗОВАТЕЛЬСКИЕ КЛАВИАТУРЫ ───────────────────────────────────────────────

def kb_page1() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔔 Подписаться на канал", url=CHANNEL_LINK)],
        [InlineKeyboardButton(text="✅ Проверить подписку", callback_data="check_sub")],
    ])

def kb_page2() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎧 Примеры работ", url=WORKS_CHANNEL_LINK)],
        [InlineKeyboardButton(text="💬 Заказать сведение", url=DM_LINK)],
        [InlineKeyboardButton(text="🔑 Ввести ключ", callback_data="enter_key")],
        [InlineKeyboardButton(text="🤝 Реферальная программа", callback_data="referral_info")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_page1")],
    ])

def kb_cancel_key() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_key")]
    ])

def kb_back_to_page2() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_page2")]
    ])

# ─── АДМИНСКИЕ КЛАВИАТУРЫ ───────────────────────────────────────────────────────

def kb_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="➕ Создать код", callback_data="admin_create")],
        [InlineKeyboardButton(text="📦 Список кодов", callback_data="admin_codes")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="🏆 Рефералы", callback_data="admin_referrals")],
        [InlineKeyboardButton(text="🎁 Коды скидок", callback_data="admin_discounts")],
    ])

def kb_content_type(prefix: str = "ctype") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Текст", callback_data=f"{prefix}_text"),
         InlineKeyboardButton(text="🖼 Фото", callback_data=f"{prefix}_photo")],
        [InlineKeyboardButton(text="🎬 Видео", callback_data=f"{prefix}_video"),
         InlineKeyboardButton(text="📁 Файл", callback_data=f"{prefix}_file")],
        [InlineKeyboardButton(text="🔗 Ссылка", callback_data=f"{prefix}_link")],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_home")],
    ])

def kb_confirm_del(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Да, удалить", callback_data=f"del_yes_{code}"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="admin_codes")],
    ])

def kb_back_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")]
    ])

def kb_cancel_admin() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_home")]
    ])

def build_codes_kb(codes: dict) -> InlineKeyboardMarkup:
    buttons = []
    for code, entry in sorted(codes.items()):
        buttons.append([
            InlineKeyboardButton(text=f"🔑 {code}  [{entry['type']}]", callback_data=f"view_{code}"),
            InlineKeyboardButton(text="🗑", callback_data=f"ask_del_{code}"),
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def kb_view_code(code: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"ask_del_{code}")],
        [InlineKeyboardButton(text="◀️ К списку кодов", callback_data="admin_codes")],
    ])

# ─── РАССЫЛКА ────────────────────────────────────────────────────────────────

def kb_broadcast_start() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_home")]
    ])

def kb_broadcast_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Отправить всем", callback_data="broadcast_send"),
         InlineKeyboardButton(text="❌ Отмена", callback_data="admin_home")],
    ])
