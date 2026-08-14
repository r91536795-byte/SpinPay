import os
import sqlite3
import time
import threading
import html
from datetime import datetime
import telebot
from telebot import types

TOKEN = os.environ.get("BOT_TOKEN", "СЮДА_ВСТАВИТЬ_ТОКЕН")
MAIN_ADMIN = 8957913298
SUPPORT = "@Helpspinpaybot"
BOT_NAME = "SpinPay"

bot = telebot.TeleBot(TOKEN)
temp_data = {}
payment_timers = {}

# ====================== PREMIUM ЭМОДЗИ ======================
def e(eid, fallback="✨"):
    return f'<tg-emoji emoji-id="{eid}">{fallback}</tg-emoji>'

ROCKET    = e("5368415277984674720", "🚀")
WALLET    = e("5368582040173041416", "👛")
MONEY     = e("5368324170671202286", "💰")
CHECK     = e("5368641901145508892", "✅")
CROSS     = e("5368755601831522045", "❌")
CLOCK     = e("5368742540911475176", "⏳")
LIGHT     = e("5368579480372533038", "⚡️")
FIRE      = e("5368420657531872134", "🔥")
INFO      = e("5370811563224483783", "ℹ️")
SUPPORT_E = e("5368782333799408226", "👨‍💻")
ADMIN_E   = e("5370836560085140324", "⚙️")
QR_E      = e("5368723230722570086", "🖼")
LINK      = e("5368600078020664977", "🔗")
OFF       = e("5368637503082218084", "🔴")
ON        = e("5368536096337446554", "🟢")

def safe(t):
    return html.escape(str(t)) if t else ""

def delete_msg(chat_id, msg_id):
    try:
        bot.delete_message(chat_id, msg_id)
    except:
        pass

def init_db():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("""CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY, join_date TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS deposits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER, amount REAL, account_id TEXT,
                        photo_id TEXT, status TEXT, date TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS qr_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, file_id TEXT, date TEXT)""")
        c.execute("INSERT OR IGNORE INTO admins (chat_id) VALUES (?)", (MAIN_ADMIN,))
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_active', 'True')")
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auto_approve', 'False')")
        conn.commit()

def is_bot_active():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='bot_active'")
        row = c.fetchone()
        return row is None or row[0] == "True"

def set_bot_active(v):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_active', ?)", (str(v),))
        conn.commit()

def is_auto_approve():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='auto_approve'")
        row = c.fetchone()
        return row and row[0] == "True"

def set_auto_approve(v):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_approve', ?)", (str(v),))
        conn.commit()

def get_admins():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT chat_id FROM admins")
        admins = [r[0] for r in c.fetchall()]
        if MAIN_ADMIN not in admins:
            admins.append(MAIN_ADMIN)
        return admins

def add_user(cid):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT 1 FROM users WHERE chat_id=?", (cid,))
        if not c.fetchone():
            c.execute("INSERT INTO users (chat_id, join_date) VALUES (?, ?)",
                      (cid, datetime.now().strftime("%d.%m.%Y %H:%M")))
            conn.commit()

