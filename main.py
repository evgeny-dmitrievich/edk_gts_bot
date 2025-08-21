import os
import asyncio
import logging
from typing import Optional
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
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(os.path.join(
            LOG_DIR, "bot.log"), encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Настройки
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в .env")
if not CHAT_ID:
    raise ValueError("CHAT_ID не найден в .env")
CHAT_ID = int(CHAT_ID)

dp = Dispatcher()

# Разрешённые форматы
ALLOWED_PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".mpeg"}

# Максимальный размер файла
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ

# Максимальное кол-во медиа в одном альбоме
MEDIA_GROUP_LIMIT = 10

media_buffer = {}


@dp.startup()
async def on_startup(bot: Bot):
    commands = [BotCommand(command="start", description="Начать работу")]
    await bot.set_my_commands(commands)
    logger.info("Меню команд бота установлено")


# Проверка формата документа
def is_allowed_file(file_name: str) -> Optional[str]:
    ext = os.path.splitext(file_name.lower())[1]
    if ext in ALLOWED_PHOTO_EXTS:
        return "photo"
    if ext in ALLOWED_VIDEO_EXTS:
        return "video"
    return None


# Подпись
def make_caption(user, base_caption: Optional[str] = None) -> str:
    return base_caption or f"🔩 Сборка/Отчет от {user.full_name}⚒️"


# Универсальная отправка файла
async def forward_file(bot: Bot, chat_id: int, file_type: str,
                       file_id: str, caption: Optional[str],
                       is_document: bool, user=None):
    if not caption and user:
        caption = make_caption(user)
    try:
        if file_type == "photo":
            if not is_document:
                await bot.send_photo(chat_id, file_id, caption=caption)
            else:
                await bot.send_document(chat_id, file_id, caption=caption)
        elif file_type == "video":
            if not is_document:
                await bot.send_video(chat_id, file_id, caption=caption)
            else:
                await bot.send_document(chat_id, file_id, caption=caption)
        return True
    except TelegramRetryAfter as e:
        logger.warning(f"Флуд-контроль: жду {e.timeout} сек.")
        await asyncio.sleep(e.timeout)
        return await forward_file(
            bot, chat_id, file_type, file_id, caption, is_document, user)
    except TelegramForbiddenError:
        logger.error("Бот потерял доступ к чату")
    except TelegramBadRequest as e:
        logger.error(f"Неверный запрос Telegram: {e}")
    except Exception as e:
        logger.error(f"Ошибка при отправке {file_type}: {e}")
    return False


# Команда /start (только приватные чаты)
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    if msg.chat.type != "private":
        return
    await msg.answer(
        "Бот запущен и готов к работе ✅ 📌 "
        "Загрузи фото или видео монтажа, я отправлю их в чат.")
    logger.info(f"{msg.from_user.full_name} "
                f"({msg.from_user.id}) использовал /start")


# Команда /id (работает везде)
@dp.message(Command("id"))
async def chat_id_cmd(msg: Message):
    await msg.answer(f"chat_id этого чата: "
                     f"<code>{msg.chat.id}</code>", parse_mode="HTML")
    logger.info(f"{msg.from_user.full_name} "
                f"({msg.from_user.id}) "
                f"использовал /id → chat_id={msg.chat.id}")


# Обработка фото/видео/документов
@dp.message(F.photo | F.video | F.document | F.media_group_id)
async def handle_media(msg: Message):
    media_group_id = msg.media_group_id or msg.message_id
    if media_group_id not in media_buffer:
        media_buffer[media_group_id] = []
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
    if file_size > MAX_FILE_SIZE:
        await msg.reply(
            f"❌Файл слишком большой!\n\n"
            f"Размер: {file_size / 1024 / 1024:.1f} МБ\n"
            f"Максимально допустимо: {MAX_FILE_SIZE / 1024 / 1024:.0f} МБ"
        )
        logger.warning(
            f"Отклонён большой файл: {file_type}, размер {file_size}")
        return
    if file_type and file_id:
        media_buffer[media_group_id].append(
            (file_type, file_id, caption, msg, is_document))
    await asyncio.sleep(2)
    if media_group_id in media_buffer:
        media_items = media_buffer.pop(media_group_id)

        # Один файл
        if len(media_items) == 1:
            file_type, file_id, caption, msg, is_document = media_items[0]
            success = await forward_file(
                msg.bot, CHAT_ID, file_type, file_id,
                caption, is_document, msg.from_user)
            if success:
                await msg.reply("✅ Файл успешно отправлен!")

        # Альбом
        else:
            # Разбиваем на чанки по 10 медиа
            for i in range(0, len(media_items), MEDIA_GROUP_LIMIT):
                chunk = media_items[i:i + MEDIA_GROUP_LIMIT]
                media = []
                for j, (file_type, file_id, caption, msg,
                        is_document) in enumerate(chunk):
                    cap = caption or (
                        make_caption(msg.from_user)
                        if (not is_document and j == 0) or (
                            is_document and j == len(chunk) - 1)
                        else None
                    )
                    if file_type == "photo":
                        media.append(InputMediaPhoto(media=file_id,
                                                     caption=cap)
                                     if not is_document
                                     else InputMediaDocument(media=file_id,
                                                             caption=cap))
                    elif file_type == "video":
                        media.append(InputMediaVideo(media=file_id,
                                                     caption=cap)
                                     if not is_document
                                     else InputMediaDocument(media=file_id,
                                                             caption=cap))
                try:
                    await msg.bot.send_media_group(CHAT_ID, media=media)
                except Exception as e:
                    logger.error(f"Ошибка при пересылке альбома: {e}")
            await msg.reply(
                f"✅ Альбом ({len(media_items)} шт.) успешно отправлен!")
            logger.info(f"Альбом ({len(media_items)} шт.) "
                        f"от {msg.from_user.full_name} "
                        f"({msg.from_user.id}) → {CHAT_ID}")


# Неподдерживаемое сообщение
@dp.message()
async def handle_unsupported(msg: Message):
    if msg.chat.type != "private":
        return
    if not msg.text or not msg.text.startswith("/"):
        await msg.reply("⚠️ К сожалению, бот не умеет работать с текстом 😢")
        logger.info(f"Неподдерживаемое сообщение от "
                    f"{msg.from_user.full_name} ({msg.from_user.id})")


# Запуск бота
async def main():
    logger.info("Бот запущен...")
    async with Bot(token=BOT_TOKEN) as bot:
        await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
