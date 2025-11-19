# currency_updater.py
import os
import json
import asyncio
import aiohttp
from datetime import datetime, time, timedelta
from typing import Dict, Any

EXCHANGE_RATES_FILE = "exchange_rates.json"

def load_exchange_rates() -> Dict[str, float]:
    """Загружает курсы валют из файла"""
    if not os.path.exists(EXCHANGE_RATES_FILE):
        # Создаем файл с курсами по умолчанию
        default_rates = {
            "RUB": 90.0,
            "UAH": 38.0,
            "USD": 1.0,
            "last_updated": datetime.now().isoformat()
        }
        with open(EXCHANGE_RATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(default_rates, f, ensure_ascii=False, indent=2)
        return default_rates
    
    try:
        with open(EXCHANGE_RATES_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return {
                "RUB": data.get("RUB", 90.0),
                "UAH": data.get("UAH", 38.0),
                "USD": 1.0
            }
    except Exception as e:
        print(f"Error loading exchange rates: {e}")
        return {"RUB": 90.0, "UAH": 38.0, "USD": 1.0}

async def fetch_exchange_rates() -> Dict[str, Any]:
    """Получает актуальные курсы валют с внешнего API"""
    try:
        async with aiohttp.ClientSession() as session:
            # Пробуем разные API
            apis = [
                'https://api.exchangerate.host/latest?base=USD',
                'https://api.exchangerate-api.com/v4/latest/USD'
            ]
            
            for api_url in apis:
                try:
                    async with session.get(api_url, timeout=10) as response:
                        if response.status == 200:
                            data = await response.json()
                            rates = data.get('rates', {})
                            
                            exchange_rates = {
                                "RUB": rates.get('RUB', 90.0),
                                "UAH": rates.get('UAH', 38.0),
                                "USD": 1.0,
                                "last_updated": datetime.now().isoformat(),
                                "source": api_url
                            }
                            
                            # Сохраняем в файл
                            with open(EXCHANGE_RATES_FILE, 'w', encoding='utf-8') as f:
                                json.dump(exchange_rates, f, ensure_ascii=False, indent=2)
                            
                            print(f"✅ Курсы валют обновлены: 1 USD = {exchange_rates['RUB']} RUB, {exchange_rates['UAH']} UAH")
                            return exchange_rates
                except Exception as e:
                    print(f"❌ Ошибка API {api_url}: {e}")
                    continue
                    
    except Exception as e:
        print(f"❌ Ошибка при получении курсов валют: {e}")
    
    # Возвращаем значения по умолчанию если все API не работают
    default_rates = {
        "RUB": 90.0,
        "UAH": 38.0, 
        "USD": 1.0,
        "last_updated": datetime.now().isoformat(),
        "source": "default"
    }
    return default_rates

async def daily_currency_updater():
    """Ежедневное обновление курсов валют"""
    print("🔄 Запуск ежедневного обновления курсов валют...")
    
    while True:
        try:
            # Обновляем курсы при старте
            await fetch_exchange_rates()
            
            # Ждем 24 часа до следующего обновления
            await asyncio.sleep(24 * 3600)
            
        except Exception as e:
            print(f"❌ Ошибка в daily_currency_updater: {e}")
            await asyncio.sleep(3600)  # Ждем 1 час при ошибке

async def update_currency_rates():
    """Ручное обновление курсов валют"""
    return await fetch_exchange_rates()

# Для тестирования
if __name__ == "__main__":
    print("Текущие курсы:", load_exchange_rates())