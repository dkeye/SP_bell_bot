import logging
import os

from telegram import (
    Update, BotCommand, BotCommandScopeDefault,
    BotCommandScopeAllGroupChats, InlineKeyboardButton, InlineKeyboardMarkup
)
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler
)

from database import init_db, add_user, remove_user, get_all_users
from network_utils import get_connected_macs
from permissions_utils import is_mac_registered, allowed_only, private_only

# Логирование
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("CHAT_ID"))
ALLOWED_TOPIC_ID = int(os.getenv("TOPIC_ID"))

# Ответы
MAC_ALREADY_REGISTERED = "❌ Этот MAC уже зарегистрирован."
MAC_NOT_REGISTERED = "❌ Этот MAC не зарегистрирован."
CANNOT_DELETE_OTHER_MAC = "❌ Вы не можете удалить чужой MAC."
USAGE_REGISTER = "❌ Использование: /reg <MAC-адрес>"
USAGE_DELETE_MAC = "❌ Использование: /delmac <MAC-адрес>"
NO_CONNECTED_USERS = "❌ В сети нет зарегистрированных пользователей."
NOTIFICATION_SENT = "🔔 Оповещение отправлено!"
NOTIFICATION_MESSAGE = "🔔 Кто-то просит открыть дверь!"


def get_user_data(update: Update):
    user = update.effective_user
    return user.id, user.username or user.first_name


@allowed_only
@private_only
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text(USAGE_REGISTER)
        return

    mac = context.args[0].upper()
    user_id, username = get_user_data(update)

    if is_mac_registered(mac):
        logger.info("MAC %s уже зарегистрирован (user_id=%s)", mac, user_id)
        await update.message.reply_text(MAC_ALREADY_REGISTERED)
        return

    add_user(mac, user_id, username)
    logger.info("MAC %s зарегистрирован для user_id=%s", mac, user_id)
    await update.message.reply_text(f"✅ @{username} зарегистрирован с MAC {mac}")


@allowed_only
@private_only
async def delete_mac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) != 1:
        await update.message.reply_text(USAGE_DELETE_MAC)
        return

    mac = context.args[0].upper()
    user_id = update.effective_user.id
    user = is_mac_registered(mac)

    if not user:
        logger.info("MAC %s не существует (user_id=%s)", mac, user_id)
        await update.message.reply_text(MAC_NOT_REGISTERED)
        return

    if user[0] != user_id:
        logger.warning("Чужой MAC: %s от %s", mac, user_id)
        await update.message.reply_text(CANNOT_DELETE_OTHER_MAC)
        return

    remove_user(mac)
    logger.info("MAC %s удалён (user_id=%s)", mac, user_id)
    await update.message.reply_text(f"✅ MAC {mac} удалён.")


@allowed_only
@private_only
async def choose_mac_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    macs = [mac for mac, (uid, _) in get_all_users().items() if uid == user_id]

    if not macs:
        await update.message.reply_text("У вас нет зарегистрированных MAC-адресов.")
        return

    buttons = [[InlineKeyboardButton(mac, callback_data=f"delmac:{mac}")] for mac in macs]
    buttons.append([InlineKeyboardButton("Удалить все", callback_data="delmac:ALL")])

    await update.message.reply_text("Выберите MAC для удаления:", reply_markup=InlineKeyboardMarkup(buttons))


@allowed_only
@private_only
async def handle_mac_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mac_arg = query.data.split(":")[1]

    users = get_all_users()
    if mac_arg == "ALL":
        count = sum(remove_user(mac) or 1 for mac, (uid, _) in users.items() if uid == user_id)
        await query.edit_message_text(f"✅ Удалено {count} MAC-адресов.")
    elif (owner := users.get(mac_arg)) and owner[0] == user_id:
        remove_user(mac_arg)
        await query.edit_message_text(f"✅ MAC {mac_arg} удалён.")
    else:
        await query.edit_message_text("❌ Вы не можете удалить этот MAC.")


@allowed_only
async def who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    connected = get_connected_macs()
    names = {users[mac][1] for mac in connected if mac in users}

    if not names:
        await update.message.reply_text(NO_CONNECTED_USERS)
        return

    msg = "👥 В сети:\n" + "\n".join(f"[{name}](https://t.me/{name})" for name in names)
    await update.message.reply_text(msg, parse_mode="MarkdownV2", disable_web_page_preview=True)


