import asyncio
import logging

from aiogram import Router, F, types
from aiogram.exceptions import TelegramForbiddenError, TelegramBadRequest
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import BroadcastFSM
from config import ADMIN_ID

router = Router(name="broadcast")


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ─── НАЧАЛО РАССЫЛКИ ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    await state.update_data(broadcast_messages=[])
    await state.set_state(BroadcastFSM.collecting)

    await callback.message.edit_text(
        "📢 *Рассылка*\n\n"
        "Отправь любой контент (текст, фото, видео, файл, ссылку) — можно несколько сообщений подряд, "
        "они будут отправлены всем пользователям в том же порядке.\n\n"
        "Когда закончишь — нажми *«Готово»*.",
        parse_mode="Markdown",
        reply_markup=_kb_collecting()
    )


def _kb_collecting() -> types.InlineKeyboardMarkup:
    return types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="✅ Готово", callback_data="broadcast_done")],
        [types.InlineKeyboardButton(text="❌ Отмена", callback_data="admin_home")],
    ])


# ─── СБОР СООБЩЕНИЙ ──────────────────────────────────────────────────────────────

@router.message(BroadcastFSM.collecting)
async def collect_broadcast_message(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    messages = data.get("broadcast_messages", [])

    # Сохраняем минимально необходимое: тип + содержимое + caption + текст
    item = _serialize_message(message)
    if item is None:
        await message.answer("⚠️ Этот тип контента не поддерживается для рассылки.")
        return

    messages.append(item)
    await state.update_data(broadcast_messages=messages)

    await message.answer(
        f"✅ Добавлено ({len(messages)} сообщ. в очереди). Можешь прислать ещё, либо нажми «Готово».",
        reply_markup=_kb_collecting()
    )


def _serialize_message(message: types.Message) -> dict | None:
    # Порядок проверок важен: медиа-сообщение может содержать caption,
    # но не message.text, поэтому сначала проверяем специфичные типы.
    if message.photo:
        return {"type": "photo", "file_id": message.photo[-1].file_id, "caption": message.caption or ""}
    if message.video:
        return {"type": "video", "file_id": message.video.file_id, "caption": message.caption or ""}
    if message.animation:
        return {"type": "animation", "file_id": message.animation.file_id, "caption": message.caption or ""}
    if message.document:
        return {"type": "document", "file_id": message.document.file_id, "caption": message.caption or ""}
    if message.audio:
        return {"type": "audio", "file_id": message.audio.file_id, "caption": message.caption or ""}
    if message.voice:
        return {"type": "voice", "file_id": message.voice.file_id}
    if message.sticker:
        return {"type": "sticker", "file_id": message.sticker.file_id}
    if message.text:
        return {"type": "text", "text": message.text}
    return None


# ─── ПОДТВЕРЖДЕНИЕ ───────────────────────────────────────────────────────────────

@router.callback_query(BroadcastFSM.collecting, F.data == "broadcast_done")
async def cb_broadcast_done(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    data = await state.get_data()
    messages = data.get("broadcast_messages", [])

    if not messages:
        await callback.answer("⚠️ Ты ничего не отправил. Сначала пришли контент.", show_alert=True)
        return

    total_users = len(db.get_all_user_ids())
    await state.set_state(BroadcastFSM.confirm)

    await callback.message.edit_text(
        f"📢 *Подтверждение рассылки*\n\n"
        f"Сообщений в очереди: *{len(messages)}*\n"
        f"Получателей: *{total_users}* пользователей\n\n"
        f"Отправить всем?",
        parse_mode="Markdown",
        reply_markup=kb.kb_broadcast_confirm()
    )


# ─── ОТПРАВКА ────────────────────────────────────────────────────────────────────

@router.callback_query(BroadcastFSM.confirm, F.data == "broadcast_send")
async def cb_broadcast_send(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    data = await state.get_data()
    messages = data.get("broadcast_messages", [])
    await state.clear()

    user_ids = db.get_all_user_ids()
    await callback.message.edit_text(f"📤 Начинаю рассылку для {len(user_ids)} пользователей...")

    bot = callback.bot
    sent, failed = 0, 0

    for uid in user_ids:
        try:
            await _send_broadcast_to_user(bot, int(uid), messages)
            sent += 1
        except TelegramForbiddenError:
            failed += 1  # пользователь заблокировал бота
        except TelegramBadRequest:
            failed += 1
        except Exception as e:
            logging.warning(f"Ошибка рассылки для {uid}: {e}")
            failed += 1

        await asyncio.sleep(0.05)  # защита от лимитов Telegram (~20 msg/sec)

    db.log_broadcast(sent, failed)

    await callback.message.answer(
        f"✅ *Рассылка завершена*\n\nДоставлено: *{sent}*\nНе удалось: *{failed}*",
        parse_mode="Markdown",
        reply_markup=kb.kb_back_admin()
    )


async def _send_broadcast_to_user(bot, user_id: int, messages: list[dict]):
    for item in messages:
        t = item["type"]
        if t == "text":
            await bot.send_message(user_id, item["text"])
        elif t == "photo":
            await bot.send_photo(user_id, item["file_id"], caption=item.get("caption") or None)
        elif t == "video":
            await bot.send_video(user_id, item["file_id"], caption=item.get("caption") or None)
        elif t == "animation":
            await bot.send_animation(user_id, item["file_id"], caption=item.get("caption") or None)
        elif t == "document":
            await bot.send_document(user_id, item["file_id"], caption=item.get("caption") or None)
        elif t == "audio":
            await bot.send_audio(user_id, item["file_id"], caption=item.get("caption") or None)
        elif t == "voice":
            await bot.send_voice(user_id, item["file_id"])
        elif t == "sticker":
            await bot.send_sticker(user_id, item["file_id"])
