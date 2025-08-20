# Bot для пересылки

Бот для автоматического пересылки фото и видео в общий чат монтажников с подписью: 🔩 "Сборка от <имя монтажника в ТГ>⚒️".

## 🚀 Возможности:
- Пересылает:
  - фото 📷
  - видео 🎬
- Логирование действий в logs/bot.log
- Команды:
  - /id - узнать chat_id текущего чата
  - /start - Запуск бота

## ⚙️ Запуск и установка в dev-режиме:
```bash
git clone https://github.com/evgeny-dmitrievich/edk_gts_bot.git
cd edk_gts_bot
```
- Установите и активируйте виртуальное окружение:
```bash
python3 -m venv venv
source venv/bin/activate   # для Linux/Mac
venv\Scripts\activate      # для Windows
```
- Установите зависимости из файла requirements.txt
```bash
pip install -r requirements.txt
```
- Создайте файл .env в корне проекта
**BOT_TOKEN** - токен бота
**CHAT_ID** - id группы, куда пересылать фото и видео (узнать можно командой /id добавив бота в группу)

- В папке с файлом main.py выполните команду:
```bash
python3 main.py 
```
### ⚒️ Технологии:
Python 3.9
Aiogram 3

### ✍ Автор:
Коваленко Евгений

