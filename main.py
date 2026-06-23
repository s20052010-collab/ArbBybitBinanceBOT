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


async def bybit_buy(session):
    url = "https://api2.bybit.com/fiat/otc/item/online"
    try:
        async with session.post(url, json={
            "tokenId": "USDT", "currencyId": "KZT",
            "side": "1", "page": "1", "size": "20"
        }, headers={"Content-Type": "application/json"},
           timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            best = None
            for item in data.get("result", {}).get("items", []):
                price = float(item.get("price", 0))
                min_l = float(item.get("minAmount", 0))
                max_l = float(item.get("maxAmount", 0))
                trades = int(item.get("recentOrderNum", 0))
                comp_raw = float(item.get("recentExecuteRate", 0))
                comp = comp_raw * 100 if comp_raw <= 1 else comp_raw
                nick = item.get("nickName", "?")
                banks = []
                for pm in item.get("payments", []):
                    name = pm.get("name") or ""
                    if name:
                        banks.append(name.strip())
                if not banks:
                    for pm in item.get("paymentMethods", []):
                        if isinstance(pm, str):
                            banks.append(pm.strip())
                        elif isinstance(pm, dict):
                            name = pm.get("name") or pm.get("paymentType") or ""
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
        logger.error(f"Bybit buy error: {e}")
        return None


async def bybit_sell(session):
    url = "https://api2.bybit.com/fiat/otc/item/online"
    try:
        async with session.post(url, json={
            "tokenId": "USDT", "currencyId": "KZT",
            "side": "0", "page": "1", "size": "20"
        }, headers={"Content-Type": "application/json"},
           timeout=aiohttp.ClientTimeout(total=10)) as r:
            data = await r.json()
            best = None
            for item in data.get("result", {}).get("items", []):
                price = float(item.get("price", 0))
                min_l = float(item.get("minAmount", 0))
                max_l = float(item.get("maxAmount", 0))
                trades = int(item.get("recentOrderNum", 0))
                comp_raw = float(item.get("recentExecuteRate", 0))
                comp = comp_raw * 100 if comp_raw <= 1 else comp_raw
                nick = item.get("nickName", "?")
                banks = []
                for pm in item.get("payments", []):
                    name = pm.get("name") or ""
                    if name:
                        banks.append(name.strip())
                if not banks:
                    for pm in item.get("paymentMethods", []):
                        if isinstance(pm, str):
                            banks.append(pm.strip())
                        elif isinstance(pm, dict):
                            name = pm.get("name") or pm.get("paymentType") or ""
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
        logger.error(f"Bybit sell error: {e}")
        return None


def check_pair(buy_data, sell_data, buy_ex, sell_ex):
    global SEEN_DEALS, SEEN_RESET_TIME

    if (datetime.now() - SEEN_RESET_TIME).seconds > 1800:
        SEEN_DEALS = set()
        SEEN_RESET_TIME = datetime.now()
        logger.info("SEEN_DEALS reset")

    if not buy_data or not sell_data:
        return None

    buy_price, buy_min, buy_max, buy_banks, buy_nick, buy_trades, buy_comp = buy_data
    sell_price, sell_min, sell_max, sell_banks, sell_nick, sell_trades, sell_comp = sell_data

    if sell_min > buy_max:
        return None

    net = round(((sell_price - buy_price) / buy_price) * 100 - 0.6, 2)

    key = f"{buy_ex}-{sell_ex}-{round(buy_price, 1)}-{round(sell_price, 1)}"
    if key in SEEN_DEALS:
        return None
    SEEN_DEALS.add(key)

    return {
        "buy_exchange": buy_ex,
        "sell_exchange": sell_ex,
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
        "profitable": net >= MIN_MARGIN
    }


async def scan(session):
    b_buy, b_sell, bb_buy, bb_sell = await asyncio.gather(
        binance_buy(session),
        binance_sell(session),
        bybit_buy(session),
        bybit_sell(session)
    )

    signals = []

    r = check_pair(b_buy, bb_sell, "Binance", "Bybit")
    if r:
        signals.append(r)

    r = check_pair(bb_buy, b_sell, "Bybit", "Binance")
    if r:
        signals.append(r)

    return signals


def fmt_kzt(val):
    return f"{int(val):,}".replace(",", " ")


def format_signal(s):
    buy_banks_str = ", ".join(s["buy_banks"]) if s["buy_banks"] else "—"
    sell_banks_str = ", ".join(s["sell_banks"]) if s["sell_banks"] else "—"
    profit_100 = round((s["sell_price"] - s["buy_price"]) * 100 * 0.994, 0)
    profit_500 = round((s["sell_price"] - s["buy_price"]) * 500 * 0.994, 0)
    icon = "🚨" if s["profitable"] else "📊"
    work_min = max(s["buy_min"], s["sell_min"])
    work_max = min(s["buy_max"], s["sell_max"]) if s["sell_max"] else s["buy_max"]

    return (
        f"{icon} *АРБИТРАЖ: {s['buy_exchange']} → {s['sell_exchange']}*\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"📥 *КУПИТЬ на {s['buy_exchange']}*\n"
        f"   Продавец: {s['buy_nick']}\n"
        f"   Цена: `{s['buy_price']} KZT`\n"
        f"   Лимит: `{fmt_kzt(s['buy_min'])} — {fmt_kzt(s['buy_max'])} KZT`\n"
        f"   🏦 Банки: {buy_banks_str}\n"
        f"   ✅ Сделок: {s['buy_trades']} | Рейтинг: {s['buy_comp']}%\n\n"
        f"📤 *ПРОДАТЬ на {s['sell_exchange']}*\n"
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
🤖 *ARB BYBIT × BINANCE BOT*
━━━━━━━━━━━━━━━━━━━━━━

Команды:
/start — запустить мониторинг
/scan — сканировать прямо сейчас
/rates — текущие курсы и маржа
/debug — полные данные с бирж
/help — помощь

Бот мониторит каждые 5 минут.
Сигнал когда маржа ≥1%.
Только Binance ↔ Bybit.
"""


async def handle_command(session, text, chat_id):
    global CHAT_ID
    CHAT_ID = chat_id
    cmd = text.strip().lower().split()[0]

    if cmd == "/start":
        await send_message(session,
            "✅ *ArbBybitBinanceBOT запущен!*\n\n"
            "Мониторю Binance ↔ Bybit P2P каждые 5 минут.\n"
            "Сигнал когда маржа ≥1%.\n\n"
            f"Продавцы: {SELLER_MIN_TRADES}+ сделок, {SELLER_MIN_COMPLETION}%+, от {SELLER_MIN_LIMIT_KZT:,} KZT\n"
            f"Покупатели: {BUYER_MIN_TRADES}+ сделок, {BUYER_MIN_COMPLETION}%+\n\n"
            "📊 Напиши /rates чтобы увидеть текущую маржу."
        )

    elif cmd == "/rates":
        await send_message(session, "📊 Получаю курсы...")
        b_buy, b_sell, bb_buy, bb_sell = await asyncio.gather(
            binance_buy(session),
            binance_sell(session),
            bybit_buy(session),
            bybit_sell(session)
        )

        msg = f"📊 *ТЕКУЩИЕ КУРСЫ — {datetime.now().strftime('%H:%M:%S')}*\n"
        msg += "━━━━━━━━━━━━━━━━━━━━━━\n\n"

        b_buy_price = b_buy[0] if b_buy else None
        b_sell_price = b_sell[0] if b_sell else None
        bb_buy_price = bb_buy[0] if bb_buy else None
        bb_sell_price = bb_sell[0] if bb_sell else None

        msg += f"🟡 *Binance:*\n"
        msg += f"   Купить USDT: `{b_buy_price or '—'} KZT` ({b_buy[4] if b_buy else '—'})\n"
        msg += f"   Продать USDT: `{b_sell_price or '—'} KZT` ({b_sell[4] if b_sell else '—'})\n\n"

        msg += f"🔵 *Bybit:*\n"
        msg += f"   Купить USDT: `{bb_buy_price or '—'} KZT` ({bb_buy[4] if bb_buy else '—'})\n"
        msg += f"   Продать USDT: `{bb_sell_price or '—'} KZT` ({bb_sell[4] if bb_sell else '—'})\n\n"

        msg += "📈 *Маржа:*\n"
        if b_buy_price and bb_sell_price:
            net = round(((bb_sell_price - b_buy_price) / b_buy_price) * 100 - 0.6, 2)
            lim = "✅" if bb_sell and b_buy and bb_sell[1] <= b_buy[2] else "❌ лимит"
            icon = "🟢" if net >= MIN_MARGIN else "🔴"
            msg += f"   {icon} Binance→Bybit: `{net}%` {lim}\n"

        if bb_buy_price and b_sell_price:
            net = round(((b_sell_price - bb_buy_price) / bb_buy_price) * 100 - 0.6, 2)
            lim = "✅" if b_sell and bb_buy and b_sell[1] <= bb_buy[2] else "❌ лимит"
            icon = "🟢" if net >= MIN_MARGIN else "🔴"
            msg += f"   {icon} Bybit→Binance: `{net}%` {lim}\n"

        msg += f"\n_Порог сигнала: {MIN_MARGIN}%_"
        await send_message(session, msg)

    elif cmd == "/scan":
        await send_message(session, "🔍 Сканирую Binance и Bybit...")
        signals = await scan(session)
        if not signals:
            await send_message(session,
                "😔 Нет сигналов — маржа < 1% или лимиты не совместимы.\n"
                "Продолжаю мониторинг каждые 5 минут.\n\n"
                "Напиши /rates чтобы увидеть текущую маржу."
            )
        else:
            for s in signals:
                await send_message(session, format_signal(s))

    elif cmd == "/debug":
        await send_message(session, "🔧 Получаю полные данные...")
        b_buy, b_sell, bb_buy, bb_sell = await asyncio.gather(
            binance_buy(session),
            binance_sell(session),
            bybit_buy(session),
            bybit_sell(session)
        )

        msg = "🔧 *DEBUG — полные данные*\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

        for label, d in [
            ("Binance BUY (продавец)", b_buy),
            ("Bybit SELL (покупатель)", bb_sell),
            ("Bybit BUY (продавец)", bb_buy),
            ("Binance SELL (покупатель)", b_sell),
        ]:
            if d:
                msg += (f"*{label}:*\n"
                        f"   Цена: {d[0]} KZT\n"
                        f"   Лимит: {fmt_kzt(d[1])} — {fmt_kzt(d[2])} KZT\n"
                        f"   Ник: {d[4]} | Сделок: {d[5]} | Рейтинг: {d[6]}%\n"
                        f"   Банки: {', '.join(d[3]) or '—'}\n\n")
            else:
                msg += f"*{label}:* нет данных\n\n"

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
                profitable = [s for s in signals if s["profitable"]]
                if profitable:
                    for s in profitable:
                        await send_message(session, format_signal(s))
                    logger.info(f"Signals sent: {len(profitable)}")
                else:
                    best_nets = []
                    b_buy, b_sell, bb_buy, bb_sell = await asyncio.gather(
                        binance_buy(session),
                        binance_sell(session),
                        bybit_buy(session),
                        bybit_sell(session)
                    )
                    if b_buy and bb_sell:
                        net = round(((bb_sell[0] - b_buy[0]) / b_buy[0]) * 100 - 0.6, 2)
                        best_nets.append(f"B→BB:{net}%")
                    if bb_buy and b_sell:
                        net = round(((b_sell[0] - bb_buy[0]) / bb_buy[0]) * 100 - 0.6, 2)
                        best_nets.append(f"BB→B:{net}%")
                    logger.info(f"No signals. {' | '.join(best_nets)}")
            except Exception as e:
                logger.error(f"Monitor error: {e}")
        await asyncio.sleep(300)


async def main():
    if not TOKEN:
        logger.error("ARB_BOT_TOKEN не установлен!")
        return
    logger.info("ArbBybitBinanceBOT запущен")
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        await asyncio.gather(
            polling_loop(session),
            monitor_loop(session)
        )


if __name__ == "__main__":
    asyncio.run(main())
