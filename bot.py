import os
import sqlite3
import time
import threading
import html
from datetime import datetime
import telebot
from telebot import types

# ==========================================
# НАСТРОЙКИ SPINPAY
# ==========================================
TOKEN = os.environ.get("BOT_TOKEN", "СЮДА_ВСТАВИТЬ_ТОКЕН")
MAIN_ADMIN = 8957913298

SUPPORT = "https://t.me/help1som"
BOT_USERNAME = "SpinPay_bot"
BOT_NAME = "SpinPay"

EMOJI = {
    "star": '<tg-emoji emoji-id="5368324170671202286">⭐️</tg-emoji>',
    "wallet": '<tg-emoji emoji-id="5368582040173041416">👛</tg-emoji>',
    "deposit": '<tg-emoji emoji-id="5368735282433517454">📥</tg-emoji>',
    "withdraw": '<tg-emoji emoji-id="5368685141072699865">📤</tg-emoji>',
    "support": '<tg-emoji emoji-id="5368782333799408226">👨‍💻</tg-emoji>',
    "admin": '<tg-emoji emoji-id="5370836560085140324">⚙️</tg-emoji>',
    "money": '<tg-emoji emoji-id="5368324170671202286">💰</tg-emoji>',
    "fire": '<tg-emoji emoji-id="5368420657531872134">🔥</tg-emoji>',
    "check": '<tg-emoji emoji-id="5368641901145508892">✅</tg-emoji>',
    "cross": '<tg-emoji emoji-id="5368755601831522045">❌</tg-emoji>',
    "clock": '<tg-emoji emoji-id="5368742540911475176">⏳</tg-emoji>',
    "rocket": '<tg-emoji emoji-id="5368415277984674720">🚀</tg-emoji>',
    "lightning": '<tg-emoji emoji-id="5368579480372533038">⚡️</tg-emoji>',
    "link": '<tg-emoji emoji-id="5368600078020664977">🔗</tg-emoji>',
    "stats": '<tg-emoji emoji-id="5368726589370219491">📊</tg-emoji>',
    "qr": '<tg-emoji emoji-id="5368723230722570086">🖼</tg-emoji>',
    "off": '<tg-emoji emoji-id="5368637503082218084">🔴</tg-emoji>',
    "on": '<tg-emoji emoji-id="5368536096337446554">🟢</tg-emoji>',
    "info": '<tg-emoji emoji-id="5370811563224483783">ℹ️</tg-emoji>',
}

bot = telebot.TeleBot(TOKEN)
temp_data = {}
payment_timers = {}

def safe_html(text):
    return html.escape(str(text)) if text else ""

# ==========================================
# БАЗА ДАННЫХ
# ==========================================
def init_db():
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('PRAGMA journal_mode=WAL;')
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        chat_id INTEGER PRIMARY KEY, 
                        join_date TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS admins (chat_id INTEGER PRIMARY KEY)''')
        c.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS deposits (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        user_id INTEGER, 
                        amount REAL, 
                        account_id TEXT, 
                        photo_id TEXT, 
                        status TEXT, 
                        date TEXT, 
                        timestamp INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS qr_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, 
                        file_id TEXT, 
                        date TEXT)''')
        c.execute('INSERT OR IGNORE INTO admins (chat_id) VALUES (?)', (MAIN_ADMIN,))
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("bot_active", "True")')
        c.execute('INSERT OR IGNORE INTO settings (key, value) VALUES ("auto_approve", "False")')
        conn.commit()

def is_bot_active():
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE key = "bot_active"')
        row = c.fetchone()
        return True if row is None else row[0] == 'True'

def set_bot_active(status):
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("bot_active", ?)', (str(status),))
        conn.commit()

def is_auto_approve():
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT value FROM settings WHERE key = "auto_approve"')
        row = c.fetchone()
        return row[0] == "True" if row else False

def set_auto_approve(status):
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO settings (key, value) VALUES ("auto_approve", ?)', (str(status),))
        conn.commit()

def get_admins():
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT chat_id FROM admins')
        admins = [row[0] for row in c.fetchall()]
        if MAIN_ADMIN not in admins:
            admins.append(MAIN_ADMIN)
        return admins

