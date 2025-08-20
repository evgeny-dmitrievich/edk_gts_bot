import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InputMediaPhoto, InputMediaVideo, BotCommand
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

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Начать работу"),
    ]
    await bot.set_my_commands(commands)
    logger.info("Меню команд бота установлено")


# Команды
@dp.message(Command("start"))
async def start_cmd(msg: Message):
    await msg.answer("Бот запущен и готов к работе ✅ 📌 "
                     "Загрузи фото или видео монтажа, я отправлю их в чат.")
    logger.info(
        f"{msg.from_user.full_name} ({msg.from_user.id}) использовал /start")


@dp.message(Command("id"))
async def chat_id_cmd(msg: Message):
    await msg.answer(
        f"chat_id этого чата: <code>{msg.chat.id}</code>", parse_mode="HTML")
    logger.info(
        f"{msg.from_user.full_name} ({msg.from_user.id})"
        f" использовал /id → chat_id={msg.chat.id}")


album_buffer = {}


# Одиночное фото
@dp.message(F.photo & ~F.media_group_id)
async def handle_photo(msg: Message):
    try:
        caption = msg.caption or f"🔩 Сборка от {msg.from_user.full_name}⚒️"
        await bot.send_photo(
            chat_id=CHAT_ID,
            photo=msg.photo[-1].file_id, caption=caption)
        await msg.reply("✅ Фото успешно отправлено!")
        logger.info(f"Фото от {msg.from_user.full_name}"
                    f"({msg.from_user.id}) → {CHAT_ID}")
    except Exception as e:
        await msg.reply("❌ Ошибка при отправке фото.")
        logger.error(f"Ошибка при пересылке фото: {e}")


# Одиночное видео
@dp.message(F.video & ~F.media_group_id)
async def handle_video(msg: Message):
    try:
        caption = msg.caption or f"🔩 Сборка от {msg.from_user.full_name}⚒️"
        await bot.send_video(
            chat_id=CHAT_ID,
            video=msg.video.file_id, caption=caption)
        await msg.reply("✅ Видео успешно отправлено!")
        logger.info(f"Видео от {msg.from_user.full_name}"
                    f"({msg.from_user.id}) → {CHAT_ID}")
    except Exception as e:
        await msg.reply("❌ Ошибка при отправке видео.")
        logger.error(f"Ошибка при пересылке видео: {e}")


# Фото + Видео
@dp.message(F.media_group_id)
async def handle_album(msg: Message):
    media_group_id = msg.media_group_id

    if media_group_id not in album_buffer:
        album_buffer[media_group_id] = []

    album_buffer[media_group_id].append(msg)

    await asyncio.sleep(2)  # Ожидание в секундах

    if media_group_id in album_buffer:
        album = album_buffer.pop(media_group_id)
        media = []

        for i, msg in enumerate(album):
            caption = (
                f"🔩 Сборка от {msg.from_user.full_name}⚒️"
                if i == 0 else None)
            if msg.photo:
                media.append(InputMediaPhoto(media=msg.photo[-1].file_id,
                                             caption=caption))
            elif msg.video:
                media.append(InputMediaVideo(media=msg.video.file_id,
                                             caption=caption))

        try:
            if media:
                await bot.send_media_group(chat_id=CHAT_ID, media=media)
                await msg.reply(
                    f"✅ Альбом ({len(media)} шт.) успешно отправлен!")
                logger.info(f"Альбом ({len(media)} шт.) "
                            f"от {msg.from_user.full_name}"
                            f"({msg.from_user.id}) → {CHAT_ID}")
        except Exception as e:
            await msg.reply("❌ Ошибка при отправке альбома.")
            logger.error(f"Ошибка при пересылке альбома: {e}")


@dp.message()
async def handle_unsupported(msg: Message):
    if not msg.photo and not msg.video and not msg.media_group_id:
        await msg.reply("⚠️ Бот принимает только фото и видео. "
                        "Он уже запущен и готов к работе ✅ 📌 "
                        "Загрузи фото или видео монтажа, я отправлю их в чат.")
        logger.info(f"Неподдерживаемый файл или символ от "
                    f"{msg.from_user.full_name} ({msg.from_user.id})")


# Запуск бота
async def main():
    logger.info("Бот запущен...")
    await set_bot_commands()
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}")
