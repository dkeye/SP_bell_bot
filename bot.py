import asyncio
import logging
import os

from telegram import Update, BotCommand, BotCommandScopeDefault, BotCommandScopeAllGroupChats, InlineKeyboardButton, \
    InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler

from database import init_db, add_user, remove_user, get_user_by_mac, get_user_by_id, get_all_users
from utils import get_connected_macs

# Инициализация логирования
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Константы
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
ALLOWED_CHAT_ID = int(os.getenv("CHAT_ID"))
ALLOWED_TOPIC_ID = int(os.getenv("TOPIC_ID"))

MAC_ALREADY_REGISTERED = "❌ Этот MAC уже зарегистрирован."
USER_ALREADY_REGISTERED = "❌ Вы уже зарегистрированы. Удалите старый MAC перед новой регистрацией."
USAGE_REGISTER = "❌ Использование: /reg <MAC-адрес>"
MAC_NOT_REGISTERED = "❌ Этот MAC не зарегистрирован."
CANNOT_DELETE_OTHER_MAC = "❌ Вы не можете удалить чужой MAC."
USAGE_DELETE_MAC = "❌ Использование: /delmac <MAC-адрес>"
NO_CONNECTED_USERS = "❌ В сети нет зарегистрированных пользователей."
NOTIFICATION_SENT = "🔔 Оповещение отправлено!"
NOTIFICATION_MESSAGE = "🔔 Кто-то просит открыть дверь!"
NOT_ALLOWED = "❌ Данная команда недоступна в данном чате или топике."


# Функции проверки и обработки
def is_mac_registered(mac_address):
    return get_user_by_mac(mac_address)


def is_user_registered(user_id):
    return get_user_by_id(user_id)


def get_user_data(update: Update):
    user_id = update.effective_user.id
    username = update.effective_user.username or update.effective_user.first_name
    return user_id, username


async def is_allowed(update: Update) -> bool:
    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id if update.message else None

    # Если это личка — проверяем, состоит ли человек в группе
    if update.effective_chat.type == "private":
        try:
            member = await update.get_bot().get_chat_member(ALLOWED_CHAT_ID, update.effective_user.id)
            if member.status not in ("member", "creator", "administrator"):
                logger.warning("Пользователь не состоит в группе: user_id=%s", update.effective_user.id)
                return False
            return True
        except Exception as e:
            logger.warning("Ошибка проверки участника: %s", e)
            return False

    # Если это группа с обсуждениями — проверяем топик
    if chat_id == ALLOWED_CHAT_ID and topic_id == ALLOWED_TOPIC_ID:
        return True

    logger.warning(
        "Недопустимая команда: user_id=%s, chat_id=%s, topic_id=%s",
        update.effective_user.id,
        chat_id,
        topic_id
    )
    return False



