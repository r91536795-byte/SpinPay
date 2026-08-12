import os
import sqlite3
import time
import threading
import html
from datetime import datetime
import telebot
from telebot import types

# ====================== НАСТРОЙКИ ======================
TOKEN = os.environ.get("BOT_TOKEN")
MAIN_ADMIN = int(os.environ.get("ADMIN_ID", "8349263362"))
SUPPORT = os.environ.get("SUPPORT", "@OperatorSpinPay")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "SpinPay_bot")

if not TOKEN:
    raise ValueError("Не указан BOT_TOKEN")

bot = telebot.TeleBot(TOKEN)
temp_data = {}
payment_timers = {}

# ====================== PREMIUM ЭМОДЗИ ======================
def e(emoji_id, fallback="✨"):
    return f'<tg-emoji emoji-id="{emoji_id}">{fallback}</tg-emoji>'

DOWNLOAD  = "5443127283898405358"
UPLOAD    = "5445355530111437729"
SHIELD1   = "5251203410396458957"
PLANE     = "5201691993775818138"
MONEY     = "5197434882321567830"
BAG       = "5294167145079395967"
LIGHTNING = "5456140674028019486"
CHECK     = "5206607081334906820"
BALANCE   = "5202187800505492618"
COIN      = "5264713049637409446"
ARROW     = "5429651785352501917"

# ====================== БАЗА ДАННЫХ ======================
def safe_html(text):
    return html.escape(str(text)) if text else ""

def init_db():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("""CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY,
                        join_date TEXT,
                        balance REAL DEFAULT 0.0)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS deposits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        amount REAL,
                        account_id TEXT,
                        photo_id TEXT,
                        status TEXT,
                        date TEXT,
                        timestamp INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS qr_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_id TEXT,
                        date TEXT)""")
        c.execute("INSERT OR IGNORE INTO admins (chat_id) VALUES (?)", (MAIN_ADMIN,))
        c.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('bot_active', 'True')")
        conn.commit()

def is_bot_active():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key = 'bot_active'")
        row = c.fetchone()
        return True if row is None else row[0] == "True"

def get_admins():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT chat_id FROM admins")
        admins = [r[0] for r in c.fetchall()]
        if MAIN_ADMIN not in admins:
            admins.append(MAIN_ADMIN)
        return admins

def add_user(chat_id):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT chat_id FROM users WHERE chat_id = ?", (chat_id,))
        if not c.fetchone():
            c.execute("INSERT INTO users (chat_id, join_date) VALUES (?, ?)",
                      (chat_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
            conn.commit()

def add_deposit(user_id, amount, account_id, photo_id):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        now = datetime.now()
        c.execute("""INSERT INTO deposits
                     (user_id, amount, account_id, photo_id, status, date, timestamp)
                     VALUES (?, ?, ?, ?, ?, ?, ?)""",
                  (user_id, amount, account_id, photo_id, "pending",
                   now.strftime("%d.%m.%Y %H:%M:%S"), int(time.time())))
        dep_id = c.lastrowid
        conn.commit()
        return dep_id

def get_last_qr():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT file_id FROM qr_codes ORDER BY id DESC LIMIT 1")
        row = c.fetchone()
        return row[0] if row else None

init_db()

# ====================== МЕНЮ ======================
def main_menu(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("Пополнить", callback_data="menu_deposit", icon_custom_emoji_id=BALANCE),
        types.InlineKeyboardButton("Вывести", callback_data="menu_withdraw", icon_custom_emoji_id=UPLOAD)
    )
    markup.add(
        types.InlineKeyboardButton("Поддержка", callback_data="menu_support", icon_custom_emoji_id=SHIELD1)
    )
    if user_id in get_admins() or user_id == MAIN_ADMIN:
        markup.add(types.InlineKeyboardButton("Админ", callback_data="menu_admin", icon_custom_emoji_id=BAG))
    return markup

def platform_markup(prefix):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("1xBet", callback_data=f"{prefix}_1xbet"),
        types.InlineKeyboardButton("Melbet", callback_data=f"{prefix}_melbet")
    )
    markup.add(types.InlineKeyboardButton("« Назад", callback_data="back_to_main", icon_custom_emoji_id=ARROW))
    return markup

def back_menu():
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("« Назад", callback_data="back_to_main", icon_custom_emoji_id=ARROW))
    return markup

