import os
import json
import asyncio
import logging
import signal
import sys
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from trade_platform import get_item_price, clear_all_prices_cache

# ---------- Логирование ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ---------- Настройки ----------
load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise SystemExit("TOKEN not set in .env")

bot = Bot(token=TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# ✅ ОБНОВЛЕННЫЕ ПУТИ ДЛЯ HEROKU
# Создаем папку data если её нет
if not os.path.exists('data'):
    os.makedirs('data')

# Файлы данных теперь в папке data/
INVENTORY_FILE = "data/inventory.json"
USER_SETTINGS_FILE = "data/user_settings.json"
WEAPON_LIST_FILE = "weapons_list.json"  # Оставляем в корне
PRICES_FILE = "data/prices.json"


# справочники
WEARS = ["Factory New", "Minimal Wear", "Field-Tested", "Well-Worn", "Battle-Scarred"]
CATEGORIES = {
    "Ножи": "knives",
    "Перчатки": "gloves",
    "Пистолеты": "pistols",
    "ПП": "smgs",
    "Винтовки": "rifles",
    "Снайперки": "snipers",
    "Дробовики": "shotguns",
    "Пулеметы": "heavy"
}
CURRENCY_SYMBOL = {"RUB": "₽", "USD": "$", "UAH": "₴", "EUR": "€", "CNY": "¥"}

# ---------- Утилиты ----------
def safe_load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            s = f.read().strip()
            return json.loads(s) if s else {}
    except Exception as e:
        logger.warning("safe_load_json error for %s: %s", path, e)
        return {}

def safe_save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.exception("safe_save_json error for %s: %s", path, e)

def load_inventory():
    return safe_load_json(INVENTORY_FILE)

def save_inventory(inv):
    safe_save_json(INVENTORY_FILE, inv)

def load_settings():
    return safe_load_json(USER_SETTINGS_FILE)

def save_settings(s):
    safe_save_json(USER_SETTINGS_FILE, s)

def load_weapons_list():
    data = safe_load_json(WEAPON_LIST_FILE)
    if not data:
        return {
            "Винтовки": ["AK-47", "M4A4", "M4A1-S", "AUG", "SG 553", "Galil AR", "FAMAS"],
            "ПП": ["MAC-10", "MP9", "MP7", "UMP-45", "P90", "PP-Bizon"],
            "Пистолеты": ["Glock-18", "USP-S", "Desert Eagle", "P250", "Five-SeveN", "CZ75-Auto"],
            "Снайперки": ["AWP", "SSG 08", "SCAR-20", "G3SG1"],
            "Дробовики": ["Nova", "XM1014", "MAG-7", "Sawed-Off"],
            "Пулеметы": ["Negev", "M249"],
            "Ножи": ["Karambit", "Bayonet", "Butterfly Knife", "M9 Bayonet"],
            "Перчатки": ["Sport Gloves", "Driver Gloves", "Hand Wraps", "Moto Gloves"]
        }
    return data

WEAPON_LISTS = load_weapons_list()

# Загружаем translations с защитой от ошибок
try:
    from translations import TRANSLATIONS
except ImportError:
    logger.warning("translations.py not found, using empty dict")
    TRANSLATIONS = {}

# ---------- Клавиатуры ----------
def main_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Инвентарь")],
            [KeyboardButton(text="Настройки")]
        ],
        resize_keyboard=True
    )
    return kb

def inventory_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Добавить скин"), KeyboardButton(text="Удалить скин")],
            [KeyboardButton(text="Мой инвентарь"), KeyboardButton(text="Обновить цены")],
            [KeyboardButton(text="Настройки")]
        ],
        resize_keyboard=True
    )
    return kb

def category_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=c)] for c in CATEGORIES.keys()] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    return kb

def currency_menu_kb():
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🇷🇺 RUB"), KeyboardButton(text="🇺🇸 USD")],
            [KeyboardButton(text="🇺🇦 UAH"), KeyboardButton(text="🇪🇺 EUR")],
            [KeyboardButton(text="🇨🇳 CNY"), KeyboardButton(text="Отмена")]
        ],
        resize_keyboard=True
    )
    return kb

# ---------- FSM ----------
class AddSkinStates(StatesGroup):
    waiting_category = State()
    waiting_weapon = State()
    waiting_name = State()
    waiting_wear = State()
    waiting_confirmation = State()
    waiting_amount = State()

class DeleteSkinStates(StatesGroup):
    choosing_skin = State()

