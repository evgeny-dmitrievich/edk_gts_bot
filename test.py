import os
import asyncio
import logging
import uuid
from logging.handlers import RotatingFileHandler
from typing import Optional
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument, BotCommand
)
from aiogram.filters import Command
from aiogram.exceptions import (
    TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter)
from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_DIR = os.path.join(BASE_DIR, "logs")
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

# Логирование
log_file = os.path.join(LOG_DIR, "bot.log")
file_handler = RotatingFileHandler(
    log_file,
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        file_handler,
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Настройки
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
MAX_FILE_SIZE = int(os.getenv("MAX_FILE_SIZE_MB", "50")) * 1024 * 1024

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")
if not CHAT_ID:
    raise ValueError("CHAT_ID не найден в .env")
CHAT_ID = int(CHAT_ID)

dp = Dispatcher()

# Разрешённые форматы
ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".mpeg"}

MEDIA_GROUP_LIMIT = 10

# Буфер и таймеры теперь с ключом album_key
media_buffer: dict[str, list] = {}
album_timers: dict[str, asyncio.Task] = {}


@dp.startup()
async def on_startup(bot: Bot):
    commands = [BotCommand(command="start", description="Начать работу")]
    await bot.set_my_commands(commands)
    logger.info("Меню команд бота установлено")


def is_real_command(text: str) -> bool:
    if not text.startswith("/"):
        return False
    command = text.split()[0][1:].split("@")[0]
    return command in ["start", "id"]


def is_allowed_file(file_name: str) -> Optional[str]:
    ext = os.path.splitext(file_name.lower())[1]
    if ext in ALLOWED_PHOTO_EXTS:
        return "photo"
    if ext in ALLOWED_VIDEO_EXTS:
        return "video"
    return None


def make_caption(user, user_caption: Optional[str] = None) -> str:
    if user_caption and user_caption.strip():
        return f"💬 {user_caption.strip()} - от {user.full_name}"
    return f"🖼️ Фото/Видео - от {user.full_name}"


async def forward_file(bot: Bot, chat_id: int,
                       file_type: Optional[str], file_id: Optional[str],
                       caption: Optional[str],
                       is_document: bool = False,
                       user=None, text_message: Optional[str] = None):
    # Текстовое сообщение
    if text_message:
        text_to_send = make_caption(user, text_message)
        try:
            await bot.send_message(chat_id, text_to_send)
            return True
        except Exception as e:
            logger.error(f"Ошибка при пересылке текста: {e}")
            return False

    final_caption = make_caption(user, caption)

    # Повторные попытки до 3 раз при RetryAfter
    for attempt in range(3):
        try:
            if file_type == "photo":
                if not is_document:
                    await bot.send_photo(chat_id, file_id, caption=final_caption)
                else:
                    await bot.send_document(chat_id, file_id, caption=final_caption)
            elif file_type == "video":
                if not is_document:
                    await bot.send_video(chat_id, file_id, caption=final_caption)
                else:
                    await bot.send_document(chat_id, file_id, caption=final_caption)
            return True
        except TelegramRetryAfter as e:
            logger.warning(
                f"Флуд-контроль: жду {e.retry_after} сек. (попытка {attempt+1})")
            await asyncio.sleep(e.retry_after)
        except TelegramForbiddenError:
            logger.error("Бот потерял доступ к чату")
            break
        except TelegramBadRequest as e:
            logger.error(f"Неверный запрос Telegram: {e}")
            break
        except Exception as e:
            logger.error(f"Ошибка при отправке {file_type}: {e}")
            break
    return False


# Генерация уникального ключа для альбома
def make_album_key(chat_id: int, media_group_id: Optional[int], msg_id: int) -> str:
    mg_id = media_group_id or msg_id
    return f"{chat_id}_{mg_id}_{uuid.uuid4().hex}"


async def schedule_album_send(album_key: str, delay: int = 5):
    if album_key in album_timers:
        album_timers[album_key].cancel()
    album_timers[album_key] = asyncio.create_task(wait_and_send(album_key, delay))


async def wait_and_send(album_key: str, delay: int):
    await asyncio.sleep(delay)
    await send_album(album_key)
    album_timers.pop(album_key, None)