def add_deposit(uid, amount, account_id, photo_id):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO deposits (user_id, amount, account_id, photo_id, status, date)
                     VALUES (?, ?, ?, ?, 'pending', ?)""",
                  (uid, amount, account_id, photo_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
        dep_id = c.lastrowid
        conn.commit()
        return dep_id

def get_last_qr():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT file_id FROM qr_codes ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        return row[0] if row else None

def get_stats():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        users = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'")
        pending = c.fetchone()[0]
        c.execute("SELECT COALESCE(SUM(amount),0) FROM deposits WHERE status='approved'")
        total = c.fetchone()[0]
        return users, pending, total

init_db()

# ====================== КЛАВИАТУРЫ ======================
def main_menu(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("⬆️ Пополнить", "⬇️ Вывести")
    kb.add("👨‍💻 Поддержка")
    if uid in get_admins() or uid == MAIN_ADMIN:
        kb.add("⚙️ Admin")
    return kb

def amount_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=4)
    kb.add("35", "50", "150", "200")
    kb.add("500", "1000", "2000", "5000")
    kb.add("10000", "50000")
    kb.add("⬅️ Отмена")
    return kb

def back_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("⬅️ Отмена")
    return kb

def admin_menu():
    active = is_bot_active()
    auto = is_auto_approve()
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    kb.add("📋 Заявки", "📊 Статистика")
    kb.add("🖼 Загрузить QR")
    kb.add("🔴 ВЫКЛ" if active else "🟢 ВКЛ")
    kb.add("✅ Авто ВКЛ" if auto else "❌ Авто ВЫКЛ")
    kb.add("🔙 Главное меню")
    return kb

def cancel_timer(uid):
    if uid in temp_data:
        del temp_data[uid]
    if uid in payment_timers:
        del payment_timers[uid]
    try:
        bot.send_message(uid, f"{CLOCK} <b>Время вышло. Заявка отменена.</b>", parse_mode="HTML")
    except:
        pass# ==========================================
# СТАРТ
# ==========================================
@bot.message_handler(commands=['start'])
def start(msg):
    try:
        delete_msg(msg.chat.id, msg.message_id)
    except:
        pass

    if not is_bot_active() and msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        bot.send_message(msg.chat.id, f"{OFF} <b>Бот временно отключён.</b>", parse_mode="HTML")
        return

    add_user(msg.chat.id)
    name = msg.from_user.first_name or "друг"

    text = f"""{ROCKET} <b>Добро пожаловать, {safe(name)}!</b>

{LIGHT} <b>Быстрые операции:</b>
• Мгновенное пополнение счёта
• Надёжный вывод средств

{SUPPORT_E} Круглосуточная поддержка:
{SUPPORT}

{CHECK} Ваши транзакции защищены!
Начните управлять своими финансами с нами уже сегодня!"""

    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=main_menu(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["⬅️ Отмена", "🔙 Главное меню"])
def cancel(msg):
    start(msg)

@bot.message_handler(func=lambda m: m.text == "👨‍💻 Поддержка")
def support(msg):
    bot.send_message(msg.chat.id, f"{SUPPORT_E} <b>Поддержка:</b> {SUPPORT}", parse_mode="HTML")

# ==========================================
# ПОПОЛНЕНИЕ
# ==========================================
@bot.message_handler(func=lambda m: m.text == "⬆️ Пополнить")
def deposit(msg):
    if not is_bot_active() and msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        bot.send_message(msg.chat.id, f"{OFF} Бот на тех. обслуживании.", parse_mode="HTML")
        return

    temp_data[msg.chat.id] = {}
    bot.send_message(msg.chat.id, f"{INFO} <b>Отправьте ваш ID 1xBet:</b>", parse_mode="HTML", reply_markup=back_kb())
    bot.register_next_step_handler(msg, get_id)

def get_id(msg):
    if msg.text == "⬅️ Отмена":
        start(msg)
        return

    delete_msg(msg.chat.id, msg.message_id)
    temp_data[msg.chat.id]["account_id"] = msg.text.strip()

    text = f"""{MONEY} <b>Отправьте сумму пополнения или выберите вариант ниже:</b>

Минимальный: 35с
Максимально: 100000с"""

    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=amount_kb())
    bot.register_next_step_handler(msg, get_amount)

def get_amount(msg):
    if msg.text == "⬅️ Отмена":
        start(msg)
        return

    delete_msg(msg.chat.id, msg.message_id)

    try:
        amount = float(msg.text.replace(",", ".").replace(" ", ""))
    except:
        bot.send_message(msg.chat.id, f"{CROSS} Введите число!", parse_mode="HTML", reply_markup=amount_kb())
        bot.register_next_step_handler(msg, get_amount)
        return

    if amount < 35 or amount > 100000:
        bot.send_message(msg.chat.id, f"{CROSS} Сумма от 35 до 100000!", parse_mode="HTML", reply_markup=amount_kb())
        bot.register_next_step_handler(msg, get_amount)
        return

    uid = msg.chat.id
    temp_data[uid]["amount"] = amount
    account_id = temp_data[uid]["account_id"]

    qr = get_last_qr()
    if qr:
        try:
            bot.send_photo(uid, qr, caption=f"{WALLET} <b>ОПЛАТИТЕ {amount} сом</b>", parse_mode="HTML")
        except:
            bot.send_message(uid, f"{QR_E} QR пока не загружен")
    else:
        bot.send_message(uid, f"{QR_E} QR пока не загружен")

    text = f"""{LINK} <b>Прикрепите скриншот чека</b>

