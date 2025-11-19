# trade_platform.py
import os
import json
import time
import requests
from typing import Dict, Any, Optional

PRICES_FILE = "data/prices.json"
WEAPONS_DIR = "weapons"
EXCHANGE_RATES_FILE = "data/exchange_rates.json"
PRICE_HISTORY_FILE = "data/price_history.json"
CACHE_TTL = 600

# валюты и их символы
CURRENCY_SYMBOLS = {"USD": "$", "RUB": "₽", "UAH": "₴", "EUR": "€", "CNY": "¥"}

def load_exchange_rates():
    """Загружает курсы валют из файла"""
    try:
        rates_data = safe_load_json(EXCHANGE_RATES_FILE)
        return {
            "RUB": rates_data.get("RUB", 90.0),
            "UAH": rates_data.get("UAH", 38.0),
            "EUR": rates_data.get("EUR", 0.92),
            "CNY": rates_data.get("CNY", 7.2),
            "USD": 1.0
        }
    except Exception as e:
        print(f"Error loading exchange rates: {e}")
        return {"RUB": 90.0, "UAH": 38.0, "EUR": 0.92, "CNY": 7.2, "USD": 1.0}

# Вспомогательные функции
def safe_load_json(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading {path}: {e}")
        return {}

def safe_save_json(path, data):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Error saving {path}: {e}")

def update_exchange_rates(rub_rate: float = None, uah_rate: float = None, eur_rate: float = None, cny_rate: float = None):
    """Обновляет курсы валют вручную"""
    rates = load_exchange_rates()
    
    if rub_rate is not None:
        rates["RUB"] = rub_rate
    if uah_rate is not None:
        rates["UAH"] = uah_rate
    if eur_rate is not None:
        rates["EUR"] = eur_rate
    if cny_rate is not None:
        rates["CNY"] = cny_rate
    
    rates["last_updated"] = time.time()
    
    safe_save_json(EXCHANGE_RATES_FILE, rates)
    print(f"✅ Курсы обновлены: 1 USD = {rates['RUB']} RUB, {rates['UAH']} UAH, {rates['EUR']} EUR, {rates['CNY']} CNY")
    return rates

# Функции поиска файлов
def find_weapon_file(weapon_name: str) -> Optional[str]:
    """Ищет файл оружия в папках weapons"""
    weapon_normalized = weapon_name.lower().replace(" ", "-").replace("|", "").replace("'", "").strip()
    
    categories = ["rifles", "pistols", "smgs", "knives", "gloves", "heavy", "shotguns", "snipers"]
    
    for category in categories:
        category_path = os.path.join(WEAPONS_DIR, category)
        if not os.path.exists(category_path):
            continue
            
        for filename in os.listdir(category_path):
            if filename.endswith('.json'):
                file_weapon = filename.replace('.json', '').lower()
                if (weapon_normalized in file_weapon or 
                    file_weapon in weapon_normalized or
                    weapon_name.lower() in file_weapon):
                    return os.path.join(category_path, filename)
    
    return None

# Функции работы со скинами
def get_skin_data_from_file(weapon_name: str, skin_input: str, wear: str) -> Optional[Dict[str, Any]]:
    """Ищет данные скина в JSON файлах weapons"""
    weapon_file = find_weapon_file(weapon_name)
    if not weapon_file:
        return None
    
    weapon_data = safe_load_json(weapon_file)
    if not weapon_data:
        return None
    
    for skin in weapon_data:
        skin_name = skin.get("name", "")
        
        if (skin_input.lower() == skin_name.lower() or
            skin_input.lower() in skin_name.lower()):
            
            links = skin.get("links", {})
            prices = skin.get("prices", {})
            
            # Возвращаем URL и цену
            if wear in links:
                return {
                    "market_url": links[wear],
                    "skin_name": skin_name,
                    "wear": wear,
                    "price_usd": prices.get(wear, 0)  # Берем цену из локального файла
                }
            else:
                # Берем первый доступный износ
                for available_wear, url in links.items():
                    return {
                        "market_url": url,
                        "skin_name": skin_name,
                        "wear": available_wear,
                        "price_usd": prices.get(available_wear, 0)
                    }
    
    return None

# Функции работы с Steam API (оставляем как fallback)
def fetch_steam_price(market_url: str, currency: str) -> Optional[float]:
    """Получает цену с Steam Market по URL"""
    try:
        if "/market/listings/730/" in market_url:
            market_hash = market_url.split("/market/listings/730/")[1]
            
            currency_codes = {"USD": 1, "RUB": 5, "UAH": 18, "EUR": 3, "CNY": 23}
            code = currency_codes.get(currency, 1)
            
            api_url = f"https://steamcommunity.com/market/priceoverview/?currency={code}&appid=730&market_hash_name={market_hash}"
            
            resp = requests.get(api_url, timeout=10)
            data = resp.json()
            
            if data.get("success") and "lowest_price" in data:
                price_str = data["lowest_price"]
                clean = price_str.replace("$", "").replace("₽", "").replace("₴", "").replace("€", "").replace("¥", "").replace("р.", "").replace(",", ".").strip()
                return float(clean)
                
    except Exception as e:
        print(f"Error fetching Steam price: {e}")
    
    return None

# Функции управления кэшем
def clear_price_cache(skin_name: str = None, wear: str = None, currency: str = None):
    """Очищает кэш цен для конкретного скина или всех скинов"""
    prices_cache = safe_load_json(PRICES_FILE)
    
    if skin_name is None:
        # Очищаем весь кэш
        prices_cache = {}
    else:
        # Очищаем конкретный скин
        key = f"{skin_name}||{wear}||{currency}"
        if key in prices_cache:
            del prices_cache[key]
    
    safe_save_json(PRICES_FILE, prices_cache)
    return True

def clear_all_prices_cache():
    """Очищает весь кэш цен"""
    return clear_price_cache()

# Функции работы с историей цен
def save_price_history(item_name: str, wear: str, currency: str, price: float, url: str = ""):
    """Сохраняет историю цен для анализа трендов"""
    try:
        history = safe_load_json(PRICE_HISTORY_FILE)
        
        key = f"{item_name}||{wear}||{currency}"
        timestamp = int(time.time())
        
        if key not in history:
            history[key] = []
        
        history[key].append({
            "timestamp": timestamp,
            "price": price,
            "url": url
        })
        
        # Храним только последние 100 записей
        if len(history[key]) > 100:
            history[key] = history[key][-100:]
        
        safe_save_json(PRICE_HISTORY_FILE, history)
        
    except Exception as e:
        print(f"Error saving price history: {e}")

def calculate_growth_from_local_history(item_name: str, wear: str, currency: str, current_price: float) -> Dict[str, str]:
    """Рассчитывает рост цен из локальной истории"""
    symbol = CURRENCY_SYMBOLS.get(currency, "$")
    
    try:
        history = safe_load_json(PRICE_HISTORY_FILE)
        key = f"{item_name}||{wear}||{currency}"
        
        if key not in history or len(history[key]) < 2:
            return {
                "24h": "N/A",
                "7d": "N/A", 
                "30d": "N/A"
            }
        
        price_history = history[key]
        now = time.time()
        
        # Находим цены за разные периоды
        price_24h = None
        price_7d = None
        price_30d = None
        
        for entry in reversed(price_history):
            age_hours = (now - entry["timestamp"]) / 3600
            
            if age_hours <= 24 and price_24h is None:
                price_24h = entry["price"]
            if age_hours <= 168 and price_7d is None:  # 7 дней
                price_7d = entry["price"]
            if age_hours <= 720 and price_30d is None:  # 30 дней
                price_30d = entry["price"]
            
            if all([price_24h, price_7d, price_30d]):
                break
        
        growth_data = {}
        
        # Рассчитываем изменения
        if price_24h:
            change = current_price - price_24h
            percent = (change / price_24h) * 100 if price_24h > 0 else 0
            growth_data["24h"] = f"{'+' if change > 0 else ''}{round(change, 2)}{symbol} ({'+' if percent > 0 else ''}{round(percent, 1)}%)"
        
        if price_7d:
            change = current_price - price_7d
            percent = (change / price_7d) * 100 if price_7d > 0 else 0
            growth_data["7d"] = f"{'+' if change > 0 else ''}{round(change, 2)}{symbol} ({'+' if percent > 0 else ''}{round(percent, 1)}%)"
        
        if price_30d:
            change = current_price - price_30d
            percent = (change / price_30d) * 100 if price_30d > 0 else 0
            growth_data["30d"] = f"{'+' if change > 0 else ''}{round(change, 2)}{symbol} ({'+' if percent > 0 else ''}{round(percent, 1)}%)"
        
        # Заполняем недостающие данные
        for period in ["24h", "7d", "30d"]:
            if period not in growth_data:
                growth_data[period] = "N/A"
        
        return growth_data
        
    except Exception as e:
        print(f"Error calculating growth from local history: {e}")
        return {"24h": "N/A", "7d": "N/A", "30d": "N/A"}

def analyze_price_trend(item_name: str, wear: str, currency: str) -> Dict[str, Any]:
    """Анализирует тренд цены на основе истории"""
    try:
        history = safe_load_json(PRICE_HISTORY_FILE)
        key = f"{item_name}||{wear}||{currency}"
        
        if key not in history or len(history[key]) < 5:
            return {"trend": "📊 Недостаточно данных", "confidence": "Низкая"}
        
        prices = [entry["price"] for entry in history[key][-10:]]  # Берем последние 10 записей
        
        if len(prices) < 2:
            return {"trend": "📊 Недостаточно данных", "confidence": "Низкая"}
        
        # Простой анализ тренда
        first_price = prices[0]
        last_price = prices[-1]
        change = last_price - first_price
        percent_change = (change / first_price) * 100 if first_price > 0 else 0
        
        # Определяем тренд
        if percent_change > 5:
            trend = "📈 Сильный рост"
            confidence = "Высокая"
        elif percent_change > 2:
            trend = "📈 Умеренный рост" 
            confidence = "Средняя"
        elif percent_change > -2:
            trend = "➡️ Стабильный"
            confidence = "Средняя"
        elif percent_change > -5:
            trend = "📉 Умеренное падение"
            confidence = "Средняя"
        else:
            trend = "📉 Сильное падение"
            confidence = "Высокая"
        
        return {
            "trend": trend,
            "confidence": confidence,
            "change_percent": round(percent_change, 1)
        }
        
    except Exception as e:
        print(f"Error analyzing price trend: {e}")
        return {"trend": "📊 Ошибка анализа", "confidence": "Низкая"}

# Главная функция
def get_item_price(item_name: str, wear: str = None, currency: str = "RUB", force_refresh: bool = False) -> Dict[str, Any]:
    """Основная функция получения цены скина"""
    prices_cache = safe_load_json(PRICES_FILE)
    now = time.time()
    key = f"{item_name}||{wear}||{currency}"
    
    # Если не принудительное обновление, проверяем кэш
    if not force_refresh and key in prices_cache and (now - prices_cache[key].get("time", 0) < CACHE_TTL):
        cached_data = prices_cache[key]["data"]
        return cached_data
    
    # Парсим название оружия и скина
    if " | " in item_name:
        weapon_name, skin_input = item_name.split(" | ", 1)
        weapon_name = weapon_name.strip()
        skin_input = skin_input.strip()
    else:
        weapon_name = item_name
        skin_input = ""
    
    # Ищем скин в наших данных
    skin_data = get_skin_data_from_file(weapon_name, skin_input, wear)
    
    result_data = {
        "price": None,
        "url": "",
        "growth": {},
        "trend": {"trend": "N/A", "confidence": "N/A"},
        "source": "not_found"
    }
    
    if skin_data:
        market_url = skin_data["market_url"]
        actual_wear = skin_data["wear"]
        price_usd = skin_data["price_usd"]
        
        # Если есть локальная цена, используем её
        if price_usd and price_usd > 0:
            # Конвертируем в нужную валюту
            exchange_rates = load_exchange_rates()
            rate = exchange_rates.get(currency, 1.0)
            final_price = round(price_usd * rate, 2)
            
            result_data = {
                "price": final_price,
                "url": market_url,
                "growth": calculate_growth_from_local_history(item_name, wear, currency, final_price),
                "trend": analyze_price_trend(item_name, wear, currency),
                "source": "local_db"
            }
        
        # Если нет локальной цены, пробуем Steam API
        else:
            usd_price = fetch_steam_price(market_url, "USD")
            
            if usd_price:
                # Конвертируем в нужную валюту
                exchange_rates = load_exchange_rates()
                rate = exchange_rates.get(currency, 1.0)
                final_price = round(usd_price * rate, 2)
                
                result_data = {
                    "price": final_price,
                    "url": market_url,
                    "growth": calculate_growth_from_local_history(item_name, wear, currency, final_price),
                    "trend": analyze_price_trend(item_name, wear, currency),
                    "source": "steam"
                }
        
        # Сохраняем в кэш и историю
        if result_data["price"]:
            prices_cache[key] = {
                "time": now,
                "data": result_data
            }
            safe_save_json(PRICES_FILE, prices_cache)
            
            save_price_history(item_name, wear, currency, result_data["price"], market_url)
    
    return result_data