# Очистка старых альбомов и отправка
async def send_album(album_key: str):
    items = media_buffer.pop(album_key, [])
    if not items:
        return

    msg = items[0][3]  # Берём первый объект Message для bot
    for i in range(0, len(items), MEDIA_GROUP_LIMIT):
        chunk = items[i:i + MEDIA_GROUP_LIMIT]
        media = []
        for j, (file_type, file_id, caption, msg_item, is_document) in enumerate(chunk):
            if caption and caption.strip():
                cap = make_caption(msg_item.from_user, caption)
            else:
                if not is_document and j == 0:
                    cap = make_caption(msg_item.from_user)
                elif is_document and j == len(chunk) - 1:
                    cap = make_caption(msg_item.from_user)
                else:
                    cap = None

            if file_type == "photo":
                media.append(InputMediaPhoto(media=file_id, caption=cap) if not is_document else InputMediaDocument(media=file_id, caption=cap))
            elif file_type == "video":
                media.append(InputMediaVideo(media=file_id, caption=cap) if not is_document else InputMediaDocument(media=file_id, caption=cap))

        try:
            await msg.bot.send_media_group(CHAT_ID, media=media)
        except TelegramRetryAfter as e:
            logger.warning(f"Флуд-контроль (альбом): жду {e.retry_after} сек.")
            await asyncio.sleep(e.retry_after)
        except Exception as e:
            logger.error(f"Ошибка при пересылке альбома: {e}")
            break

    await msg.reply(f"✅ Альбом ({len(items)} шт.) успешно отправлен!")
    logger.info(f"Альбом ({len(items)} шт.) от {msg.from_user.full_name} → {CHAT_ID}")


def cleanup_old_albums(ttl_seconds: int = 120):
    now = datetime.now()
    for album_key, items in list(media_buffer.items()):
        if not items:
            continue
        first_msg_time = datetime.fromtimestamp(items[0][3].date.timestamp())
        if now - first_msg_time > timedelta(seconds=ttl_seconds):
            logger.info(f"Очищен старый альбом: album_key={album_key}")
            media_buffer.pop(album_key, None)


@dp.message(Command("start"))
async def start_cmd(msg: Message):
    if msg.chat.type != "private":
        return
    await msg.answer(
        "Бот запущен и готов к работе ✅ 📌 "
        "Загрузи фото/видео или напиши короткое сообщение, "
        "я отправлю их в чат.")


@dp.message(Command("id"))
async def chat_id_cmd(msg: Message):
    await msg.answer(
        f"chat_id этого чата: <code>{msg.chat.id}</code>", parse_mode="HTML")


@dp.message(F.photo | F.video | F.document | F.media_group_id | F.text)
async def handle_media(msg: Message):
    chat_id = msg.chat.id

    # Текстовое сообщение, не команда
    if msg.text and not is_real_command(msg.text):
        success = await forward_file(
            msg.bot, CHAT_ID, None, None, None, user=msg.from_user,
            text_message=msg.text
        )
        if success:
            await msg.reply("✅ Сообщение успешно отправлено!")
        return

    # Генерация уникального ключа
    album_key = make_album_key(chat_id, msg.media_group_id, msg.message_id)

    file_type = None
    file_id = None
    file_size = 0
    caption = msg.caption
    is_document = False

    if msg.photo:
        file_type = "photo"
        file_id = msg.photo[-1].file_id
        file_size = msg.photo[-1].file_size
    elif msg.video:
        file_type = "video"
        file_id = msg.video.file_id
        file_size = msg.video.file_size
    elif msg.document:
        kind = is_allowed_file(msg.document.file_name)
        if not kind:
            await msg.reply("⚠️ Файл не поддерживается. "
                            "Бот принимает только фото и видео.")
            logger.warning(f"Отклонён файл: {msg.document.file_name}")
            return
        file_type = kind
        file_id = msg.document.file_id
        file_size = msg.document.file_size
        is_document = True
    else:
        return

    if file_size > MAX_FILE_SIZE:
        await msg.reply(
            f"❌Файл слишком большой!\n\n"
            f"Размер вашего файла: {file_size / 1024 / 1024:.1f} МБ\n"
            f"Максимальный размер: {MAX_FILE_SIZE / 1024 / 1024:.0f} МБ"
        )
        logger.warning(f"Отклонён большой файл: {file_type}, размер {file_size}")
        return

    # Добавляем в буфер
    if album_key not in media_buffer:
        media_buffer[album_key] = []

    media_buffer[album_key].append(
        (file_type, file_id, caption, msg, is_document)
    )

    # Планируем отправку
    if msg.media_group_id:
        await schedule_album_send(album_key)
    else:
        file_type, file_id, caption, msg_item, is_document = media_buffer.pop(album_key)[0]
        success = await forward_file(msg.bot, CHAT_ID, file_type, file_id, caption, is_document, msg_item.from_user)
        if success:
            await msg.reply("✅ Файл успешно отправлен!")


@dp.edited_message()
async def handle_edit(msg: Message):
    if msg.text and not is_real_command(msg.text):
        try:
            await msg.bot.send_message(
                CHAT_ID,
                f"✏️ (Внес исправления)\n\n"
                f"{make_caption(msg.from_user, msg.text)}"
            )
            logger.info(f"Редактированное сообщение от {msg.from_user.full_name} → {CHAT_ID}")
        except Exception as e:
            logger.error(f"Ошибка при пересылке редактированного сообщения: {e}")


async def main():
    logger.info("Бот запущен...")
    async with Bot(token=BOT_TOKEN) as bot:
        await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
