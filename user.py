import logging

from aiogram import Router, F, types
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import UserFSM

router = Router(name="user")


async def is_subscribed(bot, channel_id: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(channel_id, user_id)
        return member.status in ("member", "administrator", "creator")
    except Exception as e:
        logging.warning(f"Не удалось проверить подписку для {user_id}: {e}")
        return False


# ─── /start (+ реферальные deep links) ────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext, command: CommandObject):
    await state.clear()

    referrer_id = None
    if command.args and command.args.startswith("ref"):
        try:
            referrer_id = int(command.args.replace("ref", ""))
        except ValueError:
            referrer_id = None

    is_new = db.register_user(message.from_user.id, referrer_id)
    db.track("start", message.from_user.id)

    text = "👋 Привет!\n\nЧтобы получить доступ к боту — подпишись на наш канал и нажми «Проверить подписку»."
    if is_new and referrer_id:
        text = "👋 Привет! Ты пришёл по приглашению друга 🤝\n\n" + text

    await message.answer(text, reply_markup=kb.kb_page1())


# ─── Проверка подписки ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "check_sub")
async def cb_check_sub(callback: types.CallbackQuery):
    db.track("check_sub", callback.from_user.id)

    from config import CHANNEL_ID
    if await is_subscribed(callback.bot, CHANNEL_ID, callback.from_user.id):
        # Подписка подтверждена — это ключевой момент для анти-фрода:
        # реферал засчитывается рефереру только сейчас, а не при простом /start.
        result = db.confirm_referral(callback.from_user.id)
        if result:
            await _notify_referrer_new_tier(callback.bot, result)

        await callback.message.edit_text(
            "✅ Подписка подтверждена!\n\nДобро пожаловать. Выбери действие:",
            reply_markup=kb.kb_page2()
        )
    else:
        await callback.answer(
            "❌ Ты ещё не подписан на канал.\nПодпишись и попробуй снова!",
            show_alert=True
        )


async def _notify_referrer_new_tier(bot, result: dict):
    """Уведомляет реферера о новом уровне скидки и новом коде."""
    try:
        await bot.send_message(
            result["referrer_id"],
            f"🎉 *Поздравляем!*\n\n"
            f"У тебя теперь *{result['referral_count']}* подтверждённых друзей по реферальной программе.\n"
            f"Ты получаешь скидку *{result['new_tier_percent']}%*!\n\n"
            f"Твой код скидки:\n`{result['code']}`\n\n"
            f"Пришли этот код нам в личные сообщения, чтобы получить скидку.",
            parse_mode="Markdown"
        )
    except Exception as e:
        logging.warning(f"Не удалось отправить уведомление о реферальном бонусе: {e}")


@router.callback_query(F.data == "back_to_page1")
async def cb_back_page1(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "👋 Привет!\n\nЧтобы получить доступ к боту — подпишись на наш канал и нажми «Проверить подписку».",
        reply_markup=kb.kb_page1()
    )


@router.callback_query(F.data == "back_to_page2")
async def cb_back_page2(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "✅ Главное меню:",
        reply_markup=kb.kb_page2()
    )


# ─── Ввод ключа ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "enter_key")
async def cb_enter_key(callback: types.CallbackQuery, state: FSMContext):
    db.track("enter_key", callback.from_user.id)

    from config import CHANNEL_ID
    if not await is_subscribed(callback.bot, CHANNEL_ID, callback.from_user.id):
        await callback.answer("❌ Сначала подпишись на канал!", show_alert=True)
        return

    await state.set_state(UserFSM.waiting_key)
    await callback.message.answer("🔑 Введи 5-значный код:", reply_markup=kb.kb_cancel_key())
    await callback.answer()


@router.callback_query(F.data == "cancel_key")
async def cb_cancel_key(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.delete()
    await callback.message.answer("Главное меню:", reply_markup=kb.kb_page2())


@router.message(UserFSM.waiting_key)
async def process_key(message: types.Message, state: FSMContext):
    code = message.text.strip() if message.text else ""
    entry = db.get_code(code)

    if not entry:
        await message.answer("❌ Неверный код. Попробуй ещё раз:", reply_markup=kb.kb_cancel_key())
        return

    ctype = entry["type"]
    content = entry["content"]
    caption = entry.get("caption", "") or f"Код: {code}"

    await state.clear()

    if ctype in ("text", "link"):
        await message.answer(f"✅ *Код {code}:*\n\n{content}", parse_mode="Markdown")
    elif ctype == "photo":
        await message.answer_photo(content, caption=caption)
    elif ctype == "video":
        await message.answer_video(content, caption=caption)
    elif ctype == "file":
        await message.answer_document(content, caption=caption)

    await message.answer("Главное меню:", reply_markup=kb.kb_page2())