def admin_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📋 Заявки", callback_data="admin_deposits"),
        types.InlineKeyboardButton("📊 Статистика", callback_data="admin_stats")
    )
    markup.add(
        types.InlineKeyboardButton("🖼 Загрузить QR", callback_data="admin_qr"),
        types.InlineKeyboardButton("🔄 Вкл/Выкл", callback_data="admin_toggle")
    )
    markup.add(types.InlineKeyboardButton("« Назад", callback_data="back_to_main", icon_custom_emoji_id=ARROW))
    return markup# ====================== СТАРТ ======================
@bot.message_handler(commands=["start"])
def start(msg):
    try:
        bot.delete_message(msg.chat.id, msg.message_id)
    except:
        pass

    if not is_bot_active() and msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        bot.send_message(msg.chat.id, f"{e(SHIELD1)} <b>Бот временно отключён.</b>", parse_mode="HTML")
        return

    add_user(msg.chat.id)

    text = f"""{e(CHECK)} <b>Добро пожаловать в SpinPay!</b>

{e(BAG)} Здесь вы можете:
 • Пополнить баланс {e(MONEY)}
 • Вывести средства {e(UPLOAD)}

{e(LIGHTNING)} Все операции — мгновенно, без ожидания!
{e(ARROW)} Удобно. Надёжно. 24/7.

Служба поддержки: {SUPPORT}"""

    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(msg.chat.id, f"{e(ARROW)} Выберите действие:", parse_mode="HTML", reply_markup=main_menu(msg.from_user.id))

# ====================== НАЗАД ======================
@bot.callback_query_handler(func=lambda call: call.data == "back_to_main")
def back_to_main(call):
    bot.answer_callback_query(call.id)
    try:
        bot.delete_message(call.message.chat.id, call.message.message_id)
    except:
        pass

    uid = call.from_user.id
    text = f"""{e(CHECK)} <b>Добро пожаловать в SpinPay!</b>

{e(BAG)} Здесь вы можете:
 • Пополнить баланс {e(MONEY)}
 • Вывести средства {e(UPLOAD)}

{e(LIGHTNING)} Все операции — мгновенно, без ожидания!
{e(ARROW)} Удобно. Надёжно. 24/7.

Служба поддержки: {SUPPORT}"""

    bot.send_message(call.message.chat.id, text, parse_mode="HTML")
    bot.send_message(call.message.chat.id, f"{e(ARROW)} Выберите действие:", parse_mode="HTML", reply_markup=main_menu(uid))