class SettingsStates(StatesGroup):
    choosing_currency = State()

# ---------- Async helper ----------
async def run_blocking(func, *args):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args))

# ---------- Глобальная отмена ----------
@dp.message(F.text.casefold() == "отмена")
async def cancel_anywhere(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state:
        await state.clear()
        await message.answer("❌ Действие отменено.", reply_markup=main_menu_kb())
    else:
        await message.answer("❌ Отменять нечего.", reply_markup=main_menu_kb())

# ---------- Хендлеры ----------
@dp.message(F.text == "/start")
async def cmd_start(message: types.Message):
    await message.answer("👋 Привет! Главное меню:", reply_markup=main_menu_kb())

# --- Настройки ---
@dp.message(F.text == "Настройки")
async def open_settings(message: types.Message, state: FSMContext):
    await message.answer("⚙️ Меню настроек:", reply_markup=currency_menu_kb())
    await state.set_state(SettingsStates.choosing_currency)

@dp.message(SettingsStates.choosing_currency)
async def choose_currency(message: types.Message, state: FSMContext):
    text = message.text.strip()
    mapping = {
        "🇷🇺 RUB": "RUB", 
        "🇺🇸 USD": "USD", 
        "🇺🇦 UAH": "UAH",
        "🇪🇺 EUR": "EUR",
        "🇨🇳 CNY": "CNY"
    }
    if text not in mapping:
        await message.answer("Выберите валюту кнопкой.")
        return
    settings = load_settings()
    settings[str(message.from_user.id)] = {"currency": mapping[text]}
    save_settings(settings)
    await message.answer(f"✅ Валюта установлена: {mapping[text]}", reply_markup=main_menu_kb())
    await state.clear()

# --- Меню инвентаря ---
@dp.message(F.text == "Инвентарь")
async def inventory_menu(message: types.Message):
    await message.answer("📦 Меню инвентаря:", reply_markup=inventory_menu_kb())

# --- Показ инвентаря ---
@dp.message(F.text == "Мой инвентарь")
async def show_inventory(message: types.Message):
    inv = load_inventory()
    user_id = str(message.from_user.id)
    user_inv = inv.get(user_id, {})
    
    print(f"🔍 Инвентарь пользователя {user_id}: {len(user_inv)} скинов")
    
    if not user_inv:
        await message.answer("Инвентарь пуст.")
        return

    settings = load_settings()
    currency = settings.get(user_id, {}).get("currency", "RUB")
    symbol = CURRENCY_SYMBOL.get(currency, "₽")

    # Показываем сообщение о начале загрузки
    loading_msg = await message.answer(f"🔍 Загружаю {len(user_inv)} скинов...")

    # Создаем задачи для параллельного получения цен
    tasks = []
    items_data = []
    
    for name, data in user_inv.items():
        wear = data.get("wear")
        amount = data.get("amount", 1)
        
        # Создаем задачу для каждого скина
        task = run_blocking(get_item_price, name, wear, currency)
        tasks.append(task)
        items_data.append((name, data, amount))

    # Запускаем ВСЕ запросы ПАРАЛЛЕЛЬНО
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Удаляем сообщение о загрузке
    try:
        await bot.delete_message(chat_id=message.chat.id, message_id=loading_msg.message_id)
    except:
        pass

    total_value = 0.0
    updated_count = 0
    total_items = len(user_inv)

    # Обрабатываем и показываем результаты
    for i, (result, (name, data, amount)) in enumerate(zip(results, items_data)):
        wear = data.get("wear")
        
        if isinstance(result, Exception):
            # Сообщение об ошибке
            skin_text = f"{name} — {wear} ×{amount} шт.\n💰 Ошибка загрузки"
            await message.answer(skin_text)
            continue

        if not result or result.get("price") is None:
            # Сообщение без цены
            skin_text = f"{name} — {wear} ×{amount} шт.\n💰 Нет данных"
            
            # Кнопка "Открыть в Steam"
            url = result.get("url", "") if result else ""
            if url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📤 Открыть в Steam", url=url)]
                ])
                await message.answer(skin_text, reply_markup=kb)
            else:
                await message.answer(skin_text)
            continue

        price = result.get("price")
        url = result.get("url", "")
        growth = result.get("growth", {})
        trend = result.get("trend", {})

        try:
            price_num = float(price) if price is not None else None
        except (TypeError, ValueError):
            price_num = None

        if price_num is not None and price_num > 0:
            total = round(price_num * amount, 2)
            total_value += total
            price_display = f"💵 {price_num}{symbol}"
            updated_count += 1
            
            # Форматируем информацию о скине
            skin_text = f"{name} — {wear} ×{amount} шт.\n{price_display}"
            
            # ⬇️⬇️⬇️ АНАЛИЗ ЦЕН (24h/7d/30d) ОСТАЕТСЯ ⬇️⬇️⬇️
            # Добавляем РЕАЛЬНУЮ информацию о росте
            growth_lines = []
            for period in ["24h", "7d", "30d"]:
                if period in growth and growth[period] != "N/A":
                    growth_value = growth[period]
                    growth_lines.append(f"{period}: {growth_value}")
            
            if growth_lines:
                skin_text += "\n📊 " + " | ".join(growth_lines)
            
            # ⬇️⬇️⬇️ ТРЕНД ОСТАЕТСЯ ⬇️⬇️⬇️
            if trend and trend.get("trend") != "N/A":
                skin_text += f"\n{trend['trend']} (уверенность: {trend['confidence']})"
            
            # ⬇️⬇️⬇️ ИСТОЧНИКИ УБРАНЫ - ЭТОГО БЛОКА НЕТ ⬇️⬇️⬇️
            
            # Отправляем сообщение с кнопкой
            if url:
                kb = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📤 Открыть в Steam", url=url)]
                ])
                await message.answer(skin_text, reply_markup=kb)
            else:
                await message.answer(skin_text)

    # Итоговое сообщение
    if total_value > 0:
        summary = f"📈 Итог анализа: {updated_count}/{total_items} скинов\n💵 Общая стоимость: {round(total_value, 2)}{symbol}"
        await message.answer(summary)
    else:
        await message.answer(f"📊 Итог: 0/{total_items} скинов с ценами")
        