@allowed_only
async def bell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    connected = get_connected_macs()
    names = {users[mac][1] for mac in connected if mac in users}

    if not names:
        await update.message.reply_text(NO_CONNECTED_USERS)
        return

    msg = NOTIFICATION_MESSAGE + "\n" + "\n".join(f"@{name}" for name in names)
    try:
        await context.bot.send_message(
            chat_id=ALLOWED_CHAT_ID,
            message_thread_id=ALLOWED_TOPIC_ID,
            text=msg,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error("Ошибка отправки bell: %s", e)
        await update.message.reply_text("⚠️ Ошибка при отправке оповещения.")


async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id if update.message else None
    await update.message.reply_text(f"Chat ID: `{chat_id}`\nTopic ID: `{topic_id}`", parse_mode="MarkdownV2")


@allowed_only
@private_only
async def my_macs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    macs = [mac for mac, (uid, _) in get_all_users().items() if uid == user_id]
    if not macs:
        await update.message.reply_text("У вас нет зарегистрированных MAC-адресов.")
        return
    await update.message.reply_text("Ваши MAC-адреса:\n" + "\n".join(macs))


@allowed_only
@private_only
async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = get_all_users()
    connected = get_connected_macs()
    user_status = {}
    for mac, (user_id, username) in users.items():
        if user_id not in user_status:
            user_status[user_id] = (username, False)
        if mac in connected:
            user_status[user_id] = (username, True)

    lines = [
        f"{'🟢' if online else '⚪️'} @{username}"
        for username, online in user_status.values()
    ]

    lines.sort(reverse=True)  # Сначала 🟢, потом ⚪️

    online_count = sum(online for _, online in user_status.values())
    text = (
            f"👥 Зарегистрировано: {len(user_status)}\n"
            f"🟢 Сейчас в сети: {online_count}\n\n" +
            "\n".join(lines)
    )

    await update.message.reply_text(text)


@allowed_only
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_chat.type == "private":
        text = (
            "🛠 Доступные команды:\n\n"
            "/reg <MAC-адрес> — Зарегистрировать MAC.\n"
            "/delmac — Удалить MAC.\n"
            "/my — Посмотреть свои MAC.\n"
            "/stats — Статистика.\n"
            "/who — Кто в сети.\n"
            "/bell — Позвать всех.\n"
            "/info — ID чата и топика.\n"
            "/help — Эта справка."
        )
    else:
        text = (
            "🛠 Доступные команды:\n\n"
            "/who — Кто в сети.\n"
            "/bell — Позвать всех.\n"
            "/info — ID чата и топика.\n"
            "/help — Эта справка."
        )
    await update.message.reply_text(text)


async def set_bot_commands(application):
    await application.bot.set_my_commands([
        BotCommand("reg", "Зарегистрировать MAC-адрес"),
        BotCommand("delmac", "Удалить MAC-адрес"),
        BotCommand("my", "Посмотреть свои MAC"),
        BotCommand("stats", "Статистика"),
        BotCommand("who", "Кто в сети"),
        BotCommand("bell", "Позвать всех"),
        BotCommand("info", "Chat ID / Topic ID"),
        BotCommand("help", "Справка")
    ], scope=BotCommandScopeDefault())

    await application.bot.set_my_commands([
        BotCommand("who", "Кто в сети"),
        BotCommand("bell", "Позвать всех"),
        BotCommand("info", "Chat ID / Topic ID"),
        BotCommand("help", "Справка")
    ], scope=BotCommandScopeAllGroupChats())


def setup_bot():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.post_init = set_bot_commands

    app.add_handler(CommandHandler("reg", register, has_args=1))
    app.add_handler(CommandHandler("delmac", choose_mac_to_delete))
    app.add_handler(CallbackQueryHandler(handle_mac_delete_callback, pattern="^delmac:"))
    app.add_handler(CommandHandler("my", my_macs))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("who", who))
    app.add_handler(CommandHandler("bell", bell))
    app.add_handler(CommandHandler("info", info))
    app.add_handler(CommandHandler("help", help_command))
    return app


def run_bot():
    init_db()
    logger.info("Инициализация БД завершена.")
    app = setup_bot()
    app.run_polling()


if __name__ == "__main__":
    run_bot()