# ====================== ГЛАВНОЕ МЕНЮ ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("menu_"))
def menu_handler(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id

    if call.data == "menu_deposit":
        bot.send_message(call.message.chat.id,
            f"{e(BALANCE)} <b>Выберите платформу для пополнения:</b>",
            parse_mode="HTML", reply_markup=platform_markup("dep"))

    elif call.data == "menu_withdraw":
        bot.send_message(call.message.chat.id,
            f"{e(UPLOAD)} <b>Выберите платформу для вывода:</b>",
            parse_mode="HTML", reply_markup=platform_markup("w"))

    elif call.data == "menu_support":
        bot.send_message(call.message.chat.id, f"{e(SHIELD1)} Поддержка: {SUPPORT}", parse_mode="HTML", reply_markup=back_menu())

    elif call.data == "menu_admin":
        if uid in get_admins() or uid == MAIN_ADMIN:
            bot.send_message(call.message.chat.id, f"{e(BAG)} <b>Админ-панель SpinPay</b>", parse_mode="HTML", reply_markup=admin_menu())

# ====================== АДМИНКА ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def admin_handler(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id

    if uid not in get_admins() and uid != MAIN_ADMIN:
        return

    if call.data == "admin_stats":
        with sqlite3.connect("spinpay.db", timeout=10) as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            users = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM deposits WHERE status='pending'")
            pending = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM deposits WHERE status='approved'")
            approved = c.fetchone()[0]
            c.execute("SELECT SUM(amount) FROM deposits WHERE status='approved'")
            total = c.fetchone()[0] or 0

        text = f"""{e(BAG)} <b>Статистика</b>

👥 Пользователей: <b>{users}</b>
⏳ Ожидают: <b>{pending}</b>
✅ Одобрено: <b>{approved}</b>
💰 Сумма: <b>{total:,.2f} сом</b>"""
        bot.send_message(call.message.chat.id, text, parse_mode="HTML", reply_markup=admin_menu())

    elif call.data == "admin_deposits":
        with sqlite3.connect("spinpay.db", timeout=10) as conn:
            c = conn.cursor()
            c.execute("SELECT id, user_id, amount, account_id, photo_id FROM deposits WHERE status='pending' ORDER BY id DESC LIMIT 10")
            rows = c.fetchall()

        if not rows:
            bot.send_message(call.message.chat.id, "Нет ожидающих заявок", reply_markup=admin_menu())
            return

        for dep_id, user_id, amount, account_id, photo_id in rows:
            markup = types.InlineKeyboardMarkup()
            markup.add(
                types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
                types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
            )
            try:
                bot.send_photo(call.message.chat.id, photo_id,
                    caption=f"{e(BALANCE)} <b>Заявка #{dep_id}</b>\n\n👤 {user_id}\n💰 {amount:,.2f} сом\n🆔 {account_id}",
                    parse_mode="HTML", reply_markup=markup)
            except:
                bot.send_message(call.message.chat.id,
                    f"Заявка #{dep_id}\n👤 {user_id}\n💰 {amount} сом\n🆔 {account_id}", reply_markup=markup)

    elif call.data == "admin_qr":
        bot.send_message(call.message.chat.id, "Отправьте фото QR-кода:", reply_markup=back_menu())
        bot.register_next_step_handler(call.message, save_qr_admin)

    elif call.data == "admin_toggle":
        with sqlite3.connect("spinpay.db", timeout=10) as conn:
            c = conn.cursor()
            c.execute("SELECT value FROM settings WHERE key='bot_active'")
            row = c.fetchone()
            current = row[0] if row else "True"
            new_status = "False" if current == "True" else "True"
            c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_active', ?)", (new_status,))
            conn.commit()

        status = "ВКЛЮЧЕН ✅" if new_status == "True" else "ВЫКЛЮЧЕН 🔴"
        bot.send_message(call.message.chat.id, f"Бот теперь: <b>{status}</b>", parse_mode="HTML", reply_markup=admin_menu())

def save_qr_admin(msg):
    if not msg.photo:
        bot.send_message(msg.chat.id, "Пришлите именно фото QR", reply_markup=back_menu())
        bot.register_next_step_handler(msg, save_qr_admin)
        return

    file_id = msg.photo[-1].file_id
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("INSERT INTO qr_codes (file_id, date) VALUES (?, ?)",
                  (file_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()

    bot.send_message(msg.chat.id, f"{e(CHECK)} QR успешно загружен!", parse_mode="HTML", reply_markup=admin_menu())

# ====================== ПОПОЛНЕНИЕ ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("dep_"))
def deposit_platform(call):
    bot.answer_callback_query(call.id)
    platform = "1xBet" if "1xbet" in call.data else "Melbet"
    temp_data[call.message.chat.id] = {"platform": platform}

    bot.send_message(call.message.chat.id,
        f"{e(BAG)} <b>Отправьте ID для пополнения {platform}</b>\n\nПример: <code>628995333</code>",
        parse_mode="HTML", reply_markup=back_menu())
    bot.register_next_step_handler(call.message, get_account_id)

def get_account_id(msg):
    account_id = msg.text.strip() if msg.text else ""
    if not account_id.isdigit() or len(account_id) < 5:
        bot.send_message(msg.chat.id, f"{e(SHIELD1)} Введите корректный ID (только цифры):", parse_mode="HTML", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_account_id)
        return

    temp_data[msg.chat.id]["account_id"] = account_id
    platform = temp_data[msg.chat.id]["platform"]

    bot.send_message(msg.chat.id,
        f"{e(MONEY)} <b>Введите сумму пополнения {platform}</b>\nID: <code>{account_id}</code>\n\nОт 100 до 100 000 сом:",
        parse_mode="HTML", reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_amount)

def get_amount(msg):
    try:
        amount = float(msg.text.replace(",", "."))
    except:
        bot.send_message(msg.chat.id, f"{e(SHIELD1)} Введите число!", parse_mode="HTML", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return

    if amount < 100 or amount > 100000:
        bot.send_message(msg.chat.id, f"{e(SHIELD1)} Сумма от 100 до 100 000!", parse_mode="HTML", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return

    user_id = msg.chat.id
    temp_data[user_id]["amount"] = amount
    account_id = temp_data[user_id]["account_id"]

    qr = get_last_qr()
    if qr:
        try:
            bot.send_photo(user_id, qr, caption=f"{e(DOWNLOAD)} <b>Оплатите {amount:,.2f} сом</b>\n⏳ 5 минут", parse_mode="HTML")
        except:
            bot.send_message(user_id, f"{e(SHIELD1)} Ошибка QR")
    else:
        bot.send_message(user_id, f"{e(SHIELD1)} QR пока не загружен (админ должен загрузить)")

    bot.send_message(user_id,
        f"{e(BAG)} <b>Пришлите скриншот чека</b>\n\nID: <code>{account_id}</code>\nСумма: {amount:,.2f} сом",
        parse_mode="HTML", reply_markup=back_menu())

    if user_id in payment_timers:
        payment_timers[user_id].cancel()
    timer = threading.Timer(300, cancel_payment, args=[user_id])
    payment_timers[user_id] = timer
    timer.start()

    bot.register_next_step_handler(msg, get_check)

def cancel_payment(user_id):
    if user_id in temp_data:
        del temp_data[user_id]
    if user_id in payment_timers:
        del payment_timers[user_id]
    try:
        bot.send_message(user_id, f"{e(SHIELD1)} <b>Время вышло. Заявка отменена.</b>", parse_mode="HTML")
    except:
        pass

def get_check(msg):
    user_id = msg.chat.id

    if not msg.photo:
        bot.send_message(user_id, f"{e(SHIELD1)} Пришлите фото чека!", parse_mode="HTML", reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_check)
        return

    if user_id in payment_timers:
        payment_timers[user_id].cancel()

    account_id = temp_data.get(user_id, {}).get("account_id")
    amount = temp_data.get(user_id, {}).get("amount")
    photo_id = msg.photo[-1].file_id

    if not account_id or not amount:
        bot.send_message(user_id, f"{e(SHIELD1)} Ошибка, начните заново")
        return

    dep_id = add_deposit(user_id, amount, account_id, photo_id)

    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
        types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
    )

    for admin in get_admins():
        try:
            bot.send_photo(admin, photo_id,
                caption=f"{e(BALANCE)} <b>Заявка #{dep_id}</b>\n\n👤 {user_id}\n💰 {amount:,.2f} сом\n🆔 {account_id}",
                parse_mode="HTML", reply_markup=markup)
        except:
            pass

    bot.send_message(user_id,
        f"{e(CHECK)} <b>Заявка принята!</b>\n\nID: {account_id}\nСумма: {amount:,.2f} сом\n\nОжидайте обработки.",
        parse_mode="HTML", reply_markup=main_menu(user_id))

    if user_id in temp_data:
        del temp_data[user_id]

# ====================== ОДОБРЕНИЕ / ОТКЛОНЕНИЕ ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("reject_"))
def process_deposit(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id

    if uid not in get_admins() and uid != MAIN_ADMIN:
        return

    action, dep_id = call.data.split("_")
    dep_id = int(dep_id)

    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT user_id, amount, account_id, status FROM deposits WHERE id = ?", (dep_id,))
        row = c.fetchone()
        if not row:
            bot.send_message(call.message.chat.id, "Заявка не найдена")
            return

        user_id, amount, account_id, status = row
        if status != "pending":
            bot.send_message(call.message.chat.id, "Заявка уже обработана")
            return

        if action == "approve":
            c.execute("UPDATE deposits SET status = 'approved' WHERE id = ?", (dep_id,))
            conn.commit()
            try:
                bot.send_message(user_id, f"{e(CHECK)} <b>Ваша заявка #{dep_id} одобрена!</b>\nСумма: {amount:,.2f} сом\nID: {account_id}", parse_mode="HTML")
            except:
                pass
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                         caption=call.message.caption + "\n\n✅ ОДОБРЕНО", parse_mode="HTML")
            except:
                pass
        else:
            c.execute("UPDATE deposits SET status = 'rejected' WHERE id = ?", (dep_id,))
            conn.commit()
            try:
                bot.send_message(user_id, f"{e(SHIELD1)} <b>Ваша заявка #{dep_id} отклонена.</b>", parse_mode="HTML")
            except:
                pass
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                         caption=call.message.caption + "\n\n❌ ОТКЛОНЕНО", parse_mode="HTML")
            except:
                pass

# ====================== ВЫВОД (заглушка) ======================
@bot.callback_query_handler(func=lambda call: call.data.startswith("w_"))
def withdraw_platform(call):
    bot.answer_callback_query(call.id)
    bot.send_message(call.message.chat.id, f"{e(UPLOAD)} <b>Вывод средств</b>\n\nФункция в разработке.", parse_mode="HTML", reply_markup=back_menu())

# ====================== ЗАПУСК ======================
print("SpinPay бот запущен...")
bot.infinity_polling(none_stop=True)
