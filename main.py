import asyncio
import aiohttp
import logging
import os
from datetime import datetime

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.environ.get("ARB_BOT_TOKEN", "")
CHAT_ID = None
MIN_MARGIN = 0.5  # Снижен порог — Binance спред обычно 0.5-2%

SELLER_MIN_TRADES = 50
SELLER_MIN_COMPLETION = 98.0
SELLER_MIN_LIMIT_KZT = 10000

BUYER_MIN_TRADES = 30
BUYER_MIN_COMPLETION = 98.0
BUYER_MAX_MIN_LIMIT_KZT = 450000

SEEN_DEALS = set()
SEEN_RESET_TIME = datetime.now()


async def send_message(session, text):
    if not CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    try:
        await session.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown"
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


async def binance_buy(session):
    """Лучший продавец USDT на Binance P2P"""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    try:
        async with session.post(url, json={
            "asset": "USDT", "fiat": "KZT",
            "tradeType": "BUY", "page": 1, "rows": 20,
            "merchantCheck": False
        }, headers={"Content-Type": "application/json"},
           timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            best = None
            for a in data.get("data", []):
                adv = a.get("adv", {})
                advertiser = a.get("advertiser", {})
                price = float(adv.get("price", 0))
                min_l = float(adv.get("minSingleTransAmount", 0))
                max_l = float(adv.get("maxSingleTransAmount", 0))
                trades = int(advertiser.get("monthOrderCount", 0))
                comp = float(advertiser.get("monthFinishRate", 0)) * 100
                nick = advertiser.get("nickName", "?")
                banks = []
                for pm in adv.get("tradeMethods", []):
                    name = pm.get("tradeMethodName") or pm.get("identifier") or ""
                    if name:
                        banks.append(name.strip())
                if price <= 0: continue
                if trades < SELLER_MIN_TRADES: continue
                if comp < SELLER_MIN_COMPLETION: continue
                if min_l > SELLER_MIN_LIMIT_KZT: continue
                if max_l < SELLER_MIN_LIMIT_KZT: continue
                if not best or price < best[0]:
                    best = (price, min_l, max_l, banks, nick, trades, round(comp, 1))
            return best
    except Exception as e:
        logger.error(f"Binance buy error: {e}")
        return None


async def binance_sell(session):
    """Лучший покупатель USDT на Binance P2P"""
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"
    try:
        async with session.post(url, json={
            "asset": "USDT", "fiat": "KZT",
            "tradeType": "SELL", "page": 1, "rows": 20,
            "merchantCheck": False
        }, headers={"Content-Type": "application/json"},
           timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            best = None
            for a in data.get("data", []):
                adv = a.get("adv", {})
                advertiser = a.get("advertiser", {})
                price = float(adv.get("price", 0))
                min_l = float(adv.get("minSingleTransAmount", 0))
                max_l = float(adv.get("maxSingleTransAmount", 0))
                trades = int(advertiser.get("monthOrderCount", 0))
                comp = float(advertiser.get("monthFinishRate", 0)) * 100
                nick = advertiser.get("nickName", "?")
                banks = []
                for pm in adv.get("tradeMethods", []):
                    name = pm.get("tradeMethodName") or pm.get("identifier") or ""
                    if name:
                        banks.append(name.strip())
                if price <= 0: continue
                if trades < BUYER_MIN_TRADES: continue
                if comp < BUYER_MIN_COMPLETION: continue
                if min_l > BUYER_MAX_MIN_LIMIT_KZT: continue
                if not best or price > best[0]:
                    best = (price, min_l, max_l, banks, nick, trades, round(comp, 1))
            return best
    except Exception as e:
        logger.error(f"Binance sell error: {e}")
        return None


async def scan(session):
    global SEEN_DEALS, SEEN_RESET_TIME

    # Сброс кэша каждые 30 минут
    if (datetime.now() - SEEN_RESET_TIME).seconds > 1800:
        SEEN_DEALS = set()
        SEEN_RESET_TIME = datetime.now()
        logger.info("SEEN_DEALS reset")

    buy_data, sell_data = await asyncio.gather(
        binance_buy(session),
        binance_sell(session)
    )

    if not buy_data or not sell_data:
        logger.warning("No data from Binance")
        return []

    buy_price, buy_min, buy_max, buy_banks, buy_nick, buy_trades, buy_comp = buy_data
    sell_price, sell_min, sell_max, sell_banks, sell_nick, sell_trades, sell_comp = sell_data

    net = round(((sell_price - buy_price) / buy_price) * 100 - 0.3, 2)

    logger.info(f"Binance: buy={buy_price} sell={sell_price} net={net}%")

    if net < MIN_MARGIN:
        return []

    # Защита от повторов
    key = f"{round(buy_price, 1)}-{round(sell_price, 1)}"
    if key in SEEN_DEALS:
        return []
    SEEN_DEALS.add(key)

    return [{
        "buy_price": buy_price,
        "sell_price": sell_price,
        "buy_nick": buy_nick,
        "sell_nick": sell_nick,
        "buy_trades": buy_trades,
        "buy_comp": buy_comp,
        "buy_min": buy_min,
        "buy_max": buy_max,
        "buy_banks": buy_banks,
        "sell_trades": sell_trades,
        "sell_comp": sell_comp,
        "sell_min": sell_min,
        "sell_max": sell_max,
        "sell_banks": sell_banks,
        "net": net,
    }]


def fmt_kzt(val):
    return f"{int(val):,}".replace(",", " ")


def format_signal(s):
    buy_banks_str = ", ".join(s["buy_banks"]) if s["buy_banks"] else "—"
    sell_banks_str = ", ".join(s["sell_banks"]) if s["sell_banks"] else "—"
    profit_100 = round((s["sell_price"] - s["buy_price"]) * 100 * 0.997, 0)
    profit_500 = round((s["sell_price"] - s["buy_price"]) * 500 * 0.997, 0)
    work_min = max(s["buy_min"], s["sell_min"])
    work_max = min(s["buy_max"], s["sell_max"]) if s["sell_max"] else s["buy_max"]

    return (
        f"🚨 *СИГНАЛ — Binance P2P KZT*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 *КУПИТЬ USDT*\n"
        f"   Продавец: {s['buy_nick']}\n"
        f"   Цена: `{s['buy_price']} KZT`\n"
        f"   Лимит: `{fmt_kzt(s['buy_min'])} — {fmt_kzt(s['buy_max'])} KZT`\n"
        f"   🏦 Банки: {buy_banks_str}\n"
        f"   ✅ Сделок: {s['buy_trades']} | Рейтинг: {s['buy_comp']}%\n\n"
        f"📤 *ПРОДАТЬ USDT*\n"
        f"   Покупатель: {s['sell_nick']}\n"
        f"   Цена: `{s['sell_price']} KZT`\n"
        f"   Лимит: `{fmt_kzt(s['sell_min'])} — {fmt_kzt(s['sell_max'])} KZT`\n"
        f"   🏦 Банки: {sell_banks_str}\n"
        f"   ✅ Сделок: {s['sell_trades']} | Рейтинг: {s['sell_comp']}%\n\n"
        f"💼 *Рабочий диапазон:*\n"
        f"   `{fmt_kzt(work_min)} — {fmt_kzt(work_max)} KZT`\n\n"
        f"💰 *Чистая маржа: {s['net']}%*\n"
        f"💵 Прибыль со 100 USDT: ~{fmt_kzt(profit_100)} KZT\n"
        f"💵 Прибыль с 500 USDT: ~{fmt_kzt(profit_500)} KZT\n\n"
        f"⚠️ Проверь имя плательщика!\n"
        f"⚠️ Жди реального зачисления!\n\n"
        f"🕐 {datetime.now().strftime('%H:%M:%S %d.%m.%Y')}"
    )


HELP_TEXT = """
🤖 *BINANCE P2P ARB BOT*
━━━━━━━━━━━━━━━━━━━━━━

Команды:
/start — запустить мониторинг
/scan — сканировать прямо сейчас
/rates — текущие курсы и маржа
/debug — полные данные с Binance
/help — помощь

Бот мониторит Binance P2P каждые 5 минут.
Сигнал когда маржа ≥0.5%.
"""


async def handle_command(session, text, chat_id):
    global CHAT_ID
    CHAT_ID = chat_id
    cmd = text.strip().lower().split()[0]

    if cmd == "/start":
        await send_message(session,
            "✅ *Binance P2P Arb Bot запущен!*\n\n"
            "Мониторю Binance P2P каждые 5 минут.\n"
            f"Сигнал когда маржа ≥{MIN_MARGIN}%.\n\n"
            f"Продавцы: {SELLER_MIN_TRADES}+ сделок, {SELLER_MIN_COMPLETION}%+, от {SELLER_MIN_LIMIT_KZT:,} KZT\n"
            f"Покупатели: {BUYER_MIN_TRADES}+ сделок, {BUYER_MIN_COMPLETION}%+\n\n"
            "📊 Напиши /rates чтобы увидеть текущую маржу.\n"
            "⚠️ Bybit временно отключён — API недоступен с US серверов."
        )

    elif cmd == "/rates":
        await send_message(session, "📊 Получаю курсы с Binance...")
        buy_data, sell_data = await asyncio.gather(
            binance_buy(session),
            binance_sell(session)
        )

        msg = f"📊 *ТЕКУЩИЕ КУРСЫ — {datetime.now().strftime('%H:%M:%S')}*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        msg += "🟡 *Binance P2P:*\n"

        if buy_data:
            msg += f"   📥 Купить USDT: `{buy_data[0]} KZT`\n"
            msg += f"   Продавец: {buy_data[4]} | Сделок: {buy_data[5]} | {buy_data[6]}%\n"
            msg += f"   Лимит: {fmt_kzt(buy_data[1])} — {fmt_kzt(buy_data[2])} KZT\n\n"
        else:
            msg += "   📥 Купить: нет данных\n\n"

        if sell_data:
            msg += f"   📤 Продать USDT: `{sell_data[0]} KZT`\n"
            msg += f"   Покупатель: {sell_data[4]} | Сделок: {sell_data[5]} | {sell_data[6]}%\n"
            msg += f"   Лимит: {fmt_kzt(sell_data[1])} — {fmt_kzt(sell_data[2])} KZT\n\n"
        else:
            msg += "   📤 Продать: нет данных\n\n"

        if buy_data and sell_data:
            net = round(((sell_data[0] - buy_data[0]) / buy_data[0]) * 100 - 0.3, 2)
            icon = "🟢" if net >= MIN_MARGIN else "🔴"
            lim_ok = "✅" if sell_data[1] <= buy_data[2] else "❌ лимит несовместим"
            msg += f"📈 *Маржа: {icon} `{net}%`* {lim_ok}\n"
            msg += f"_Порог сигнала: {MIN_MARGIN}%_"

        await send_message(session, msg)

    elif cmd == "/scan":
        await send_message(session, "🔍 Сканирую Binance P2P...")
        signals = await scan(session)
        if not signals:
            buy_data, sell_data = await asyncio.gather(
                binance_buy(session),
                binance_sell(session)
            )
            if buy_data and sell_data:
                net = round(((sell_data[0] - buy_data[0]) / buy_data[0]) * 100 - 0.3, 2)
                await send_message(session,
                    f"😔 Нет сигнала.\n"
                    f"Текущая маржа: `{net}%` (порог {MIN_MARGIN}%)\n"
                    f"Купить: {buy_data[0]} KZT | Продать: {sell_data[0]} KZT\n\n"
                    "Продолжаю мониторинг каждые 5 минут."
                )
            else:
                await send_message(session, "❌ Нет данных с Binance.")
        else:
            for s in signals:
                await send_message(session, format_signal(s))

    elif cmd == "/debug":
        await send_message(session, "🔧 Получаю полные данные...")
        buy_data, sell_data = await asyncio.gather(
            binance_buy(session),
            binance_sell(session)
        )

        msg = "🔧 *DEBUG — Binance P2P*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        if buy_data:
            msg += (f"*Продавец (BUY):*\n"
                    f"   Цена: {buy_data[0]} KZT\n"
                    f"   Лимит: {fmt_kzt(buy_data[1])} — {fmt_kzt(buy_data[2])} KZT\n"
                    f"   Ник: {buy_data[4]} | Сделок: {buy_data[5]} | {buy_data[6]}%\n"
                    f"   Банки: {', '.join(buy_data[3]) or '—'}\n\n")
        else:
            msg += "*Продавец (BUY):* нет данных\n\n"

        if sell_data:
            msg += (f"*Покупатель (SELL):*\n"
                    f"   Цена: {sell_data[0]} KZT\n"
                    f"   Лимит: {fmt_kzt(sell_data[1])} — {fmt_kzt(sell_data[2])} KZT\n"
                    f"   Ник: {sell_data[4]} | Сделок: {sell_data[5]} | {sell_data[6]}%\n"
                    f"   Банки: {', '.join(sell_data[3]) or '—'}\n\n")
        else:
            msg += "*Покупатель (SELL):* нет данных\n\n"

        if buy_data and sell_data:
            net = round(((sell_data[0] - buy_data[0]) / buy_data[0]) * 100 - 0.3, 2)
            lim = "✅" if sell_data[1] <= buy_data[2] else "❌"
            msg += f"*Маржа:* {net}% | Лимиты: {lim}"

        await send_message(session, msg)

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
                    await handle_command(session, text, CHAT_ID)
        await asyncio.sleep(1)


async def monitor_loop(session):
    await asyncio.sleep(30)
    while True:
        if CHAT_ID:
            try:
                signals = await scan(session)
                if signals:
                    for s in signals:
                        await send_message(session, format_signal(s))
                    logger.info(f"Signal sent: {signals[0]['net']}%")
            except Exception as e:
                logger.error(f"Monitor error: {e}")
        await asyncio.sleep(300)


async def main():
    if not TOKEN:
        logger.error("ARB_BOT_TOKEN не установлен!")
        return
    logger.info(f"Binance P2P Arb Bot запущен | порог {MIN_MARGIN}%")
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        await asyncio.gather(
            polling_loop(session),
            monitor_loop(session)
        )


if __name__ == "__main__":
    asyncio.run(main())
