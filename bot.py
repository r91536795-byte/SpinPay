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
SUPPORT = "https://t.me/help1som"
BOT_NAME = "SpinPay"

bot = telebot.TeleBot(TOKEN)
temp_data = {}
payment_timers = {}

def safe(text):
    return html.escape(str(text)) if text else ""

def init_db():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("PRAGMA journal_mode=WAL;")
        c.execute("""CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY,
                        join_date TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)""")
        c.execute("""CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS deposits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER,
                        amount REAL,
                        account_id TEXT,
                        photo_id TEXT,
                        status TEXT,
                        date TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS qr_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        file_id TEXT,
                        date TEXT)""")
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

def set_bot_active(val):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_active', ?)", (str(val),))
        conn.commit()

def is_auto_approve():
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("SELECT value FROM settings WHERE key='auto_approve'")
        row = c.fetchone()
        return row and row[0] == "True"

def set_auto_approve(val):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_approve', ?)", (str(val),))
        conn.commit()

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
        c.execute("SELECT 1 FROM users WHERE chat_id=?", (chat_id,))
        if not c.fetchone():
            c.execute("INSERT INTO users (chat_id, join_date) VALUES (?, ?)",
                      (chat_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
            conn.commit()

def add_deposit(user_id, amount, account_id, photo_id):
    with sqlite3.connect("spinpay.db", timeout=10) as conn:
        c = conn.cursor()
        c.execute("""INSERT INTO deposits (user_id, amount, account_id, photo_id, status, date)
                     VALUES (?, ?, ?, ?, 'pending', ?)""",
                  (user_id, amount, account_id, photo_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
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

def main_menu(user_id):
    kb = types.InlineKeyboardMarkup(row_width=2)
    kb.add(
        types.InlineKeyboardButton("+ Пополнить", callback_data="deposit"),
        types.InlineKeyboardButton("Вывести", callback_data="withdraw")
    )
    kb.add(types.InlineKeyboardButton("Поддержка", callback_data="support"))
    if user_id in get_admins() or user_id == MAIN_ADMIN:
        kb.add(types.InlineKeyboardButton("⚙️ Admin", callback_data="admin"))
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

def back_kb():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("🔙 Назад")
    return kb

def cancel_timer(user_id):
    if user_id in temp_data:
        del temp_data[user_id]
    if user_id in payment_timers:
        del payment_timers[user_id]
    try:
        bot.send_message(user_id, "⏳ <b>Время вышло. Заявка отменена.</b>", parse_mode="HTML")
    except:
        pass# ==========================================
# СТАРТ
# ==========================================
@bot.message_handler(commands=['start'])
def start(msg):
    if not is_bot_active() and msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        bot.send_message(msg.chat.id, "🔴 <b>Бот временно отключён.</b>", parse_mode="HTML")
        return

    add_user(msg.chat.id)

    text = f"""🚀 <b>Добро пожаловать в {BOT_NAME}!</b>

💼 Здесь вы можете:
• Пополнить баланс
• Вывести средства

⚡️ Все операции — быстро и удобно.
Поддержка: {SUPPORT}"""

    bot.send_message(msg.chat.id, text, parse_mode="HTML", reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(msg.chat.id, "Выберите действие:", reply_markup=main_menu(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["🔙 Назад", "🔙 Главное меню"])
def back(msg):
    start(msg)

# ==========================================
# INLINE МЕНЮ
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data in ["deposit", "withdraw", "support", "admin"])
def menu_handler(call):
    bot.answer_callback_query(call.id)
    uid = call.from_user.id

    if call.data == "deposit":
        if not is_bot_active() and uid not in get_admins() and uid != MAIN_ADMIN:
            bot.send_message(call.message.chat.id, "🔴 Бот на тех. обслуживании.")
            return
        temp_data[call.message.chat.id] = {}
        bot.send_message(call.message.chat.id, "Введите ваш ID аккаунта 1xBet:", reply_markup=back_kb())
        bot.register_next_step_handler(call.message, get_account_id)

    elif call.data == "withdraw":
        bot.send_message(call.message.chat.id, "📤 <b>Вывод средств</b>\n\nФункция в разработке.", parse_mode="HTML")

    elif call.data == "support":
        bot.send_message(call.message.chat.id, f"👨‍💻 Поддержка: {SUPPORT}")

    elif call.data == "admin":
        if uid in get_admins() or uid == MAIN_ADMIN:
            bot.send_message(call.message.chat.id, f"⚙️ <b>Админ-панель {BOT_NAME}</b>", parse_mode="HTML", reply_markup=admin_menu())

# ==========================================
# ПОПОЛНЕНИЕ
# ==========================================
def get_account_id(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return

    temp_data[msg.chat.id]["account_id"] = f"1xBet | {msg.text.strip()}"
    bot.send_message(msg.chat.id, "Введите сумму (от 100 до 100000 сом):", reply_markup=back_kb())
    bot.register_next_step_handler(msg, get_amount)

def get_amount(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return
    try:
        amount = float(msg.text.replace(",", "."))
    except:
        bot.send_message(msg.chat.id, "❌ Введите число!", reply_markup=back_kb())
        bot.register_next_step_handler(msg, get_amount)
        return

    if amount < 100 or amount > 100000:
        bot.send_message(msg.chat.id, "❌ Сумма от 100 до 100000!", reply_markup=back_kb())
        bot.register_next_step_handler(msg, get_amount)
        return

    user_id = msg.chat.id
    temp_data[user_id]["amount"] = amount
    account_id = temp_data[user_id]["account_id"]

    # QR
    qr = get_last_qr()
    if qr:
        try:
            bot.send_photo(user_id, qr, caption=f"💰 ОПЛАТИТЕ {amount:,.2f} сом\n⏳ 5 минут")
        except:
            bot.send_message(user_id, "QR пока не загружен")
    else:
        bot.send_message(user_id, "QR пока не загружен")

    bot.send_message(user_id,
        f"📎 Пришлите скриншот чека\n\n"
        f"🆔 Счёт: <code>{safe(account_id)}</code>\n"
        f"💰 Сумма: {amount:,.2f} сом\n\n"
        f"⏳ У вас 5 минут!",
        parse_mode="HTML", reply_markup=back_kb())

    if user_id in payment_timers:
        payment_timers[user_id].cancel()
    t = threading.Timer(300, cancel_timer, args=[user_id])
    payment_timers[user_id] = t
    t.start()

    bot.register_next_step_handler(msg, get_check)

def get_check(msg):
    user_id = msg.chat.id
    if msg.text == "🔙 Назад":
        if user_id in payment_timers:
            payment_timers[user_id].cancel()
        start(msg)
        return

    photo_id = None
    if msg.photo:
        photo_id = msg.photo[-1].file_id
    elif msg.document:
        photo_id = msg.document.file_id
    else:
        bot.send_message(user_id, "❌ Пришлите фото!", reply_markup=back_kb())
        bot.register_next_step_handler(msg, get_check)
        return

    if user_id in payment_timers:
        payment_timers[user_id].cancel()

    account_id = temp_data.get(user_id, {}).get("account_id")
    amount = temp_data.get(user_id, {}).get("amount")

    if not account_id or not amount:
        bot.send_message(user_id, "Ошибка. Начните заново.")
        start(msg)
        return

    dep_id = add_deposit(user_id, amount, account_id, photo_id)

    if is_auto_approve():
        with sqlite3.connect("spinpay.db", timeout=10) as conn:
            c = conn.cursor()
            c.execute("UPDATE deposits SET status='approved' WHERE id=?", (dep_id,))
            conn.commit()

        bot.send_message(user_id,
            f"✅ <b>Заявка автоматически одобрена!</b>\n\n"
            f"Сумма: {amount:,.2f} сом\n"
            f"ID: {safe(account_id)}",
            parse_mode="HTML", reply_markup=main_menu(user_id))

        for admin in get_admins():
            try:
                bot.send_message(admin, f"✅ Авто-одобрена #{dep_id}\n👤 {user_id}\n💰 {amount:,.2f} сом")
            except:
                pass
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        caption = f"⚡️ <b>ЗАЯВКА #{dep_id}</b>\n\n👤 {user_id}\n💰 {amount:,.2f} сом\n🆔 {safe(account_id)}"

        for admin in get_admins():
            try:
                bot.send_photo(admin, photo_id, caption=caption, parse_mode="HTML", reply_markup=markup)
            except:
                bot.send_message(admin, caption, parse_mode="HTML", reply_markup=markup)

        bot.send_message(user_id, "✅ Заявка принята! Ожидайте обработки.", reply_markup=main_menu(user_id))

    if user_id in temp_data:
        del temp_data[user_id]

# ==========================================
# АДМИНКА
# ==========================================
@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats_handler(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    users, pending, total = get_stats()
    bot.send_message(msg.chat.id,
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"⏳ Ожидают: <b>{pending}</b>\n"
        f"💰 Сумма: <b>{total:,.2f} сом</b>",
        parse_mode="HTML", reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Заявки")
def pending_handler(msg):
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
        caption = f"⚡️ <b>Заявка #{dep_id}</b>\n\n👤 {user_id}\n💰 {amount:,.2f} сом\n🆔 {safe(account_id)}"
        try:
            bot.send_photo(msg.chat.id, photo_id, caption=caption, parse_mode="HTML", reply_markup=markup)
        except:
            bot.send_message(msg.chat.id, caption, parse_mode="HTML", reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🖼 Загрузить QR")
def qr_handler(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    bot.send_message(msg.chat.id, "Отправьте фото QR-кода:", reply_markup=back_kb())
    bot.register_next_step_handler(msg, save_qr)

def save_qr(msg):
    if msg.text == "🔙 Назад":
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

    bot.send_message(msg.chat.id, "✅ QR успешно загружен!", reply_markup=admin_menu())

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
                bot.send_message(user_id, f"✅ Заявка #{dep_id} одобрена!\nСумма: {amount:,.2f} сом")
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
                bot.send_message(user_id, f"❌ Заявка #{dep_id} отклонена.")
            except:
                pass
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                         caption=call.message.caption + "\n\n❌ ОТКЛОНЕНО")
            except:
                pass

# ==========================================
# ЗАПУСК
# ==========================================
print(f"{BOT_NAME} запущен...")
bot.infinity_polling(none_stop=True)
