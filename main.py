import os
import asyncio
import logging
from typing import Optional
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, InputMediaPhoto, InputMediaVideo, InputMediaDocument, BotCommand
)
from aiogram.filters import Command
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
        logging.FileHandler(
            os.path.join(LOG_DIR, "bot.log"), encoding="utf-8"),
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
ALLOWED_PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif"}
ALLOWED_VIDEO_EXT = {".mp4", ".mov", ".avi", ".mkv", ".wmv", ".webm", ".mpeg"}

# Максимальный размер файла
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 МБ


media_buffer = {}


@dp.startup()
async def on_startup(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу")
    ]
    await bot.set_my_commands(commands)
    logger.info("Меню команд бота установлено")


# Проверка формата файла
def is_allowed_file(file_name: str) -> Optional[str]:
    ext = os.path.splitext(file_name.lower())[1]
    if ext in ALLOWED_PHOTO_EXT:
        return "photo"
    if ext in ALLOWED_VIDEO_EXT:
        return "video"
    return None


# Команда /start (только приватные чаты)
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    if msg.chat.type != "private":
        return
    await msg.answer(
        "Бот запущен и готов к работе ✅ 📌 "
        "Загрузи фото или видео монтажа, я отправлю их в чат."
    )
    logger.info(
        f"{msg.from_user.full_name} ({msg.from_user.id}) использовал /start")


# Команда /id (работает везде)
@dp.message(Command("id"))
async def chat_id_cmd(msg: Message):
    await msg.answer(f"chat_id этого чата: "
                     f"<code>{msg.chat.id}</code>", parse_mode="HTML")
    logger.info(f"{msg.from_user.full_name} ({msg.from_user.id}) "
                f"использовал /id → chat_id={msg.chat.id}")


# Обработка фото/видео (включая документы)
@dp.message(F.photo | F.video | F.document | F.media_group_id)
async def handle_media(msg: Message):
    media_group_id = msg.media_group_id or msg.message_id
    if media_group_id not in media_buffer:
        media_buffer[media_group_id] = []

    file_type = None
    file_id = None
    file_size = 0
    caption = msg.caption if msg.caption else None
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

    # Проверка размера
    if file_size > MAX_FILE_SIZE:
        await msg.reply(
            f"❌Файл слишком большой!\n\n"
            f"Размер вашего файла: {file_size / 1024 / 1024:.1f} МБ\n"
            f"Максимально допустимый размер: "
            f"{MAX_FILE_SIZE / 1024 / 1024:.0f} МБ\n\n"
            f"⚠️ Пожалуйста, отправьте файл меньшего размера."
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
        if len(media_items) == 1:
            file_type, file_id, caption, msg, is_document = media_items[0]
            try:
                if file_type == "photo":
                    if not is_document:
                        await msg.bot.send_photo(
                            CHAT_ID, file_id,
                            caption=caption or f"🔩 Сборка от "
                                               f"{msg.from_user.full_name}⚒️"
                        )
                    else:
                        await msg.bot.send_document(
                            CHAT_ID, file_id,
                            caption=caption or f"🔩 Сборка от "
                                               f"{msg.from_user.full_name}⚒️"
                        )
                elif file_type == "video":
                    if not is_document:
                        await msg.bot.send_video(
                            CHAT_ID, file_id,
                            caption=caption or f"🔩 Сборка от "
                                               f"{msg.from_user.full_name}⚒️"
                        )
                    else:
                        await msg.bot.send_document(
                            CHAT_ID, file_id,
                            caption=caption or f"🔩 Сборка от "
                                               f"{msg.from_user.full_name}⚒️"
                        )
                await msg.reply("✅ Файл успешно отправлен!")
                logger.info(f"{file_type.capitalize()} от "
                            f"{msg.from_user.full_name} "
                            f"({msg.from_user.id}) → {CHAT_ID}")
            except Exception as e:
                await msg.reply("❌ Ошибка при отправке файла.")
                logger.error(f"Ошибка при отправке {file_type}: {e}")
        else:
            media = []
            for i, (
                file_type, file_id, caption, msg, is_document) in enumerate(
                    media_items):
                cap = caption or (f"🔩 Сборка от "
                                  f"{msg.from_user.full_name}⚒️"
                                  if i == 0 else None)
                if file_type == "photo":
                    if not is_document:
                        media.append(
                            InputMediaPhoto(media=file_id, caption=cap))
                    else:
                        media.append(
                            InputMediaDocument(media=file_id, caption=cap))
                elif file_type == "video":
                    if not is_document:
                        media.append(
                            InputMediaVideo(media=file_id, caption=cap))
                    else:
                        media.append(
                            InputMediaDocument(media=file_id, caption=cap))
            try:
                await msg.bot.send_media_group(CHAT_ID, media=media)
                await msg.reply(
                    f"✅ Альбом ({len(media)} шт.) успешно отправлен!")
                logger.info(f"Альбом ({len(media)} шт.) от "
                            f"{msg.from_user.full_name} "
                            f"({msg.from_user.id}) → {CHAT_ID}")
            except Exception as e:
                await msg.reply("❌ Ошибка при пересылке альбома.")
                logger.error(f"Ошибка при пересылке альбома: {e}")


# Неподдерживаемое сообщение (только если это не команда)
@dp.message()
async def handle_unsupported(msg: Message):
    # Проверяем, что это приватный чат
    if msg.chat.type != "private":
        return
    if not msg.text or not msg.text.startswith("/"):
        await msg.reply("⚠️ К сожалению бот не умеет читать(😢 ")
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
