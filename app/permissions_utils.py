import logging
import os
from functools import wraps

from telegram import Update
from telegram.ext import ContextTypes

from database import get_user_by_mac, get_user_by_id

logger = logging.getLogger(__name__)

ALLOWED_CHAT_ID = int(os.getenv("CHAT_ID"))
ALLOWED_TOPIC_ID = int(os.getenv("TOPIC_ID"))

NOT_ALLOWED = "❌ Данная команда недоступна в данном чате или топике."


def allowed_only(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        chat_id = update.effective_chat.id
        topic_id = update.message.message_thread_id if update.message else None

        # личка: проверяем, состоит ли пользователь в группе
        if update.effective_chat.type == "private":
            try:
                member = await update.get_bot().get_chat_member(ALLOWED_CHAT_ID, update.effective_user.id)
                if member.status not in ("member", "creator", "administrator"):
                    logger.warning("Пользователь не в группе: %s", update.effective_user.id)
                    await update.message.reply_text(NOT_ALLOWED)
                    return
            except Exception as e:
                logger.warning("Ошибка проверки участника: %s", e)
                await update.message.reply_text(NOT_ALLOWED)
                return
            return await handler(update, context)

        # группа с обсуждениями — проверяем топик
        if chat_id == ALLOWED_CHAT_ID and topic_id == ALLOWED_TOPIC_ID:
            return await handler(update, context)

        logger.warning("Недопустимый доступ: %s", update.effective_user.id)
        await update.message.reply_text(NOT_ALLOWED)

    return wrapper


def private_only(handler):
    @wraps(handler)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        if update.effective_chat.type != "private":
            return
        return await handler(update, context)

    return wrapper


# Функции проверки и обработки
def is_mac_registered(mac_address):
    return get_user_by_mac(mac_address)


def is_user_registered(user_id):
    return get_user_by_id(user_id)