# --- Обновление цен ---
@dp.message(F.text == "Обновить цены")
async def refresh_prices(message: types.Message):
    user_id = str(message.from_user.id)
    
    inv = load_inventory()
    user_inv = inv.get(user_id, {})
    
    if not user_inv:
        await message.answer("❌ Инвентарь пуст.", reply_markup=inventory_menu_kb())
        return
    
    settings = load_settings()
    currency = settings.get(user_id, {}).get("currency", "RUB")
    symbol = CURRENCY_SYMBOL.get(currency, "₽")
    
    # Очищаем кэш для принудительного обновления
    clear_all_prices_cache()
    
    total_items = len(user_inv)
    
    # Показываем сообщение о начале обновления
    progress_msg = await message.answer(f"🔄 Начинаю обновление {total_items} скинов...\n⏳ Это займет ~{total_items * 2} секунд")
    
    updated_count = 0
    total_value = 0.0
    errors = []
    
    # Создаем задачи для параллельного выполнения
    tasks = []
    items_data = []
    
    for name, data in user_inv.items():
        wear = data.get("wear")
        amount = data.get("amount", 1)
        
        # Создаем задачу для каждого скина
        task = run_blocking(get_item_price, name, wear, currency, True)
        tasks.append(task)
        items_data.append((name, data, amount))
    
    # Запускаем ВСЕ запросы ПАРАЛЛЕЛЬНО
    try:
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Обрабатываем результаты
        for i, (result, (name, data, amount)) in enumerate(zip(results, items_data)):
            # Обновляем прогресс каждые 5 скинов
            if i % 5 == 0:
                try:
                    await bot.edit_message_text(
                        chat_id=message.chat.id,
                        message_id=progress_msg.message_id,
                        text=f"🔄 Обработано {i}/{total_items} скинов..."
                    )
                except:
                    pass
            
            if isinstance(result, Exception):
                errors.append(f"{name}: {str(result)}")
                continue
                
            if result and result.get("price"):
                price = result.get("price")
                try:
                    price_num = float(price) if price is not None else None
                    if price_num is not None and price_num > 0:
                        total = round(price_num * amount, 2)
                        total_value += total
                        updated_count += 1
                except (TypeError, ValueError):
                    pass
    
    except Exception as e:
        errors.append(f"Ошибка обновления: {str(e)}")
    
    # Формируем итоговое сообщение
    result_text = f"✅ Обновление завершено!\n\n"
    result_text += f"📊 Обновлено: {updated_count}/{total_items} скинов\n"
    result_text += f"💵 Общая стоимость: {round(total_value, 2)}{symbol}\n"
    
    if errors:
        result_text += f"❌ Ошибок: {len(errors)}\n"
        if len(errors) <= 3:  # Показываем только первые 3 ошибки
            result_text += "\n".join([f"• {error}" for error in errors[:3]])
        else:
            result_text += f"• {errors[0]}\n• ... и еще {len(errors) - 1} ошибок"
    
    # Обновляем итоговое сообщение
    try:
        await bot.edit_message_text(
            chat_id=message.chat.id,
            message_id=progress_msg.message_id,
            text=result_text
        )
    except:
        await message.answer(result_text, reply_markup=inventory_menu_kb())