Аккаунт ID: <code>{safe(account_id)}</code>
Сумма: {amount} KGS {CHECK}

{CROSS} Оплатите и отправьте скриншот чека в течение 5 минут, чек должен быть в формате картинки

{INFO} Нажми оплатить чтобы перейти для оплаты в приложение"""

    bot.send_message(uid, text, parse_mode="HTML", reply_markup=back_kb())

    if uid in payment_timers:
        payment_timers[uid].cancel()
    t = threading.Timer(300, cancel_timer, args=[uid])
    payment_timers[uid] = t
    t.start()

    bot.register_next_step_handler(msg, get_check)

def get_check(msg):
    uid = msg.chat.id
    if msg.text == "⬅️ Отмена":
        if uid in payment_timers:
            payment_timers[uid].cancel()
        start(msg)
        return

    photo_id = None
    if msg.photo:
        photo_id = msg.photo[-1].file_id
    elif msg.document:
        photo_id = msg.document.file_id
    else:
        bot.send_message(uid, f"{CROSS} Пришлите фото чека!", parse_mode="HTML", reply_markup=back_kb())
        bot.register_next_step_handler(msg, get_check)
        return

    if uid in payment_timers:
        payment_timers[uid].cancel()

    account_id = temp_data.get(uid, {}).get("account_id")
    amount = temp_data.get(uid, {}).get("amount")

    if not account_id or not amount:
        bot.send_message(uid, f"{CROSS} Ошибка. Начните заново.")
        start(msg)
        return

    dep_id = add_deposit(uid, amount, account_id, photo_id)

    if is_auto_approve():
        with sqlite3.connect("spinpay.db", timeout=10) as conn:
            c = conn.cursor()
            c.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
            conn.commit()

        bot.send_message(uid,
            f"{CHECK} <b>Заявка автоматически одобрена!</b>\n\n"
            f"Сумма: {amount} сом\nID: {safe(account_id)}",
            parse_mode="HTML", reply_markup=main_menu(uid))

        for admin in get_admins():
            try:
                bot.send_message(admin, f"{CHECK} Авто-одобрена #{dep_id}\n👤 {uid}\n💰 {amount} сом")
            except:
                pass
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        caption = f"{LIGHT} <b>ЗАЯВКА #{dep_id}</b>\n\n👤 {uid}\n💰 {amount} сом\n🆔 {safe(account_id)}"

        for admin in get_admins():
            try:
                bot.send_photo(admin, photo_id, caption=caption, parse_mode="HTML", reply_markup=markup)
            except:
                bot.send_message(admin, caption, parse_mode="HTML", reply_markup=markup)

        bot.send_message(uid, f"{CHECK} <b>Заявка принята!</b>\n{CLOCK} Ожидайте обработки.", parse_mode="HTML", reply_markup=main_menu(uid))

    if uid in temp_data:
        del temp_data[uid]

# ==========================================
# ВЫВОД
# ==========================================
@bot.message_handler(func=lambda m: m.text == "⬇️ Вывести")
def withdraw(msg):
    bot.send_message(msg.chat.id, f"{WALLET} <b>Вывод средств</b>\n\nФункция в разработке.", parse_mode="HTML")

# ==========================================
# АДМИНКА
# ==========================================
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin")
def admin_panel(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    bot.send_message(msg.chat.id, f"{ADMIN_E} <b>Админ-панель {BOT_NAME}</b>", parse_mode="HTML", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    users, pending, total = get_stats()
    bot.send_message(msg.chat.id,
        f"{INFO} <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n"
        f"💰 Сумма: <b>{total:,.2f} сом</b>",
        parse_mode="HTML", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Заявки")
def pending(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return

    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT id, user_id, amount, account_id, photo_id FROM deposits WHERE status='pending' ORDER BY id DESC LIMIT 10")
        rows = c.fetchall()

    if not rows:
        bot.send_message(msg.chat.id, "Нет ожидающих заявок", reply_markup=admin_menu())
        return

    for dep_id, user_id, amount, account_id, photo_id in rows:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        caption = f"{LIGHT} <b>Заявка #{dep_id}</b>\n\n👤 {user_id}\n💰 {amount} сом\n🆔 {safe(account_id)}"
        try:
            bot.send_photo(msg.chat.id, photo_id, caption=caption, parse_mode="HTML", reply_markup=markup)
        except:
            bot.send_message(msg.chat.id, caption, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🖼 Загрузить QR")
def change_qr(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    bot.send_message(msg.chat.id, "Отправьте фото QR-кода:", reply_markup=back_kb())
    bot.register_next_step_handler(msg, save_qr)

def save_qr(msg):
    if msg.text == "⬅️ Отмена":
        start(msg)
        return
    if not msg.photo:
        bot.send_message(msg.chat.id, "Пришлите фото!", reply_markup=back_kb())
        bot.register_next_step_handler(msg, save_qr)
        return

    file_id = msg.photo[-1].file_id
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO qr_codes (file_id, date) VALUES (?, ?)",
                  (file_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()

    bot.send_message(msg.chat.id, f"{CHECK} QR успешно загружен!", parse_mode="HTML", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text in ["🔴 ВЫКЛ", "🟢 ВКЛ"])
def toggle_bot(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    current = is_bot_active()
    set_bot_active(not current)
    status = "ВКЛЮЧЕН ✅" if not current else "ВЫКЛЮЧЕН 🔴"
    bot.send_message(msg.chat.id, f"Бот теперь: <b>{status}</b>", parse_mode="HTML", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text in ["✅ Авто ВКЛ", "❌ Авто ВЫКЛ"])
def toggle_auto(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    current = is_auto_approve()
    set_auto_approve(not current)
    status = "ВКЛЮЧЕНО ✅" if not current else "ВЫКЛЮЧЕНО ❌"
    bot.send_message(msg.chat.id, f"Авто-одобрение: <b>{status}</b>", parse_mode="HTML", reply_markup=admin_menu())

# ==========================================
# ОДОБРЕНИЕ / ОТКЛОНЕНИЕ
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("reject_"))
def process(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id not in get_admins() and call.from_user.id != MAIN_ADMIN:
        return

    action, dep_id = call.data.split("_")
    dep_id = int(dep_id)

    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount, account_id, status FROM deposits WHERE id=?", (dep_id,))
        row = c.fetchone()
        if not row:
            bot.send_message(call.message.chat.id, "Заявка не найдена")
            return

        user_id, amount, account_id, status = row
        if status != "pending":
            bot.send_message(call.message.chat.id, "Уже обработана")
            return

        if action == "approve":
            c.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
            conn.commit()
            try:
                bot.send_message(user_id, f"{CHECK} <b>Заявка #{dep_id} одобрена!</b>\nСумма: {amount} сом", parse_mode="HTML")
            except:
                pass
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                         caption=call.message.caption + "\n\n✅ ОДОБРЕНО")
            except:
                pass
        else:
            c.execute("UPDATE deposits SET status='rejected' WHERE id=?", (dep_id,))
            conn.commit()
            try:
                bot.send_message(user_id, f"{CROSS} <b>Заявка #{dep_id} отклонена.</b>", parse_mode="HTML")
            except:
                pass
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                         caption=call.message.caption + "\n\n❌ ОТКЛОНЕНО")
            except:
                pass

print(f"{BOT_NAME} запущен...")
bot.infinity_polling(none_stop=True)
