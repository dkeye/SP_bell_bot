import asyncio
import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

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

    if chat_id != ALLOWED_CHAT_ID or topic_id != ALLOWED_TOPIC_ID:
        logger.warning(
            "Недопустимая команда: user_id=%s, chat_id=%s, topic_id=%s",
            update.effective_user.id,
            chat_id,
            topic_id
        )
        return False
    return True


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
    await update.message.reply_text(message, parse_mode="MarkdownV2")



# /bell команда
async def bell(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        await update.message.reply_text(NOT_ALLOWED)
        return

    # Получение подключенных MAC-адресов и пользователей
    connected_macs = get_connected_macs()
    users = get_all_users()

    # Извлечение уникальных user_id зарегистрированных пользователей
    user_ids = {users[mac][0] for mac in connected_macs if mac in users}

    # Если ни один пользователь не в сети
    if not user_ids:
        logger.info("Оповещение не отправлено: Никого нет в сети (user_id=%s)", update.effective_user.id)
        await update.message.reply_text(NO_CONNECTED_USERS)
        return

    # Собираем уникальные usernames для уведомления
    usernames = {users[mac][1] for mac in connected_macs if mac in users}

    # Формируем уведомление для текущего чата
    notification_message = NOTIFICATION_MESSAGE + "\n" + "\n".join(f"@{username}" for username in usernames)

    logger.info("Оповещение отправлено в группе (user_id=%s, usernames=%s)", update.effective_user.id, usernames)

    # Отправляем уведомление в текущий чат
    await update.message.reply_text(notification_message)


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
        "/delmac <MAC-адрес> - Удалить зарегистрированный MAC-адрес.\n"
        "/who - Показывает список пользователей, которые находятся в сети.\n"
        "/bell - Отправить уведомление зарегистрированным пользователям.\n"
        "/info - Получить информацию о текущем чате (ID).\n"
        "/help - Вывести список доступных команд."
    )
    await update.message.reply_text(help_text, parse_mode="Markdown")


# Настройка бота
def setup_bot():
    application = Application.builder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("reg", register))
    application.add_handler(CommandHandler("delmac", delete_mac))
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

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(application.run_polling())
    except KeyboardInterrupt:
        logger.info("Бот остановлен вручную")
    finally:
        logger.info("Закрытие приложения")
        loop.run_until_complete(application.shutdown())


if __name__ == "__main__":
    run_bot()
