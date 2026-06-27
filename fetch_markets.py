import httpx
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
import time

today = int(time.time())
one_twenty_days = today + (120 * 24 * 60 * 60)
KALSHI_API_URL = f"https://external-api.kalshi.com/trade-api/v2/markets?status=open&min_close_ts={today}&max_close_ts={one_twenty_days}"
POLYMARKET_GAMMA_BASE = "https://gamma-api.polymarket.com/markets?active=true&closed=false"
VOLUME_THRESHOLD = 1

@dataclass
class Market:
    platform: str
    market_id: str
    question: str
    match_key: str
    yes_ask: float
    yes_bid: float
    volume_24h: float
    liquidity: float
    close_time: datetime
    url: str
    clob_token_ids: list = field(default_factory=list)

    @property
    def no_ask(self) -> float:
        return round(1 - self.yes_bid, 4)

    @property
    def no_bid(self) -> float:
        return round(1 - self.yes_ask, 4)


def polymarket_gamma_to_market(d):
    if not d.get('active', False): return None
    if d.get('closed', True): return None
    if d.get('volume24hr', 0) < VOLUME_THRESHOLD: return None
    if not d.get('clobTokenIds'): return None
    if not d.get('endDate'): return None
    if not d.get('slug'): return None

    outcomes = json.loads(d.get('outcomes', '[]'))
    
    is_binary = outcomes == ["Yes", "No"]
    is_neg_risk = d.get('negRisk', False)
    if not is_binary and not is_neg_risk:
        return None

    if is_neg_risk:
        yes_ask = float(d.get('bestAsk') or 0)
        yes_bid = float(d.get('bestBid') or 0)
        if yes_ask == 0 and yes_bid == 0:
            return None
    else:
        outcome_prices = json.loads(d.get('outcomePrices', '["0", "0"]'))
        try:
            yes_ask = float(outcome_prices[0])
            yes_bid = yes_ask
        except (IndexError, ValueError):
            yes_ask = yes_bid = 0.0

    close_time = datetime.fromisoformat(d['endDate'].replace('Z', '+00:00'))
    close_ts = close_time.timestamp()
    if close_ts < today or close_ts > one_twenty_days:
        return None

    raw_desc = d.get('description', '')
    clean_desc = raw_desc.split('\n\n')[0] if raw_desc else ''
    unique_parts = list(dict.fromkeys(p for p in [d.get('question', ''), clean_desc] if p))

    return Market(
        platform="polymarket",
        market_id=d['id'],
        question=" - ".join(unique_parts).strip(),
        match_key=d.get('question', ''),
        yes_ask=yes_ask,
        yes_bid=yes_bid,
        volume_24h=d.get('volume24hr', 0),
        liquidity=d.get('liquidityNum', 0),
        close_time=close_time,
        url=f"https://polymarket.com/event/{d['slug']}",
        clob_token_ids=json.loads(d['clobTokenIds'])
    )


def kalshi_to_market(d):
    if d.get('mve_collection_ticker'): return None
    if d.get('primary_participant_key'): return None
    if float(d.get('volume_24h_fp', '0')) < VOLUME_THRESHOLD: return None

    title = d.get('title', '')
    sub_title = d.get('yes_sub_title', '')

    if sub_title and sub_title.lower() not in title.lower():
        match_key = f"{title} - {sub_title}"
    else:
        match_key = title

    unique_parts = []
    for p in [title, sub_title, d.get('rules_primary', '')]:
        if p and p not in unique_parts:
            unique_parts.append(p)

    return Market(
        platform="kalshi",
        market_id=d['ticker'],
        question=" - ".join(unique_parts).strip(),
        match_key=match_key,
        yes_ask=float(d.get('yes_ask_dollars', 0)),
        yes_bid=float(d.get('yes_bid_dollars', 0)),
        volume_24h=float(d.get('volume_24h_fp', 0)),
        liquidity=float(d.get('liquidity_dollars', 0)),
        close_time=datetime.fromisoformat(d['close_time'].replace('Z', '+00:00')),
        url=f"https://kalshi.com/markets/{d['ticker']}"
    )


def get_polymarket_gamma_markets(target=500):
    seen_ids = set()
    markets = []
    begin = int(time.time())

    sort_orders = ["volume24hr", "liquidity", "startDate", "endDate"]

    for sort in sort_orders:
        url_base = f"{POLYMARKET_GAMMA_BASE}&order={sort}&ascending=false"
        offset = 0
        limit = 100

        while len(markets) < target:
            url = f"{url_base}&limit={limit}&offset={offset}"

            retries = 0
            while retries < 3:
                try:
                    response = httpx.get(url, timeout=30)
                    break
                except httpx.ReadTimeout:
                    retries += 1
                    print(f"  Polymarket timeout (attempt {retries}/3), retrying...")
                    time.sleep(2 ** retries)
            else:
                print("  Polymarket fetch failed after 3 attempts, stopping")
                break

            if response.status_code != 200:
                break

            data = response.json()
            if not data:
                break

            new = 0
            for d in data:
                market_id = d.get('id')
                if market_id in seen_ids:
                    continue
                seen_ids.add(market_id)
                new += 1
                parsed = polymarket_gamma_to_market(d)
                if parsed:
                    markets.append(parsed)

            if new == 0 or len(data) < limit:
                break

            offset += limit

        print(f"  After sort={sort}: {len(markets)} unique markets")
        if len(markets) >= target:
            break

    print(f"Polymarket targets found: {len(markets)} | Time Elapsed: {int(time.time()) - begin} sec")
    return markets


def get_kalshi_markets(target):
    markets = []
    cursor = None
    begin = int(time.time())

    with httpx.Client(timeout=10) as client:
        while len(markets) < target:
            url = f"{KALSHI_API_URL}&limit=100"
            if cursor:
                url += f"&cursor={cursor}"

            response = client.get(url)

            if response.status_code == 429:
                time.sleep(1)
                continue

            data = response.json()

            for m in data['markets']:
                parsed = kalshi_to_market(m)
                if parsed:
                    markets.append(parsed)

            cursor = data.get('cursor')
            if not cursor:
                break

    print(f"Kalshi targets found: {len(markets)} | Time Elapsed: {int(time.time()) - begin} sec")
    return markets


def load_confirmed_matches():
    import os
    if not os.path.exists("confirmed_matches.json"):
        return {}
    with open("confirmed_matches.json") as f:
        content = f.read().strip()
        return json.loads(content) if content else {}


def find_markets(target=2000):
    kalshi = get_kalshi_markets(target=target)
    pm = get_polymarket_gamma_markets(target=target)
    print(f"Total: {len(kalshi)} Kalshi | {len(pm)} Polymarket")
    return kalshi, pm
