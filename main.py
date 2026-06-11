import asyncio
import aiohttp
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("ARB_BOT_TOKEN", "")
CHAT_ID = None
MIN_MARGIN = 1.0

# ═══════════════════════════════════════
# ФИЛЬТРЫ ПРОДАВЦОВ (покупаем USDT)
# ═══════════════════════════════════════
SELLER_MIN_TRADES = 50
SELLER_MIN_COMPLETION = 98.0
SELLER_MIN_LIMIT_KZT = 10000

# ═══════════════════════════════════════
# ФИЛЬТРЫ ПОКУПАТЕЛЕЙ (продаём USDT)
# ═══════════════════════════════════════
BUYER_MIN_TRADES = 30
BUYER_MIN_COMPLETION = 98.0
BUYER_MAX_MIN_LIMIT_KZT = 450000


# ════════════════════════════════════════
# BINANCE P2P
# ════════════════════════════════════════

async def binance_buy_price(session):
    """Лучшая цена покупки USDT на Binance (мы платим — ищем минимум)"""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    try:
        async with session.post(url, json={
            "asset": "USDT", "fiat": "KZT",
            "tradeType": "BUY", "page": 1, "rows": 20,
            "merchantCheck": False,
            "transAmount": str(SELLER_MIN_LIMIT_KZT)
        }, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json()
                ads = data.get("data", [])
                filtered = []
                for a in ads:
                    adv = a.get("adv", {})
                    advertiser = a.get("advertiser", {})
                    price = float(adv.get("price", 0))
                    min_limit = float(adv.get("minSingleTransAmount", 0))
                    max_limit = float(adv.get("maxSingleTransAmount", 0))
                    month_trades = int(advertiser.get("monthOrderCount", 0))
                    completion = float(advertiser.get("monthFinishRate", 0)) * 100
                    nick = advertiser.get("nickName", "?")
                    if price <= 0: continue
                    if min_limit > SELLER_MIN_LIMIT_KZT: continue
                    if max_limit < SELLER_MIN_LIMIT_KZT: continue
                    if month_trades < SELLER_MIN_TRADES: continue
                    if completion < SELLER_MIN_COMPLETION: continue
                    filtered.append((price, nick, month_trades, round(completion, 1)))
                if filtered:
                    filtered.sort(key=lambda x: x[0])
                    return filtered[0][0], filtered[0][1], filtered[0][2], filtered[0][3], "Binance"
    except Exception as e:
        logger.error(f"Binance buy error: {e}")
    return None, None, None, None, "Binance"


async def binance_sell_price(session):
    """Лучшая цена продажи USDT на Binance (мы получаем — ищем максимум)"""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    try:
        async with session.post(url, json={
            "asset": "USDT", "fiat": "KZT",
            "tradeType": "SELL", "page": 1, "rows": 20,
            "merchantCheck": False,
        }, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json()
                ads = data.get("data", [])
                filtered = []
                for a in ads:
                    adv = a.get("adv", {})
                    advertiser = a.get("advertiser", {})
                    price = float(adv.get("price", 0))
                    min_limit = float(adv.get("minSingleTransAmount", 0))
                    max_limit = float(adv.get("maxSingleTransAmount", 0))
                    month_trades = int(advertiser.get("monthOrderCount", 0))
                    completion = float(advertiser.get("monthFinishRate", 0)) * 100
                    nick = advertiser.get("nickName", "?")
                    if price <= 0: continue
                    if min_limit > BUYER_MAX_MIN_LIMIT_KZT: continue
                    if month_trades < BUYER_MIN_TRADES: continue
                    if completion < BUYER_MIN_COMPLETION: continue
                    filtered.append((price, nick, month_trades, round(completion, 1)))
                if filtered:
                    filtered.sort(key=lambda x: x[0], reverse=True)
                    return filtered[0][0], filtered[0][1], filtered[0][2], filtered[0][3], "Binance"
    except Exception as e:
        logger.error(f"Binance sell error: {e}")
    return None, None, None, None, "Binance"


# ════════════════════════════════════════
# BYBIT P2P
# ════════════════════════════════════════

async def bybit_buy_price(session):
    """Лучшая цена покупки USDT на Bybit"""
    url = "https://api2.bybit.com/fiat/otc/item/online"
    try:
        async with session.post(url, json={
            "tokenId": "USDT", "currencyId": "KZT",
            "side": "1",  # 1 = buy
            "page": "1", "size": "20",
            "amount": str(SELLER_MIN_LIMIT_KZT)
        }, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json()
                items = data.get("result", {}).get("items", [])
                filtered = []
                for item in items:
                    price = float(item.get("price", 0))
                    min_limit = float(item.get("minAmount", 0))
                    max_limit = float(item.get("maxAmount", 0))
                    nick = item.get("nickName", "?")
                    # Bybit использует recentOrderNum и recentExecuteRate
                    month_trades = int(item.get("recentOrderNum", 0))
                    completion_str = item.get("recentExecuteRate", "0")
                    completion = float(completion_str) * 100 if float(completion_str) <= 1 else float(completion_str)
                    if price <= 0: continue
                    if min_limit > SELLER_MIN_LIMIT_KZT: continue
                    if max_limit < SELLER_MIN_LIMIT_KZT: continue
                    if month_trades < SELLER_MIN_TRADES: continue
                    if completion < SELLER_MIN_COMPLETION: continue
                    filtered.append((price, nick, month_trades, round(completion, 1)))
                if filtered:
                    filtered.sort(key=lambda x: x[0])
                    return filtered[0][0], filtered[0][1], filtered[0][2], filtered[0][3], "Bybit"
    except Exception as e:
        logger.error(f"Bybit buy error: {e}")
    return None, None, None, None, "Bybit"


async def bybit_sell_price(session):
    """Лучшая цена продажи USDT на Bybit"""
    url = "https://api2.bybit.com/fiat/otc/item/online"
    try:
        async with session.post(url, json={
            "tokenId": "USDT", "currencyId": "KZT",
            "side": "0",  # 0 = sell
            "page": "1", "size": "20"
        }, headers={"Content-Type": "application/json"}, timeout=aiohttp.ClientTimeout(total=10)) as r:
            if r.status == 200:
                data = await r.json()
                items = data.get("result", {}).get("items", [])
                filtered = []
                for item in items:
                    price = float(item.get("price", 0))
                    min_limit = float(item.get("minAmount", 0))
                    nick = item.get("nickName", "?")
                    month_trades = int(item.get("recentOrderNum", 0))
                    completion_str = item.get("recentExecuteRate", "0")
                    completion = float(completion_str) * 100 if float(completion_str) <= 1 else float(completion_str)
                    if price <= 0: continue
                    if min_limit > BUYER_MAX_MIN_LIMIT_KZT: continue
                    if month_trades < BUYER_MIN_TRADES: continue
                    if completion < BUYER_MIN_COMPLETION: continue
                    filtered.append((price, nick, month_trades, round(completion, 1)))
                if filtered:
                    filtered.sort(key=lambda x: x[0], reverse=True)
                    return filtered[0][0], filtered[0][1], filtered[0][2], filtered[0][3], "Bybit"
    except Exception as e:
        logger.error(f"Bybit sell error: {e}")
    return None, None, None, None, "Bybit"


# ════════════════════════════════════════
# СКАНИРОВАНИЕ
# ════════════════════════════════════════

async def scan(session):
    """Сканирует все 4 комбинации: Binance→Bybit, Bybit→Binance, Binance→Binance, Bybit→Bybit"""

    # Получаем цены со всех площадок параллельно
    b_buy_price, b_buy_nick, b_buy_trades, b_buy_compl, _ = await binance_buy_price(session)
    await asyncio.sleep(0.5)
    b_sell_price, b_sell_nick, b_sell_trades, b_sell_compl, _ = await binance_sell_price(session)
    await asyncio.sleep(0.5)
    bb_buy_price, bb_buy_nick, bb_buy_trades, bb_buy_compl, _ = await bybit_buy_price(session)
    await asyncio.sleep(0.5)
    bb_sell_price, bb_sell_nick, bb_sell_trades, bb_sell_compl, _ = await bybit_sell_price(session)

    signals = []

    # Комбинация 1: Купить на Binance → Продать на Bybit
    if b_buy_price and bb_sell_price:
        gross = ((bb_sell_price - b_buy_price) / b_buy_price) * 100
        net = round(gross - 0.6, 2)
        signals.append({
            "buy_exchange": "Binance", "sell_exchange": "Bybit",
            "buy_price": b_buy_price, "sell_price": bb_sell_price,
            "buy_nick": b_buy_nick, "sell_nick": bb_sell_nick,
            "buy_trades": b_buy_trades, "buy_compl": b_buy_compl,
            "sell_trades": bb_sell_trades, "sell_compl": bb_sell_compl,
            "net": net, "profitable": net >= MIN_MARGIN
        })

    # Комбинация 2: Купить на Bybit → Продать на Binance
    if bb_buy_price and b_sell_price:
        gross = ((b_sell_price - bb_buy_price) / bb_buy_price) * 100
        net = round(gross - 0.6, 2)
        signals.append({
            "buy_exchange": "Bybit", "sell_exchange": "Binance",
            "buy_price": bb_buy_price, "sell_price": b_sell_price,
            "buy_nick": bb_buy_nick, "sell_nick": b_sell_nick,
            "buy_trades": bb_buy_trades, "buy_compl": bb_buy_compl,
            "sell_trades": b_sell_trades, "sell_compl": b_sell_compl,
            "net": net, "profitable": net >= MIN_MARGIN
        })

    # Комбинация 3: Binance → Binance
    if b_buy_price and b_sell_price:
        gross = ((b_sell_price - b_buy_price) / b_buy_price) * 100
        net = round(gross - 0.6, 2)
        signals.append({
            "buy_exchange": "Binance", "sell_exchange": "Binance",
            "buy_price": b_buy_price, "sell_price": b_sell_price,
            "buy_nick": b_buy_nick, "sell_nick": b_sell_nick,
            "buy_trades": b_buy_trades, "buy_compl": b_buy_compl,
            "sell_trades": b_sell_trades, "sell_compl": b_sell_compl,
            "net": net, "profitable": net >= MIN_MARGIN
        })

    # Комбинация 4: Bybit → Bybit
    if bb_buy_price and bb_sell_price:
        gross = ((bb_sell_price - bb_buy_price) / bb_buy_price) * 100
        net = round(gross - 0.6, 2)
        signals.append({
            "buy_exchange": "Bybit", "sell_exchange": "Bybit",
            "buy_price": bb_buy_price, "sell_price": bb_sell_price,
            "buy_nick": bb_buy_nick, "sell_nick": bb_sell_nick,
            "buy_trades": bb_buy_trades, "buy_compl": bb_buy_compl,
            "sell_trades": bb_sell_trades, "sell_compl": bb_sell_compl,
            "net": net, "profitable": net >= MIN_MARGIN
        })

    return signals


def format_signal(s):
    profit_100 = round((s["sell_price"] - s["buy_price"]) * 100 * 0.994, 2)
    profit_1000 = round((s["sell_price"] - s["buy_price"]) * 1000 * 0.994, 2)
    return (
        f"🚨 *АРБИТРАЖ: {s['buy_exchange']} → {s['sell_exchange']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 *КУПИТЬ на {s['buy_exchange']}*\n"
        f"   Цена: `{s['buy_price']} KZT`\n"
        f"   Продавец: {s['buy_nick']}\n"
        f"   ✅ Сделок: {s['buy_trades']} | Рейтинг: {s['buy_compl']}%\n\n"
        f"📤 *ПРОДАТЬ на {s['sell_exchange']}*\n"
        f"   Цена: `{s['sell_price']} KZT`\n"
        f"   Покупатель: {s['sell_nick']}\n"
        f"   ✅ Сделок: {s['sell_trades']} | Рейтинг: {s['sell_compl']}%\n\n"
        f"💰 *Чистая маржа: {s['net']}%*\n"
        f"💵 Прибыль со 100 USDT: ~{profit_100} KZT\n"
        f"💵 Прибыль с 1000 USDT: ~{profit_1000} KZT\n\n"
        f"⚠️ Проверь имя плательщика!\n"
        f"⚠️ Жди реального зачисления!\n\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
    )


def format_rates(signals):
    text = f"📊 *КУРСЫ USDT — {datetime.now().strftime('%H:%M')}*\n"
    text += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
    for s in signals:
        icon = "🟢" if s["profitable"] else "🔴"
        text += f"{icon} *{s['buy_exchange']} → {s['sell_exchange']}*\n"
        text += f"  📥 Купить: `{s['buy_price']} KZT`\n"
        text += f"  📤 Продать: `{s['sell_price']} KZT`\n"
        text += f"  💰 Маржа: *{s['net']}%*\n\n"
    return text


# ════════════════════════════════════════
# TELEGRAM
# ════════════════════════════════════════

async def send_message(session, text):
    if not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        await session.post(url, json={
            "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"
        })
    except Exception as e:
        logger.error(f"Send error: {e}")


async def get_updates(session, offset=0):
    url = f"https://api.telegram.org/bot{TOKEN}/getUpdates"
    try:
        async with session.get(url, params={"offset": offset, "timeout": 30}) as r:
            data = await r.json()
            return data.get("result", [])
    except:
        return []


HELP_TEXT = """
🤖 *ARB BYBIT × BINANCE BOT*
━━━━━━━━━━━━━━━━━━━━━━

Команды:
/start — запустить мониторинг
/scan — сканировать сейчас
/rates — текущие курсы
/filters — текущие фильтры
/safety — правила безопасности
/help — помощь

Бот мониторит Binance и Bybit P2P каждые 5 минут.
Сигнал когда маржа ≥1%.
"""

SAFETY_TEXT = """
🛡 *ПРАВИЛА БЕЗОПАСНОСТИ*
━━━━━━━━━━━━━━━━━━━━━━

✅ ВСЕГДА:
• Ждать реального зачисления в банке
• Проверять имя отправителя = имя на бирже
• Работать только через escrow биржи

❌ НИКОГДА:
• Не отпускать USDT по скрину
• Не принимать деньги от третьих лиц
• Не делать сделки в Telegram вне биржи

⚠️ ЛИМИТЫ:
• Неделя 1: 1 сделка/день, до 200 USDT
• Неделя 2: до 2 сделок, до 500 USDT
• После 20+ сделок — масштабировать
"""


def filters_text():
    return (
        f"⚙️ *ТЕКУЩИЕ ФИЛЬТРЫ*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 *ПРОДАВЦЫ* (покупаем USDT):\n"
        f"   • Сделок: {SELLER_MIN_TRADES}+\n"
        f"   • Рейтинг: {SELLER_MIN_COMPLETION}%+\n"
        f"   • Лимит от: {SELLER_MIN_LIMIT_KZT:,} KZT\n\n"
        f"📤 *ПОКУПАТЕЛИ* (продаём USDT):\n"
        f"   • Сделок: {BUYER_MIN_TRADES}+\n"
        f"   • Рейтинг: {BUYER_MIN_COMPLETION}%+\n"
        f"   • Мин. лимит не выше: {BUYER_MAX_MIN_LIMIT_KZT:,} KZT\n\n"
        f"📊 *Площадки:* Binance P2P + Bybit P2P\n"
        f"💱 *Валюта:* KZT\n"
    )


async def handle_command(session, text):
    global CHAT_ID
    cmd = text.strip().lower()

    if cmd == "/start":
        await send_message(session,
            "✅ *ArbBybitBinanceBOT запущен!*\n\n"
            "Мониторю Binance и Bybit P2P каждые 5 минут.\n"
            "Сигнал когда маржа ≥1%\n\n"
            + filters_text()
        )

    elif cmd == "/scan":
        await send_message(session, "🔍 Сканирую Binance и Bybit... подожди 30 сек")
        signals = await scan(session)
        if not signals:
            await send_message(session, "❌ Не удалось получить данные. Попробуй позже.")
            return
        profitable = [s for s in signals if s["profitable"]]
        if profitable:
            profitable.sort(key=lambda x: x["net"], reverse=True)
            for s in profitable:
                await send_message(session, format_signal(s))
        else:
            best = max(signals, key=lambda x: x["net"])
            await send_message(session,
                f"😔 Прибыльных связок нет.\n"
                f"Лучшая маржа: {best['net']}% ({best['buy_exchange']} → {best['sell_exchange']})\n"
                "Продолжаю мониторинг каждые 5 минут."
            )

    elif cmd == "/rates":
        await send_message(session, "📊 Получаю курсы...")
        signals = await scan(session)
        if signals:
            await send_message(session, format_rates(signals))
        else:
            await send_message(session, "❌ Не удалось получить данные.")

    elif cmd == "/filters":
        await send_message(session, filters_text())

    elif cmd == "/safety":
        await send_message(session, SAFETY_TEXT)

    elif cmd == "/help":
        await send_message(session, HELP_TEXT)


async def polling_loop(session):
    offset = 0
    while True:
        updates = await get_updates(session, offset)
        for update in updates:
            offset = update["update_id"] + 1
            msg = update.get("message", {})
            if msg:
                global CHAT_ID
                CHAT_ID = msg["chat"]["id"]
                text = msg.get("text", "")
                if text.startswith("/"):
                    await handle_command(session, text)
        await asyncio.sleep(1)


async def monitor_loop(session):
    await asyncio.sleep(30)
    while True:
        if CHAT_ID:
            try:
                signals = await scan(session)
                profitable = [s for s in signals if s["profitable"]]
                if profitable:
                    profitable.sort(key=lambda x: x["net"], reverse=True)
                    for s in profitable:
                        await send_message(session, format_signal(s))
                    logger.info(f"Signals sent: {len(profitable)}")
                else:
                    best_net = max((s["net"] for s in signals), default=0)
                    logger.info(f"No signals. Best: {best_net:.2f}%")
            except Exception as e:
                logger.error(f"Monitor error: {e}")
        await asyncio.sleep(300)


async def main():
    if not TOKEN:
        logger.error("TOKEN не установлен! Установи ARB_BOT_TOKEN")
        return

    logger.info("ArbBybitBinanceBOT запущен | Binance + Bybit | KZT")
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        await asyncio.gather(
            polling_loop(session),
            monitor_loop(session)
        )


if __name__ == "__main__":
    asyncio.run(main())
