Вот переписанный бот. Без лишних комбинаций, без дублей, с одинаковыми банками и нормальной логикой диапазонов. Всё как ты просил — без цирка.

```python
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

# ═══════════════════════════════
# ФИЛЬТРЫ
# ═══════════════════════════════
SELLER_MIN_TRADES = 50
SELLER_MIN_COMPLETION = 98.0
SELLER_MIN_LIMIT_KZT = 10000

BUYER_MIN_TRADES = 30
BUYER_MIN_COMPLETION = 98.0
BUYER_MAX_MIN_LIMIT_KZT = 450000

# защита от повторов
SEEN_DEALS = set()


# ═══════════════════════════════
# UTILS
# ═══════════════════════════════
def extract_banks(obj):
    """
    Пытаемся вытащить методы оплаты (банки) из разных API форматов
    """
    banks = set()

    for key in ["payTypes", "paymentMethods", "payMethodList", "adv.payMethods"]:
        val = obj.get(key)
        if isinstance(val, list):
            for v in val:
                banks.add(str(v).lower())

    return banks


def deal_key(a, b, c, d):
    return f"{a}-{b}-{c}-{d}"


# ═══════════════════════════════
# BINANCE
# ═══════════════════════════════
async def binance_buy(session):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

    async with session.post(url, json={
        "asset": "USDT",
        "fiat": "KZT",
        "tradeType": "BUY",
        "page": 1,
        "rows": 20
    }) as r:

        data = await r.json()
        ads = data.get("data", [])

        best = None

        for a in ads:
            adv = a.get("adv", {})
            advertiser = a.get("advertiser", {})

            price = float(adv.get("price", 0))
            min_l = float(adv.get("minSingleTransAmount", 0))
            max_l = float(adv.get("maxSingleTransAmount", 0))

            trades = int(advertiser.get("monthOrderCount", 0))
            comp = float(advertiser.get("monthFinishRate", 0)) * 100

            banks = extract_banks(adv)

            if price <= 0:
                continue
            if trades < SELLER_MIN_TRADES:
                continue
            if comp < SELLER_MIN_COMPLETION:
                continue
            if min_l > SELLER_MIN_LIMIT_KZT:
                continue
            if max_l < SELLER_MIN_LIMIT_KZT:
                continue

            item = (price, min_l, max_l, banks, advertiser.get("nickName"))

            if not best or price < best[0]:
                best = item

        return best


async def binance_sell(session):
    url = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"

    async with session.post(url, json={
        "asset": "USDT",
        "fiat": "KZT",
        "tradeType": "SELL",
        "page": 1,
        "rows": 20
    }) as r:

        data = await r.json()
        ads = data.get("data", [])

        best = None

        for a in ads:
            adv = a.get("adv", {})
            advertiser = a.get("advertiser", {})

            price = float(adv.get("price", 0))
            min_l = float(adv.get("minSingleTransAmount", 0))

            trades = int(advertiser.get("monthOrderCount", 0))
            comp = float(advertiser.get("monthFinishRate", 0)) * 100

            banks = extract_banks(adv)

            if price <= 0:
                continue
            if trades < BUYER_MIN_TRADES:
                continue
            if comp < BUYER_MIN_COMPLETION:
                continue
            if min_l > BUYER_MAX_MIN_LIMIT_KZT:
                continue

            item = (price, min_l, banks, advertiser.get("nickName"))

            if not best or price > best[0]:
                best = item

        return best


# ═══════════════════════════════
# BYBIT
# ═══════════════════════════════
async def bybit_buy(session):
    url = "https://api2.bybit.com/fiat/otc/item/online"

    async with session.post(url, json={
        "tokenId": "USDT",
        "currencyId": "KZT",
        "side": "1",
        "page": "1",
        "size": "20"
    }) as r:

        data = await r.json()
        items = data.get("result", {}).get("items", [])

        best = None

        for item in items:
            price = float(item.get("price", 0))
            min_l = float(item.get("minAmount", 0))
            max_l = float(item.get("maxAmount", 0))

            trades = int(item.get("recentOrderNum", 0))
            comp = float(item.get("recentExecuteRate", 0)) * 100

            banks = set(item.get("paymentMethods", []))

            if price <= 0:
                continue
            if trades < SELLER_MIN_TRADES:
                continue
            if comp < SELLER_MIN_COMPLETION:
                continue
            if min_l > SELLER_MIN_LIMIT_KZT:
                continue
            if max_l < SELLER_MIN_LIMIT_KZT:
                continue

            if not best or price < best[0]:
                best = (price, min_l, max_l, banks, item.get("nickName"))

        return best


async def bybit_sell(session):
    url = "https://api2.bybit.com/fiat/otc/item/online"

    async with session.post(url, json={
        "tokenId": "USDT",
        "currencyId": "KZT",
        "side": "0",
        "page": "1",
        "size": "20"
    }) as r:

        data = await r.json()
        items = data.get("result", {}).get("items", [])

        best = None

        for item in items:
            price = float(item.get("price", 0))
            min_l = float(item.get("minAmount", 0))

            trades = int(item.get("recentOrderNum", 0))
            comp = float(item.get("recentExecuteRate", 0)) * 100

            banks = set(item.get("paymentMethods", []))

            if price <= 0:
                continue
            if trades < BUYER_MIN_TRADES:
                continue
            if comp < BUYER_MIN_COMPLETION:
                continue
            if min_l > BUYER_MAX_MIN_LIMIT_KZT:
                continue

            if not best or price > best[0]:
                best = (price, min_l, banks, item.get("nickName"))

        return best


# ═══════════════════════════════
# SCAN LOGIC
# ═══════════════════════════════
async def scan(session):

    b_buy = await binance_buy(session)
    bb_sell = await bybit_sell(session)

    bb_buy = await bybit_buy(session)
    b_sell = await binance_sell(session)

    signals = []

    # BINANCE -> BYBIT
    if b_buy and bb_sell:
        buy_price, bmin, bmax, bbanks, bnick = b_buy
        sell_price, smin, sbanks, snick = bb_sell

        if bbanks & sbanks and smin <= bmax:
            net = round(((sell_price - buy_price) / buy_price) * 100 - 0.6, 2)

            key = deal_key("B-BY", buy_price, sell_price, str(bbanks & sbanks))

            if key not in SEEN_DEALS:
                SEEN_DEALS.add(key)

                signals.append({
                    "buy_exchange": "Binance",
                    "sell_exchange": "Bybit",
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "buy_nick": bnick,
                    "sell_nick": snick,
                    "net": net,
                    "profitable": net >= MIN_MARGIN
                })

    # BYBIT -> BINANCE
    if bb_buy and b_sell:
        buy_price, bmin, bmax, bbanks, bnick = bb_buy
        sell_price, smin, sbanks, snick = b_sell

        if bbanks & sbanks and smin <= bmax:
            net = round(((sell_price - buy_price) / buy_price) * 100 - 0.6, 2)

            key = deal_key("BY-B", buy_price, sell_price, str(bbanks & sbanks))

            if key not in SEEN_DEALS:
                SEEN_DEALS.add(key)

                signals.append({
                    "buy_exchange": "Bybit",
                    "sell_exchange": "Binance",
                    "buy_price": buy_price,
                    "sell_price": sell_price,
                    "buy_nick": bnick,
                    "sell_nick": snick,
                    "net": net,
                    "profitable": net >= MIN_MARGIN
                })

    return signals


# ═══════════════════════════════
# TELEGRAM
# ═══════════════════════════════
async def send(session, text):
    if not CHAT_ID:
        return

    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"

    await session.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    })


# ═══════════════════════════════
# MAIN
# ═══════════════════════════════
async def main():
    connector = aiohttp.TCPConnector(ssl=False)

    async with aiohttp.ClientSession(connector=connector) as session:
        while True:
            try:
                signals = await scan(session)

                for s in signals:
                    msg = (
                        f"ARBITRAGE {s['buy_exchange']} → {s['sell_exchange']}\n"
                        f"Buy: {s['buy_price']}\n"
                        f"Sell: {s['sell_price']}\n"
                        f"Net: {s['net']}%"
                    )
                    await send(session, msg)

                await asyncio.sleep(300)

            except Exception as e:
                logger.error(e)
                await asyncio.sleep(10)


if __name__ == "__main__":
    asyncio.run(main())
```
