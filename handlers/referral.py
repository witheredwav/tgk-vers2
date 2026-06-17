from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext

import database as db
import keyboards as kb
from config import ADMIN_ID, REFERRAL_TIERS
from handlers.user import notify_referrer

router = Router(name="referral")


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ══════════════════════════════════════════════════════════════════════════════
#  ПОЛЬЗОВАТЕЛЬ: ПРОГРЕСС РЕФЕРАЛЬНОЙ ПРОГРАММЫ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "referral_info")
async def cb_referral_info(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    bot_info = await callback.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start=ref{user_id}"
    ref_link_escaped = ref_link.replace("_", "\\_")  # экранируем подчёркивания для Markdown-режима
    count = db.get_referral_count(user_id)

    tiers_sorted = sorted(REFERRAL_TIERS, key=lambda x: x[0])
    next_tier = next((t for t in tiers_sorted if t[0] > count), None)

    lines = [
        "🤝 *Реферальная программа*\n",
        f"Твоя ссылка (нажми, чтобы скопировать или переслать):\n{ref_link_escaped}\n",
        f"Подтверждённых друзей: *{count}*\n",
        "*Уровни скидок:*"
    ]
    for threshold, percent in tiers_sorted:
        mark = "✅" if count >= threshold else "▫️"
        lines.append(f"{mark} {threshold} друзей → скидка {percent}%")

    lines.append("")
    if next_tier:
        remaining = next_tier[0] - count
        lines.append(f"Пригласи ещё *{remaining}* друзей для скидки *{next_tier[1]}%*!")
    else:
        lines.append("🎉 Ты достиг максимального уровня скидки!")

    existing = [c for c, d in db.list_discount_codes().items() if d["user_id"] == str(user_id)]
    if existing:
        code = existing[0]
        percent = db.list_discount_codes()[code]["tier_percent"]
        lines.append(f"\n🎁 Твой код скидки *{percent}%*:\n`{code}`\nПришли его нам в личные сообщения для применения.")

    lines.append(
        "\n_Друг засчитывается только после того, как подпишется на канал — "
        "просто перехода по ссылке недостаточно._\n\n"
        "_Скидка действует на весь заказ целиком: можно заказать одно сведение "
        "или сразу несколько треков — скидка применится один раз ко всей сумме. "
        "После использования кода списывается ровно столько друзей, сколько требовал "
        "этот уровень — остаток выше порога сохранится и продолжит копиться к следующей скидке._"
    )

    kb_referral = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(
            text="📤 Поделиться ссылкой",
            switch_inline_query=f"Присоединяйся! {ref_link}"
        )],
        [types.InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_page2")],
    ])

    await callback.message.edit_text(
        "\n".join(lines), parse_mode="Markdown", reply_markup=kb_referral
    )