# --- Добавление скина ---
@dp.message(F.text == "Добавить скин")
async def add_skin_start(message: types.Message, state: FSMContext):
    await message.answer("Выберите класс оружия:", reply_markup=category_menu_kb())
    await state.set_state(AddSkinStates.waiting_category)

@dp.message(AddSkinStates.waiting_category)
async def add_choose_category(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text not in CATEGORIES:
        await message.answer("Неверная категория. Попробуй ещё раз.")
        return
    await state.update_data(category=text)
    weapons = WEAPON_LISTS.get(text, [])
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=w)] for w in weapons] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите оружие:", reply_markup=kb)
    await state.set_state(AddSkinStates.waiting_weapon)

@dp.message(AddSkinStates.waiting_weapon)
async def add_choose_weapon(message: types.Message, state: FSMContext):
    text = message.text.strip()
    await state.update_data(weapon=text)
    await message.answer(
        "Введите название скина:",
        reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
    )
    await state.set_state(AddSkinStates.waiting_name)

@dp.message(AddSkinStates.waiting_name)
async def add_enter_name(message: types.Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    weapon = data.get("weapon", "")
    
    # Ищем совпадение в translations
    found_translation = None
    if TRANSLATIONS:
        for key, translation_data in TRANSLATIONS.items():
            if (translation_data.get("weapon", "").lower() == weapon.lower() and 
                any(alias.lower() == text.lower() for alias in translation_data.get("ru", []))):
                found_translation = translation_data
                break
    
    if found_translation:
        # Нашли совпадение, используем английское название
        full_name = f"{weapon} | {found_translation['en']}"
        await state.update_data(name=full_name, original_input=text)
        
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=w)] for w in WEARS] + [[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer("Выберите износ:", reply_markup=kb)
        await state.set_state(AddSkinStates.waiting_wear)
    else:
        # Не нашли совпадение, используем введенное название
        full_name = f"{weapon} | {text}"
        await state.update_data(name=full_name, original_input=text)
        
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=w)] for w in WEARS] + [[KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
        await message.answer("Выберите износ:", reply_markup=kb)
        await state.set_state(AddSkinStates.waiting_wear)

@dp.message(AddSkinStates.waiting_wear)
async def add_choose_wear(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text not in WEARS:
        await message.answer("Выберите износ кнопкой.")
        return
    
    await state.update_data(wear=text)
    
    # Получаем все данные для подтверждения
    data = await state.get_data()
    weapon = data.get("weapon", "")
    skin_name = data.get("name", "").replace(f"{weapon} | ", "")
    original_input = data.get("original_input", "")
    wear = data.get("wear", "")
    full_name = f"{weapon} | {skin_name}"
    
    # Получаем текущую цену для отображения
    settings = load_settings()
    user_id = str(message.from_user.id)
    currency = settings.get(user_id, {}).get("currency", "RUB")
    symbol = CURRENCY_SYMBOL.get(currency, "₽")
    
    price_info = ""
    try:
        item = await run_blocking(get_item_price, full_name, wear, currency)
        if item and item.get("price"):
            price = item.get("price")
            price_info = f"\n$Текущая цена: {price}{symbol}"
    except Exception as e:
        logger.error("Error getting price for confirmation: %s", e)
    
    # Создаем клавиатуру подтверждения
    kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=full_name)],
            [KeyboardButton(text="Изменить")]
        ],
        resize_keyboard=True
    )
    
    # Проверяем, было ли исправлено название
    if original_input.lower() != skin_name.lower():
        confirmation_text = (
            f"Вы имели ввиду:\n\n"
            f"🔫 Оружие: {weapon}\n"
            f"🎨 Скин: {skin_name}\n"
            f"📊 Износ: {wear}"
        )
    else:
        confirmation_text = (
            f"Проверьте данные:\n\n"
            f"🔫 Оружие: {weapon}\n"
            f"🎨 Скин: {skin_name}\n"
            f"📊 Износ: {wear}"
        )
    
    confirmation_text += price_info
    confirmation_text += f"\n\nЕсли всё верно - нажмите на название скина для подтверждения:\n{full_name}"
    
    await message.answer(confirmation_text, reply_markup=kb)
    await state.set_state(AddSkinStates.waiting_confirmation)