# /reg команда
async def register(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        await update.message.reply_text(NOT_ALLOWED)
        return

    if len(context.args) != 1:
        await update.message.reply_text(USAGE_REGISTER)
        return

    mac_address = context.args[0].upper()
    user_id, username = get_user_data(update)

    if is_mac_registered(mac_address):
        logger.info("MAC %s уже зарегистрирован (user_id=%s)", mac_address, user_id)
        await update.message.reply_text(MAC_ALREADY_REGISTERED)
        return

    # Регистрация нового MAC для пользователя
    add_user(mac_address, user_id, username)
    logger.info("MAC %s зарегистрирован для user_id=%s, username=%s", mac_address, user_id, username)
    await update.message.reply_text(f"✅ @{username} зарегистрирован с MAC {mac_address}")


# /delmac команда
async def delete_mac(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        await update.message.reply_text(NOT_ALLOWED)
        return

    if len(context.args) != 1:
        await update.message.reply_text(USAGE_DELETE_MAC)
        return

    mac_address = context.args[0].upper()
    user_id = update.effective_user.id
    user = is_mac_registered(mac_address)

    if not user:
        logger.info("Попытка удалить несуществующий MAC: %s (user_id=%s)", mac_address, user_id)
        await update.message.reply_text(MAC_NOT_REGISTERED)
        return

    if user[1] != user_id:
        logger.warning("Попытка удалить чужой MAC. user_id=%s, MAC=%s", user_id, mac_address)
        await update.message.reply_text(CANNOT_DELETE_OTHER_MAC)
        return

    remove_user(mac_address)
    logger.info("MAC %s удалён (user_id=%s)", mac_address, user_id)
    await update.message.reply_text(f"✅ MAC {mac_address} удалён.")


async def choose_mac_to_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    users = get_all_users()
    user_macs = [mac for mac, (uid, _) in users.items() if uid == user_id]

    if not user_macs:
        await update.message.reply_text("У вас нет зарегистрированных MAC-адресов.")
        return

    buttons = [[InlineKeyboardButton(mac, callback_data=f"delmac:{mac}")]
               for mac in user_macs]
    buttons.append([InlineKeyboardButton("Удалить все", callback_data="delmac:ALL")])

    await update.message.reply_text(
        "Выберите MAC-адрес для удаления:",
        reply_markup=InlineKeyboardMarkup(buttons)
    )

async def handle_mac_delete_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    mac_arg = query.data.split(":")[1]

    users = get_all_users()
    if mac_arg == "ALL":
        removed = 0
        for mac, (uid, _) in list(users.items()):
            if uid == user_id:
                remove_user(mac)
                removed += 1
        await query.edit_message_text(f"✅ Удалено {removed} MAC-адресов.")
    else:
        owner = users.get(mac_arg)
        if owner and owner[0] == user_id:
            remove_user(mac_arg)
            await query.edit_message_text(f"✅ MAC {mac_arg} удалён.")
        else:
            await query.edit_message_text("❌ Вы не можете удалить этот MAC.")

# /who команда
async def who(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        await update.message.reply_text(NOT_ALLOWED)
        return

    connected_macs = get_connected_macs()
    users = get_all_users()
    registered_usernames = {users[mac][1] for mac in connected_macs if mac in users}

    if not registered_usernames:
        logger.info("Никто не подключён (user_id=%s)", update.effective_user.id)
        await update.message.reply_text(NO_CONNECTED_USERS)
        return

    message = "👥 В сети:\n" + "\n".join(f"[{username}](https://t.me/{username})" for username in registered_usernames)
    logger.info("Список пользователей в сети: user_id=%s, users=%s", update.effective_user.id, registered_usernames)
    await update.message.reply_text(message, parse_mode="MarkdownV2", disable_web_page_preview=True)



# /bell команда
async def bell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        await update.message.reply_text(NOT_ALLOWED)
        return

    connected_macs = get_connected_macs()
    users = get_all_users()
    usernames = {users[mac][1] for mac in connected_macs if mac in users}

    if not usernames:
        logger.info("Оповещение не отправлено: Никого нет в сети (user_id=%s)", update.effective_user.id)
        await update.message.reply_text(NO_CONNECTED_USERS)
        return

    # 📣 Отправляем сообщение в чат
    message = NOTIFICATION_MESSAGE + "\n" + "\n".join(f"@{username}" for username in usernames)

    try:
        await context.bot.send_message(
            chat_id=ALLOWED_CHAT_ID,
            message_thread_id=ALLOWED_TOPIC_ID,
            text=message,
            disable_web_page_preview=True
        )
        logger.info("Оповещение отправлено в чат: %s", message)
    except Exception as e:
        logger.error("Ошибка при отправке оповещения в группу: %s", e)
        await update.message.reply_text("⚠️ Ошибка при отправке оповещения.")



# /info команда
async def info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    topic_id = update.message.message_thread_id if update.message else None

    logger.info("chat_id=%s, topic_id=%s", chat_id, topic_id)
    await update.message.reply_text(f"Chat ID: `{chat_id}`\nTopic ID: `{topic_id}`", parse_mode="MarkdownV2")


# /help команда
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда, отображающая список доступных команд и их описание."""
    if not await is_allowed(update):
        await update.message.reply_text(NOT_ALLOWED)
        return

    # Текст для справки
    help_text = (
        "🛠 Доступные команды:\n\n"
        "/reg <MAC-адрес> - Зарегистрировать новый MAC-адрес.\n"
        "/delmac - Удалить зарегистрированный MAC-адрес.\n"
        "/who - Показывает список пользователей, которые находятся в сети.\n"
        "/bell - Отправить уведомление зарегистрированным пользователям.\n"
        "/info - Получить информацию о текущем чате (ID).\n"
        "/help - Вывести список доступных команд."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")

async def set_bot_commands(application):
    await application.bot.set_my_commands(
        [
            BotCommand("reg", "Зарегистрировать MAC-адрес"),
            BotCommand("delmac", "Удалить MAC-адрес"),
            BotCommand("who", "Кто в сети"),
            BotCommand("bell", "Позвать всех"),
            BotCommand("info", "Chat ID / Topic ID"),
            BotCommand("help", "Справка")
        ],
        scope=BotCommandScopeDefault()
    )

    await application.bot.set_my_commands(
        [
            BotCommand("who", "Кто в сети"),
            BotCommand("bell", "Позвать всех"),
            BotCommand("help", "Справка")
        ],
        scope=BotCommandScopeAllGroupChats()
    )

# Настройка бота
def setup_bot():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.post_init = set_bot_commands

    application.add_handler(CommandHandler("reg", register, has_args=1))
    application.add_handler(CommandHandler("delmac", choose_mac_to_delete))
    application.add_handler(CallbackQueryHandler(handle_mac_delete_callback, pattern="^delmac:"))
    application.add_handler(CommandHandler("who", who))
    application.add_handler(CommandHandler("bell", bell))
    application.add_handler(CommandHandler("info", info))
    application.add_handler(CommandHandler("help", help_command))
    return application


# Запуск бота
def run_bot():
    init_db()
    logger.info("Инициализация БД завершена.")

    application = setup_bot()
    application.run_polling()


if __name__ == "__main__":
    run_bot()