# ══════════════════════════════════════════════════════════════════════════════
#  АДМИН: УПРАВЛЕНИЕ РЕФЕРАЛАМИ
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin_referrals")
async def cb_admin_referrals(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    leaderboard = db.get_referral_leaderboard(15)
    if not leaderboard:
        await callback.message.edit_text(
            "🏆 *Топ рефералов*\n\nПока никто никого не пригласил.",
            parse_mode="Markdown",
            reply_markup=kb.kb_back_admin()
        )
        return

    buttons = []
    lines = ["🏆 *Топ рефералов*\n", "Нажми на пользователя, чтобы изменить число рефералов:\n"]
    for i, (uid, count, tier) in enumerate(leaderboard, 1):
        tier_text = f" (скидка {tier}%)" if tier else ""
        lines.append(f"{i}. ID `{uid}` — {count} друзей{tier_text}")
        buttons.append([
            types.InlineKeyboardButton(text=f"ID {uid} — {count} 👥", callback_data=f"refadj_{uid}")
        ])
    buttons.append([types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")])

    await callback.message.edit_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("refadj_"))
async def cb_referral_adjust_menu(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    uid = callback.data.replace("refadj_", "")
    count = db.get_referral_count(int(uid))

    code_line = ""
    existing = [c for c, d in db.list_discount_codes().items() if d["user_id"] == uid]
    if existing:
        code = existing[0]
        percent = db.list_discount_codes()[code]["tier_percent"]
        code_line = f"\n🎁 Действующий код: `{code}` ({percent}%)"

    kb_adjust = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="➖ 1", callback_data=f"refdelta_{uid}_-1"),
            types.InlineKeyboardButton(text="➕ 1", callback_data=f"refdelta_{uid}_1"),
        ],
        [
            types.InlineKeyboardButton(text="➖ 5", callback_data=f"refdelta_{uid}_-5"),
            types.InlineKeyboardButton(text="➕ 5", callback_data=f"refdelta_{uid}_5"),
        ],
        [types.InlineKeyboardButton(text="◀️ К списку", callback_data="admin_referrals")],
    ])

    await callback.message.edit_text(
        f"👤 Пользователь ID `{uid}`\nТекущее число рефералов: *{count}*"
        f"{code_line}\n\nВыбери изменение:",
        parse_mode="Markdown",
        reply_markup=kb_adjust
    )


