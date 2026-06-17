from aiogram import Router, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from states import AdminFSM
from config import ADMIN_ID

router = Router(name="admin")


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ─── ВХОД В АДМИНКУ ─────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ Нет доступа.")
        return
    await state.clear()
    await message.answer("🛠 *Админ-панель*", parse_mode="Markdown", reply_markup=kb.kb_admin())


@router.callback_query(F.data == "admin_home")
async def cb_admin_home(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text("🛠 *Админ-панель*", parse_mode="Markdown", reply_markup=kb.kb_admin())


# ─── СТАТИСТИКА ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return
    await callback.message.edit_text(
        db.get_stats_text(), parse_mode="Markdown", reply_markup=kb.kb_back_admin()
    )


# ─── СОЗДАНИЕ КОДА ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_create")
async def cb_admin_create(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    code = db.next_free_code()
    if not code:
        await callback.answer("❌ Все коды исчерпаны!", show_alert=True)
        return

    await state.update_data(new_code=code)
    await state.set_state(AdminFSM.choose_type)
    await callback.message.edit_text(
        f"➕ Новый код: *{code}*\n\nВыбери тип контента:",
        parse_mode="Markdown",
        reply_markup=kb.kb_content_type("ctype")
    )


@router.callback_query(F.data.startswith("ctype_"), AdminFSM.choose_type)
async def cb_choose_type(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    ctype = callback.data.replace("ctype_", "")
    await state.update_data(content_type=ctype)
    await state.set_state(AdminFSM.send_content)

    prompts = {
        "text": "📝 Отправь текстовое сообщение:",
        "photo": "🖼 Отправь фото (можно с подписью):",
        "video": "🎬 Отправь видео (можно с подписью):",
        "file": "📁 Отправь файл (можно с подписью):",
        "link": "🔗 Отправь ссылку текстом:",
    }
    await callback.message.edit_text(prompts.get(ctype, "Отправь контент:"), reply_markup=kb.kb_cancel_admin())


@router.message(AdminFSM.send_content)
async def admin_save_content(message: types.Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    data = await state.get_data()
    code = data["new_code"]
    ctype = data["content_type"]
    entry = {"type": ctype}

    if ctype in ("text", "link"):
        if not message.text:
            await message.answer("⚠️ Нужен текст. Попробуй снова:")
            return
        entry["content"] = message.text
    elif ctype == "photo":
        if not message.photo:
            await message.answer("⚠️ Нужно фото. Попробуй снова:")
            return
        entry["content"] = message.photo[-1].file_id
        entry["caption"] = message.caption or ""
    elif ctype == "video":
        if not message.video:
            await message.answer("⚠️ Нужно видео. Попробуй снова:")
            return
        entry["content"] = message.video.file_id
        entry["caption"] = message.caption or ""
    elif ctype == "file":
        if not message.document:
            await message.answer("⚠️ Нужен файл. Попробуй снова:")
            return
        entry["content"] = message.document.file_id
        entry["caption"] = message.caption or ""

    db.save_code(code, entry)
    await state.clear()

    await message.answer(
        f"✅ Код *{code}* сохранён!\nТип: `{ctype}`",
        parse_mode="Markdown",
        reply_markup=kb.kb_admin()
    )


# ─── СПИСОК КОДОВ ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin_codes")
async def cb_admin_codes(callback: types.CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    await state.clear()
    codes = db.list_codes()
    if not codes:
        await callback.message.edit_text("📦 Кодов пока нет.", reply_markup=kb.kb_back_admin())
        return

    await callback.message.edit_text(
        f"📦 *Список кодов* — всего: {len(codes)}",
        parse_mode="Markdown",
        reply_markup=kb.build_codes_kb(codes)
    )


@router.callback_query(F.data.startswith("view_"))
async def cb_view_code(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    code = callback.data.replace("view_", "")
    entry = db.get_code(code)
    if not entry:
        await callback.answer("Код не найден.", show_alert=True)
        return

    preview = str(entry.get("content", ""))[:60]
    text = (
        f"🔑 *Код:* `{code}`\n"
        f"📋 *Тип:* {entry['type']}\n"
        f"📄 *Содержимое:* `{preview}`"
    )
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb.kb_view_code(code))


@router.callback_query(F.data.startswith("ask_del_"))
async def cb_ask_delete(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    code = callback.data.replace("ask_del_", "")
    await callback.message.edit_text(
        f"🗑 Удалить код *{code}*?\n\nЭто действие необратимо.",
        parse_mode="Markdown",
        reply_markup=kb.kb_confirm_del(code)
    )


@router.callback_query(F.data.startswith("del_yes_"))
async def cb_confirm_delete(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    code = callback.data.replace("del_yes_", "")
    if db.delete_code(code):
        await callback.answer(f"✅ Код {code} удалён.", show_alert=True)
    else:
        await callback.answer("❌ Код уже не существует.", show_alert=True)

    codes = db.list_codes()
    if not codes:
        await callback.message.edit_text("📦 Кодов пока нет.", reply_markup=kb.kb_back_admin())
    else:
        await callback.message.edit_text(
            f"📦 *Список кодов* — всего: {len(codes)}",
            parse_mode="Markdown",
            reply_markup=kb.build_codes_kb(codes)
        )
