import json
import os
import random
import string
from datetime import datetime
from threading import Lock

from config import DB_FILE, REFERRAL_TIERS

_lock = Lock()  # защита от одновременной записи при polling

# ─── БАЗОВЫЕ ОПЕРАЦИИ ──────────────────────────────────────────────────────────

def _default_db() -> dict:
    return {
        "codes": {},            # {"00001": {"type": ..., "content": ..., "caption": ...}}
        "stats": {              # {"total": {"event": [user_ids]}, "daily": {"YYYY-MM-DD": {...}}}
            "total": {},
            "daily": {}
        },
        "users": {},             # см. _default_user()
        "discount_codes": {},    # {"AB12CDE34": {"user_id": "123", "tier_percent": 10, "created": "..."}}
        "broadcast_log": []      # история рассылок
    }

def _default_user() -> dict:
    return {
        "joined": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "referrer": None,           # кто пригласил этого пользователя
        "referrals": [],            # все, кто перешёл по ссылке (включая неподтверждённых)
        "confirmed_referrals": [],  # подтвердили подписку на канал — только они считаются для скидок
        "current_tier_percent": 0,  # текущий уровень скидки (0 если нет)
        "manual_adjustment": 0,     # ручная корректировка админом (+/-), не влияет на confirmed_referrals напрямую
    }