@router.callback_query(F.data.startswith("refdelta_"))
async def cb_referral_apply_delta(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    # формат: refdelta_<uid>_<delta>
    parts = callback.data.split("_")
    uid = parts[1]
    delta = int(parts[2])

    result = db.adjust_referral_count(int(uid), delta)

    if result is None:
        await callback.answer("❌ Пользователь не найден.", show_alert=True)
        return

    # уведомляем самого пользователя — точно так же, как при обычном реферале,
    # чтобы для него ручная корректировка и реальный реферал выглядели одинаково
    await notify_referrer(callback.bot, result)

    if result["tier_changed"] and result["code"]:
        await callback.answer(
            f"✅ Новое количество: {result['referral_count']}. "
            f"Выдан новый код {result['code']} ({result['tier_percent']}%).",
            show_alert=True
        )
    else:
        await callback.answer(f"✅ Новое количество: {result['referral_count']}", show_alert=True)

    code_line = ""
    if result["code"]:
        code_line = f"\n🎁 Выдан код: `{result['code']}` ({result['tier_percent']}%)"
    elif result["tier_percent"]:
        # уровень не сменился сейчас, но у пользователя уже есть активный код с прошлого раза
        existing = [c for c, d in db.list_discount_codes().items() if d["user_id"] == uid]
        if existing:
            code_line = f"\n🎁 Действующий код: `{existing[0]}` ({result['tier_percent']}%)"

    kb_adjust = types.InlineKeyboardMarkup(inline_keyboard=[
        [
            types.InlineKeyboardButton(text="➖ 1", callback_data=f"refdelta_{uid}_-1"),
            types.InlineKeyboardButton(text="➕ 1", callback_data=f"refdelta_{uid}_1"),
        ],
        [
            types.InlineKeyboardButton(text="➖ 5", callback_data=f"refdelta_{uid}_-5"),
            types.InlineKeyboardButton(text="➕ 5", callback_data=f"refdelta_{uid}_5"),
        ],
        [types.InlineKeyboardButton(text="◀️ К списку", callback_data="admin_referrals")],
    ])
    await callback.message.edit_text(
        f"👤 Пользователь ID `{uid}`\nТекущее число рефералов: *{result['referral_count']}*"
        f"{code_line}\n\nВыбери изменение:",
        parse_mode="Markdown",
        reply_markup=kb_adjust
    )


# ══════════════════════════════════════════════════════════════════════════════
#  АДМИН: КОДЫ СКИДОК
# ══════════════════════════════════════════════════════════════════════════════

@router.callback_query(F.data == "admin_discounts")
async def cb_admin_discounts(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    codes = db.list_discount_codes()
    if not codes:
        await callback.message.edit_text(
            "🎁 *Коды скидок*\n\nАктивных кодов нет.",
            parse_mode="Markdown",
            reply_markup=kb.kb_back_admin()
        )
        return

    buttons = []
    for code, data in sorted(codes.items(), key=lambda x: x[1]["created"], reverse=True):
        label = f"{code} — {data['tier_percent']}% (ID {data['user_id']})"
        buttons.append([
            types.InlineKeyboardButton(text=label, callback_data=f"viewdisc_{code}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"deldisc_{code}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")])

    await callback.message.edit_text(
        f"🎁 *Коды скидок* — активно: {len(codes)}\n\n"
        f"Нажми 🗑 после того как пользователь воспользовался кодом.",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons)
    )


@router.callback_query(F.data.startswith("viewdisc_"))
async def cb_view_discount(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    code = callback.data.replace("viewdisc_", "")
    data = db.get_discount_code(code)
    if not data:
        await callback.answer("Код не найден.", show_alert=True)
        return

    text = (
        f"🎁 *Код скидки:* `{code}`\n"
        f"👤 *Пользователь:* `{data['user_id']}`\n"
        f"💸 *Скидка:* {data['tier_percent']}%\n"
        f"📅 *Создан:* {data['created']}\n\n"
        f"_При удалении у пользователя будет вычтено {data.get('tier_threshold', 0)} рефералов "
        f"(порог этого уровня) — остаток выше порога сохранится и продолжит копиться._"
    )
    kb_back = types.InlineKeyboardMarkup(inline_keyboard=[
        [types.InlineKeyboardButton(text="🗑 Удалить (использован)", callback_data=f"deldisc_{code}")],
        [types.InlineKeyboardButton(text="◀️ К списку", callback_data="admin_discounts")],
    ])
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=kb_back)


@router.callback_query(F.data.startswith("deldisc_"))
async def cb_delete_discount(callback: types.CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("⛔ Нет доступа.", show_alert=True)
        return

    code = callback.data.replace("deldisc_", "")
    deducted = db.get_discount_code(code)
    deduct_amount = deducted.get("tier_threshold", 0) if deducted else 0
    deleted = db.delete_discount_code(code)
    if deleted:
        await callback.answer(f"✅ Код {code} удалён. Списано {deduct_amount} рефералов.", show_alert=True)
        try:
            new_count = db.get_referral_count(int(deleted["user_id"]))
            extra = ""
            if new_count > 0:
                extra = f" У тебя остаётся *{new_count}* друзей — они продолжают копиться к следующему уровню!"
            await callback.bot.send_message(
                int(deleted["user_id"]),
                "✅ *Скидка применена к заказу!*\n\n"
                f"Спасибо, что воспользовался реферальной программой.{extra}",
                parse_mode="Markdown"
            )
        except Exception:
            pass
    else:
        await callback.answer("❌ Код уже не существует.", show_alert=True)

    # обновлённый список
    codes = db.list_discount_codes()
    if not codes:
        await callback.message.edit_text(
            "🎁 *Коды скидок*\n\nАктивных кодов нет.",
            parse_mode="Markdown",
            reply_markup=kb.kb_back_admin()
        )
        return

    buttons = []
    for c, data in sorted(codes.items(), key=lambda x: x[1]["created"], reverse=True):
        label = f"{c} — {data['tier_percent']}% (ID {data['user_id']})"
        buttons.append([
            types.InlineKeyboardButton(text=label, callback_data=f"viewdisc_{c}"),
            types.InlineKeyboardButton(text="🗑", callback_data=f"deldisc_{c}"),
        ])
    buttons.append([types.InlineKeyboardButton(text="◀️ Назад", callback_data="admin_home")])

    await callback.message.edit_text(
        f"🎁 *Коды скидок* — активно: {len(codes)}",
        parse_mode="Markdown",
        reply_markup=types.InlineKeyboardMarkup(inline_keyboard=buttons)
    )