def add_user(chat_id):
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT chat_id FROM users WHERE chat_id = ?', (chat_id,))
        if not c.fetchone():
            c.execute('INSERT INTO users (chat_id, join_date) VALUES (?, ?)', 
                      (chat_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
            conn.commit()

def add_deposit(user_id, amount, account_id, photo_id):
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        now = datetime.now()
        c.execute('''INSERT INTO deposits 
                     (user_id, amount, account_id, photo_id, status, date, timestamp) 
                     VALUES (?, ?, ?, ?, ?, ?, ?)''',
                  (user_id, amount, account_id, photo_id, 'pending', 
                   now.strftime("%d.%m.%Y %H:%M:%S"), int(time.time())))
        dep_id = c.lastrowid
        conn.commit()
        return dep_id

def get_last_qr():
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT file_id FROM qr_codes ORDER BY id DESC LIMIT 1')
        row = c.fetchone()
        return row[0] if row else None

def get_stats():
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        users = c.fetchone()[0]
        c.execute('SELECT COUNT(*) FROM deposits WHERE status="pending"')
        pending = c.fetchone()[0]
        c.execute('SELECT SUM(amount) FROM deposits WHERE status="approved"')
        total = c.fetchone()[0] or 0
        return {'users': users, 'pending': pending, 'total': total}

init_db()

# ==========================================
# МЕНЮ
# ==========================================
def main_menu(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📥 Пополнить", "📤 Вывести")
    markup.add("👨‍💻 Поддержка")
    if user_id in get_admins() or user_id == MAIN_ADMIN:
        markup.add("⚙️ Admin")
    return markup

def admin_menu():
    active = is_bot_active()
    auto = is_auto_approve()
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add("📋 Заявки", "📊 Статистика")
    markup.add("🖼 Изменить QR")
    markup.add("🔴 ВЫКЛ" if active else "🟢 ВКЛ")
    markup.add("✅ Авто-одобрение ВКЛ" if auto else "❌ Авто-одобрение ВЫКЛ")
    markup.add("🔙 Главное меню")
    return markup

def back_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.add("🔙 Назад")
    return markup

def cancel_payment(user_id):
    if user_id in temp_data:
        del temp_data[user_id]
    if user_id in payment_timers:
        del payment_timers[user_id]
    try:
        bot.send_message(user_id, f"{EMOJI['clock']} <b>ВРЕМЯ ОПЛАТЫ ИСТЕКЛО!</b>\n\nЗаявка отменена.", parse_mode='HTML')
    except:
        pass# ==========================================
# СТАРТ
# ==========================================
@bot.message_handler(commands=['start'])
def start(msg):
    if not is_bot_active() and msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        bot.send_message(msg.chat.id, f"{EMOJI['off']} <b>Бот временно отключён.</b>", parse_mode='HTML')
        return

    add_user(msg.chat.id)

    text = f"""{EMOJI['rocket']} <b>Добро пожаловать в {BOT_NAME}!</b>

{EMOJI['wallet']} Здесь вы можете:
 • Пополнить баланс {EMOJI['money']}
 • Вывести средства {EMOJI['withdraw']}

{EMOJI['lightning']} Все операции — мгновенно, без ожидания!
{EMOJI['fire']} Удобно. Надёжно. 24/7.

Служба поддержки: {SUPPORT}"""

    bot.send_message(msg.chat.id, text, parse_mode='HTML', reply_markup=main_menu(msg.from_user.id))

@bot.message_handler(func=lambda m: m.text in ["🔙 Назад", "🔙 Главное меню"])
def back(msg):
    start(msg)

@bot.message_handler(func=lambda m: m.text in ["👨‍💻 Поддержка", "Поддержка"])
def support(msg):
    bot.send_message(msg.chat.id, f"{EMOJI['support']} <b>Помощь:</b> {SUPPORT}", parse_mode='HTML')

# ==========================================
# ПОПОЛНЕНИЕ
# ==========================================
@bot.message_handler(func=lambda m: m.text in ["📥 Пополнить", "Пополнить"])
def deposit(msg):
    if not is_bot_active() and msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        bot.send_message(msg.chat.id, f"{EMOJI['off']} Бот на тех. обслуживании.", parse_mode='HTML')
        return

    temp_data[msg.chat.id] = {"platform": "1xBet"}
    bot.send_message(msg.chat.id, f"{EMOJI['info']} <b>Введите ваш ID аккаунта 1xBet:</b>", parse_mode='HTML', reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_account_id)

def get_account_id(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return

    account_val = f"1xBet | {msg.text.strip()}"
    temp_data[msg.chat.id]["account_id"] = account_val

    bot.send_message(msg.chat.id, f"{EMOJI['money']} <b>Введите сумму (от 100 до 100 000 сом):</b>", parse_mode='HTML', reply_markup=back_menu())
    bot.register_next_step_handler(msg, get_amount)

def get_amount(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return
    try:
        amount = float(msg.text.replace(',', '.'))
    except:
        bot.send_message(msg.chat.id, f"{EMOJI['cross']} Введите число!", parse_mode='HTML', reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return

    if amount < 100 or amount > 100000:
        bot.send_message(msg.chat.id, f"{EMOJI['cross']} Сумма от 100 до 100 000!", parse_mode='HTML', reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_amount)
        return

    user_id = msg.chat.id
    temp_data[user_id]["amount"] = amount
    account_id = temp_data[user_id]["account_id"]

    # Отправка QR
    qr = get_last_qr()
    if qr:
        try:
            bot.send_photo(user_id, qr, caption=f"{EMOJI['wallet']} <b>ОПЛАТИТЕ {amount:,.2f} сом</b>\n{EMOJI['clock']} 5 минут", parse_mode='HTML')
        except:
            bot.send_message(user_id, f"{EMOJI['qr']} QR пока не загружен")
    else:
        bot.send_message(user_id, f"{EMOJI['qr']} QR пока не загружен")

    bot.send_message(user_id,
        f"""{EMOJI['link']} <b>Пришлите скриншот чека</b>

🆔 Счёт: <code>{safe_html(account_id)}</code>
{EMOJI['money']} Сумма: {amount:,.2f} сом

{EMOJI['clock']} У вас 5 минут!""",
        parse_mode='HTML', reply_markup=back_menu())

    if user_id in payment_timers:
        payment_timers[user_id].cancel()
    timer = threading.Timer(300, cancel_payment, args=[user_id])
    payment_timers[user_id] = timer
    timer.start()

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
        bot.send_message(user_id, f"{EMOJI['cross']} Пришлите фото или файл!", parse_mode='HTML', reply_markup=back_menu())
        bot.register_next_step_handler(msg, get_check)
        return

    if user_id in payment_timers:
        payment_timers[user_id].cancel()

    account_id = temp_data.get(user_id, {}).get("account_id")
    amount = temp_data.get(user_id, {}).get("amount")

    if not account_id or not amount:
        bot.send_message(user_id, f"{EMOJI['cross']} Ошибка, начните заново")
        start(msg)
        return

    dep_id = add_deposit(user_id, amount, account_id, photo_id)

    if is_auto_approve():
        with sqlite3.connect('spinpay.db', timeout=10) as conn:
            c = conn.cursor()
            c.execute('UPDATE deposits SET status = "approved" WHERE id = ?', (dep_id,))
            conn.commit()

        bot.send_message(user_id,
            f"""{EMOJI['check']} <b>Заявка автоматически одобрена!</b>

🆔 Счёт: <code>{safe_html(account_id)}</code>
{EMOJI['money']} Сумма: {amount:,.2f} сом

Спасибо, что пользуетесь {BOT_NAME}!""",
            parse_mode='HTML', reply_markup=main_menu(user_id))

        for admin in get_admins():
            try:
                bot.send_message(admin, f"{EMOJI['check']} Авто-одобрена заявка #{dep_id}\n👤 {user_id}\n💰 {amount:,.2f} сом\n🆔 {safe_html(account_id)}")
            except:
                pass
    else:
        markup = types.InlineKeyboardMarkup()
        markup.add(
            types.InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{dep_id}"),
            types.InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{dep_id}")
        )
        caption = f"{EMOJI['lightning']} <b>ЗАЯВКА #{dep_id}</b>\n\n👤 {user_id}\n{EMOJI['money']} {amount:,.2f} сом\n🆔 {safe_html(account_id)}"
        
        for admin in get_admins():
            try:
                bot.send_photo(admin, photo_id, caption=caption, parse_mode='HTML', reply_markup=markup)
            except:
                bot.send_message(admin, caption, parse_mode='HTML', reply_markup=markup)

        bot.send_message(user_id,
            f"{EMOJI['check']} <b>Заявка принята!</b>\n{EMOJI['clock']} Ожидайте обработки.",
            parse_mode='HTML', reply_markup=main_menu(user_id))

    if user_id in temp_data:
        del temp_data[user_id]

# ==========================================
# ВЫВОД
# ==========================================
@bot.message_handler(func=lambda m: m.text in ["📤 Вывести", "Вывести"])
def withdraw(msg):
    bot.send_message(msg.chat.id, f"{EMOJI['withdraw']} <b>Вывод средств</b>\n\nФункция в разработке.", parse_mode='HTML')

# ==========================================
# АДМИНКА
# ==========================================
@bot.message_handler(func=lambda m: m.text == "⚙️ Admin")
def admin_panel(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    bot.send_message(msg.chat.id, f"{EMOJI['admin']} <b>Админ-панель {BOT_NAME}</b>", parse_mode='HTML', reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📊 Статистика")
def stats(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    s = get_stats()
    text = f"""{EMOJI['stats']} <b>Статистика</b>

👥 Пользователей: <b>{s['users']}</b>
⏳ Ожидают: <b>{s['pending']}</b>
💰 Сумма одобренных: <b>{s['total']:,.2f} сом</b>"""
    bot.send_message(msg.chat.id, text, parse_mode='HTML', reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text == "📋 Заявки")
def pending_deposits(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return

    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT id, user_id, amount, account_id, photo_id FROM deposits WHERE status="pending" ORDER BY id DESC LIMIT 10')
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
        caption = f"{EMOJI['lightning']} <b>Заявка #{dep_id}</b>\n\n👤 {user_id}\n{EMOJI['money']} {amount:,.2f} сом\n🆔 {safe_html(account_id)}"
        try:
            bot.send_photo(msg.chat.id, photo_id, caption=caption, parse_mode='HTML', reply_markup=markup)
        except:
            bot.send_message(msg.chat.id, caption, parse_mode='HTML', reply_markup=markup)

@bot.message_handler(func=lambda m: m.text == "🖼 Изменить QR")
def change_qr(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    bot.send_message(msg.chat.id, "Отправьте новое фото QR-кода:", reply_markup=back_menu())
    bot.register_next_step_handler(msg, save_qr)

def save_qr(msg):
    if msg.text == "🔙 Назад":
        start(msg)
        return
    if not msg.photo:
        bot.send_message(msg.chat.id, "Пришлите фото!", reply_markup=back_menu())
        bot.register_next_step_handler(msg, save_qr)
        return

    file_id = msg.photo[-1].file_id
    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('INSERT INTO qr_codes (file_id, date) VALUES (?, ?)', 
                  (file_id, datetime.now().strftime("%d.%m.%Y %H:%M")))
        conn.commit()

    bot.send_message(msg.chat.id, f"{EMOJI['check']} QR успешно обновлён!", parse_mode='HTML', reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text in ["🔴 ВЫКЛ", "🟢 ВКЛ"])
def toggle_bot(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    current = is_bot_active()
    set_bot_active(not current)
    status = "ВКЛЮЧЕН ✅" if not current else "ВЫКЛЮЧЕН 🔴"
    bot.send_message(msg.chat.id, f"Бот теперь: <b>{status}</b>", parse_mode='HTML', reply_markup=admin_menu())

@bot.message_handler(func=lambda m: m.text in ["✅ Авто-одобрение ВКЛ", "❌ Авто-одобрение ВЫКЛ"])
def toggle_auto(msg):
    if msg.from_user.id not in get_admins() and msg.from_user.id != MAIN_ADMIN:
        return
    current = is_auto_approve()
    set_auto_approve(not current)
    status = "ВКЛЮЧЕНО ✅" if not current else "ВЫКЛЮЧЕНО ❌"
    bot.send_message(msg.chat.id, f"Авто-одобрение теперь: <b>{status}</b>", parse_mode='HTML', reply_markup=admin_menu())

# ==========================================
# ОДОБРЕНИЕ / ОТКЛОНЕНИЕ
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith("approve_") or call.data.startswith("reject_"))
def process_deposit(call):
    bot.answer_callback_query(call.id)
    if call.from_user.id not in get_admins() and call.from_user.id != MAIN_ADMIN:
        return

    action, dep_id = call.data.split("_")
    dep_id = int(dep_id)

    with sqlite3.connect('spinpay.db', timeout=10) as conn:
        c = conn.cursor()
        c.execute('SELECT user_id, amount, account_id, status FROM deposits WHERE id = ?', (dep_id,))
        row = c.fetchone()
        if not row:
            bot.send_message(call.message.chat.id, "Заявка не найдена")
            return

        user_id, amount, account_id, status = row
        if status != "pending":
            bot.send_message(call.message.chat.id, "Уже обработана")
            return

        if action == "approve":
            c.execute('UPDATE deposits SET status = "approved" WHERE id = ?', (dep_id,))
            conn.commit()
            try:
                bot.send_message(user_id, f"{EMOJI['check']} <b>Заявка #{dep_id} одобрена!</b>\nСумма: {amount:,.2f} сом", parse_mode='HTML')
            except:
                pass
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id,
                                         caption=call.message.caption + "\n\n✅ ОДОБРЕНО")
            except:
                pass
        else:
            c.execute('UPDATE deposits SET status = "rejected" WHERE id = ?', (dep_id,))
            conn.commit()
            try:
                bot.send_message(user_id, f"{EMOJI['cross']} <b>Заявка #{dep_id} отклонена.</b>", parse_mode='HTML')
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
print(f"{BOT_NAME} бот запущен...")
bot.infinity_polling(none_stop=True)