@dp.message(AddSkinStates.waiting_confirmation)
async def add_confirm_skin(message: types.Message, state: FSMContext):
    text = message.text.strip()
    data = await state.get_data()
    expected_name = data.get("name", "")
    
    if text == "Изменить":
        # Возвращаемся к вводу названия скина
        await message.answer(
            "Введите название скина:",
            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Отмена")]], resize_keyboard=True)
        )
        await state.set_state(AddSkinStates.waiting_name)
        return
    
    if text != expected_name:
        await message.answer("Пожалуйста, подтвердите добавление скина, нажав на его название.")
        return
    
    # Переходим к вводу количества
    await message.answer(
        "Введите количество предметов:",
        reply_markup=ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="1")], [KeyboardButton(text="Отмена")]],
            resize_keyboard=True
        )
    )
    await state.set_state(AddSkinStates.waiting_amount)

@dp.message(AddSkinStates.waiting_amount)
async def add_enter_amount(message: types.Message, state: FSMContext):
    text = message.text.strip()
    try:
        amount = max(1, int(text))
    except ValueError:
        amount = 1
    data = await state.get_data()
    user_id = str(message.from_user.id)
    inv = load_inventory()
    if user_id not in inv:
        inv[user_id] = {}
    name = data.get("name")
    wear = data.get("wear")
    inv[user_id][name] = {"wear": wear, "amount": amount}
    save_inventory(inv)
    
    # Показываем финальную информацию с ценой
    settings = load_settings()
    currency = settings.get(user_id, {}).get("currency", "RUB")
    symbol = CURRENCY_SYMBOL.get(currency, "₽")
    
    price_info = ""
    try:
        item = await run_blocking(get_item_price, name, wear, currency)
        if item and item.get("price"):
            price = item.get("price")
            total_price = round(price * amount, 2)
            price_info = f"\n💵Цена: {price}{symbol} × {amount} = {total_price}{symbol}"
    except Exception as e:
        logger.error("Error getting final price: %s", e)
    
    await message.answer(
        f"✅ Добавлено: {name} ({wear}) — {amount} шт.{price_info}",
        reply_markup=inventory_menu_kb()
    )
    await state.clear()

# --- Удаление скина ---    
@dp.message(F.text == "Удалить скин")
async def delete_start(message: types.Message, state: FSMContext):
    inv = load_inventory()
    user_id = str(message.from_user.id)
    user_inv = inv.get(user_id, {})
    if not user_inv:
        await message.answer("Инвентарь пуст.")
        return
    kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=n)] for n in user_inv.keys()] + [[KeyboardButton(text="Отмена")]],
        resize_keyboard=True
    )
    await message.answer("Выберите скин для удаления:", reply_markup=kb)
    await state.set_state(DeleteSkinStates.choosing_skin)

@dp.message(DeleteSkinStates.choosing_skin)
async def delete_choose(message: types.Message, state: FSMContext):
    text = message.text.strip()
    inv = load_inventory()
    user_id = str(message.from_user.id)
    user_inv = inv.get(user_id, {})
    if text in user_inv:
        del user_inv[text]
        inv[user_id] = user_inv
        save_inventory(inv)
        await message.answer(f"✅ Удалено: {text}", reply_markup=inventory_menu_kb())
    else:
        await message.answer("Такого скина нет.", reply_markup=inventory_menu_kb())
    await state.clear()

# --- Назад ---
@dp.message(F.text.casefold() == "назад")
async def go_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("📦 Меню инвентаря:", reply_markup=inventory_menu_kb())

# ---------- Polling ----------
async def run_polling():
    tries = 0
    while True:
        try:
            logger.info("Starting polling...")
            await dp.start_polling(bot, timeout=30)
        except Exception as e:
            tries += 1
            logger.exception("Polling error: %s", e)
            wait = min(30, 1 + tries * 2)
            await asyncio.sleep(wait)
            continue
        break

if __name__ == "__main__":
    try:
        asyncio.run(run_polling())
    except KeyboardInterrupt:
        logger.info("Stopped by user")