def load_db() -> dict:
    if not os.path.exists(DB_FILE):
        return _default_db()
    with open(DB_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    defaults = _default_db()
    for key, val in defaults.items():
        data.setdefault(key, val)
    # миграция пользователей старого формата
    for uid, user in data["users"].items():
        for key, val in _default_user().items():
            if key == "joined":
                continue
            user.setdefault(key, val)
    return data

def save_db(db: dict):
    with _lock:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(db, f, ensure_ascii=False, indent=2)

# ─── СТАТИСТИКА (уникальные пользователи на событие) ─────────────────────────

def track(event: str, user_id: int):
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    uid = str(user_id)

    total_users = db["stats"].setdefault("total", {}).setdefault(event, [])
    if uid not in total_users:
        total_users.append(uid)

    day_users = db["stats"].setdefault("daily", {}).setdefault(today, {}).setdefault(event, [])
    if uid not in day_users:
        day_users.append(uid)

    save_db(db)

def get_stats_text() -> str:
    db = load_db()
    today = datetime.now().strftime("%Y-%m-%d")
    total = db["stats"].get("total", {})
    daily = db["stats"].get("daily", {}).get(today, {})

    events = {
        "start": "🚀 /start",
        "check_sub": "✅ Проверка подписки",
        "works": "🎧 Примеры работ",
        "order": "💬 Заказать сведение",
        "enter_key": "🔑 Ввод ключа",
    }

    total_users_count = len(db.get("users", {}))
    active_codes_count = len(db.get("discount_codes", {}))

    lines = [
        "📊 *Статистика*\n",
        f"👥 Всего пользователей бота: *{total_users_count}*",
        f"🎁 Активных кодов скидки: *{active_codes_count}*\n",
        "*За сегодня:*"
    ]
    for e, label in events.items():
        lines.append(f"  {label}: {len(daily.get(e, []))} чел.")
    lines.append("\n*Всего за всё время:*")
    for e, label in events.items():
        lines.append(f"  {label}: {len(total.get(e, []))} чел.")
    return "\n".join(lines)

# ─── КОНТЕНТНЫЕ КОДЫ (выдача файлов/текста) ────────────────────────────────────

def next_free_code() -> str | None:
    db = load_db()
    existing = set(db["codes"].keys())
    all_codes = [f"{i:05d}" for i in range(1, 100000)]
    free = [c for c in all_codes if c not in existing]
    if not free:
        return None
    return random.choice(free)

def get_code(code: str) -> dict | None:
    db = load_db()
    return db["codes"].get(code)

def save_code(code: str, entry: dict):
    db = load_db()
    db["codes"][code] = entry
    save_db(db)

def delete_code(code: str) -> bool:
    db = load_db()
    if code in db["codes"]:
        del db["codes"][code]
        save_db(db)
        return True
    return False

def list_codes() -> dict:
    db = load_db()
    return db["codes"]

# ─── ПОЛЬЗОВАТЕЛИ ──────────────────────────────────────────────────────────────

def register_user(user_id: int, referrer_id: int | None = None) -> bool:
    """
    Регистрирует пользователя при первом /start. Возвращает True если пользователь новый.
    Реферал на этом этапе только запоминается как "пришедший" — он НЕ засчитывается
    в подтверждённые рефералы (и не влияет на скидку), пока не подтвердит подписку на канал.
    Это первый уровень защиты от накрутки: простой /start без подписки ничего не даёт.
    """
    db = load_db()
    uid = str(user_id)
    is_new = uid not in db["users"]

    if is_new:
        user = _default_user()
        # антифрод: реферал не может пригласить сам себя
        if referrer_id and referrer_id != user_id:
            user["referrer"] = str(referrer_id)
        db["users"][uid] = user

        if user["referrer"]:
            ref_uid = user["referrer"]
            if ref_uid in db["users"]:
                referrals = db["users"][ref_uid]["referrals"]
                if uid not in referrals:
                    referrals.append(uid)

        save_db(db)

    return is_new

def get_user(user_id: int) -> dict | None:
    db = load_db()
    return db["users"].get(str(user_id))

def get_all_user_ids() -> list[str]:
    db = load_db()
    return list(db["users"].keys())

# ─── РЕФЕРАЛЬНАЯ СИСТЕМА С ПОДТВЕРЖДЕНИЕМ И АНТИ-ФРОДОМ ────────────────────────

def _effective_referral_count(user: dict) -> int:
    """
    Эффективное число рефералов для расчёта скидки:
    подтверждённые подпиской рефералы + ручная корректировка админом.
    Не может быть отрицательным.
    """
    count = len(user.get("confirmed_referrals", [])) + user.get("manual_adjustment", 0)
    return max(0, count)

def get_referral_count(user_id: int) -> int:
    user = get_user(user_id)
    if not user:
        return 0
    return _effective_referral_count(user)

def _tier_for_count(count: int) -> int | None:
    """Возвращает % скидки для данного количества рефералов, либо None если ниже первого порога."""
    percent = None
    for threshold, pct in sorted(REFERRAL_TIERS, key=lambda x: x[0]):
        if count >= threshold:
            percent = pct
    return percent

def _generate_discount_code() -> str:
    """9 символов: случайные буквы (латиница, верхний регистр) и цифры."""
    db = load_db()
    existing = set(db["discount_codes"].keys())
    alphabet = string.ascii_uppercase + string.digits
    while True:
        code = "".join(random.choice(alphabet) for _ in range(9))
        if code not in existing:
            return code

def confirm_referral(referred_user_id: int) -> dict | None:
    """
    Вызывается, когда приглашённый пользователь ПОДТВЕРДИЛ подписку на канал
    (а не просто перешёл по ссылке). Это и есть защита от накрутки ботами/фейками:
    подписаться на реальный канал — заметно дороже, чем просто открыть ссылку.

    Засчитывает реферала рефереру, пересчитывает уровень скидки, при необходимости
    генерирует новый код взамен старого.

    Возвращает dict с информацией о смене уровня для уведомления пользователя,
    либо None если уровень не изменился или у пользователя нет реферера.
    """
    db = load_db()
    uid = str(referred_user_id)
    user = db["users"].get(uid)
    if not user or not user.get("referrer"):
        return None

    ref_uid = user["referrer"]
    referrer = db["users"].get(ref_uid)
    if not referrer:
        return None

    # анти-дубль: повторное подтверждение того же реферала не засчитывается второй раз
    confirmed = referrer.setdefault("confirmed_referrals", [])
    if uid in confirmed:
        return None
    confirmed.append(uid)

    old_count = _effective_referral_count(referrer) - 1  # до этого подтверждения
    new_count = _effective_referral_count(referrer)

    old_tier = _tier_for_count(old_count)
    new_tier = _tier_for_count(new_count)

    result = None

    if new_tier != old_tier and new_tier is not None:
        # удаляем старый код этого пользователя, если был
        _delete_user_discount_codes(db, ref_uid)

        # генерируем новый код под новый уровень
        code = _generate_discount_code()
        db["discount_codes"][code] = {
            "user_id": ref_uid,
            "tier_percent": new_tier,
            "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        referrer["current_tier_percent"] = new_tier

        result = {
            "referrer_id": int(ref_uid),
            "new_tier_percent": new_tier,
            "code": code,
            "referral_count": new_count,
        }

    save_db(db)
    return result

def _delete_user_discount_codes(db: dict, user_id: str):
    """Удаляет все активные коды скидки данного пользователя (используется перед выдачей нового)."""
    to_delete = [c for c, data in db["discount_codes"].items() if data["user_id"] == user_id]
    for c in to_delete:
        del db["discount_codes"][c]

def get_referral_leaderboard(limit: int = 10) -> list[tuple[str, int, int]]:
    """Возвращает [(user_id, effective_count, tier_percent)], отсортировано по убыванию."""
    db = load_db()
    rows = []
    for uid, data in db["users"].items():
        count = _effective_referral_count(data)
        if count > 0:
            tier = data.get("current_tier_percent", 0)
            rows.append((uid, count, tier))
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:limit]

def adjust_referral_count(user_id: int, delta: int) -> int:
    """
    Ручная корректировка количества рефералов админом (+1 / -1 / любое значение).
    Не трогает confirmed_referrals напрямую (это лог реальных подтверждений),
    а меняет manual_adjustment — итоговое число это confirmed + manual_adjustment.
    Возвращает новое эффективное количество.
    """
    db = load_db()
    uid = str(user_id)
    user = db["users"].get(uid)
    if not user:
        return 0
    user["manual_adjustment"] = user.get("manual_adjustment", 0) + delta
    save_db(db)
    return _effective_referral_count(user)

# ─── КОДЫ СКИДОК ────────────────────────────────────────────────────────────────

def get_discount_code(code: str) -> dict | None:
    db = load_db()
    return db["discount_codes"].get(code.upper())

def list_discount_codes() -> dict:
    db = load_db()
    return db["discount_codes"]

def delete_discount_code(code: str) -> bool:
    db = load_db()
    code = code.upper()
    if code in db["discount_codes"]:
        del db["discount_codes"][code]
        save_db(db)
        return True
    return False

# ─── ЛОГ РАССЫЛОК ──────────────────────────────────────────────────────────────

def log_broadcast(sent: int, failed: int):
    db = load_db()
    db["broadcast_log"].append({
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "sent": sent,
        "failed": failed
    })
    save_db(db)
