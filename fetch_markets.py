import httpx
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
import time

today = int(time.time())
sixty_days = int(time.time()) + (120 * 24 * 60 * 60)
KALSHI_API_URL = f"https://external-api.kalshi.com/trade-api/v2/markets?status=open&min_close_ts={today}&max_close_ts={sixty_days}"
POLYMARKET_API_URL = "https://gamma-api.polymarket.com/markets?active=true&closed=false"
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
    
def polymarket_to_market(d):
    if not d.get('active', False): return None
    if d.get('closed', True): return None
    if d.get('volume24hr', 0) < VOLUME_THRESHOLD: return None
    if not d.get('clobTokenIds'): return None
    if not d.get('endDate'): return None
    if not d.get('slug'): return None
    
    outcomes = json.loads(d.get('outcomes', '[]'))
    if outcomes != ["Yes", "No"]:
        return None
        
    close_time = datetime.fromisoformat(d['endDate'].replace('Z', '+00:00'))
    close_ts = close_time.timestamp()
    
    if close_ts < today or close_ts > sixty_days:
        return None

    outcome_prices = json.loads(d.get('outcomePrices', '["0", "0"]'))
    try:
        yes_price = float(outcome_prices[0])
    except (IndexError, ValueError):
        yes_price = 0.0
        
    raw_desc = d.get('description', '')
    clean_desc = raw_desc.split('\n\n')[0] if raw_desc else ''
    
    title_parts = [
        d.get('question', ''),
        clean_desc
    ]
    
    unique_parts = list(dict.fromkeys(p for p in title_parts if p))
    full_question = " - ".join(unique_parts).strip()
    
    return Market(
        platform="polymarket",
        market_id=d['id'],
        question=full_question,
        match_key=d.get('question', ''),
        yes_ask=yes_price, 
        yes_bid=yes_price, 
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
    
    title_parts = [
        d.get('title', ''),
        d.get('yes_sub_title', ''),
        d.get('rules_primary', '')
    ]
    
    unique_parts = []
    for p in title_parts:
        if p and p not in unique_parts:
            unique_parts.append(p)
            
    full_question = " - ".join(unique_parts).strip()
    
    return Market(
        platform="kalshi",
        market_id=d['ticker'],
        question=full_question,
        match_key=d.get('title', ''),
        yes_ask=float(d.get('yes_ask_dollars', 0)),
        yes_bid=float(d.get('yes_bid_dollars', 0)),
        volume_24h=float(d.get('volume_24h_fp', 0)),
        liquidity=float(d.get('liquidity_dollars', 0)),
        close_time=datetime.fromisoformat(d['close_time'].replace('Z', '+00:00')),
        url=f"https://kalshi.com/markets/{d['ticker']}"
    )

def get_polymarket_markets(target):
    markets = []
    offset = 0
    limit = 100
    seen_ids = set()
    begin = int(time.time())

    while len(markets) < target:
        url = f"{POLYMARKET_API_URL}&limit={limit}&offset={offset}"
        
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

        new_markets_from_api = 0
        for d in data:
            market_id = d.get('id')
            if market_id in seen_ids:
                continue
            seen_ids.add(market_id)
            new_markets_from_api += 1
            parsed = polymarket_to_market(d)
            if parsed:
                markets.append(parsed)

        if new_markets_from_api == 0 or len(data) < limit:
            break

        offset += limit

    print(f"Polymarket targets found: {len(markets)} | Time Elapsed: {int(time.time()) - begin} sec")
    return markets

def get_kalshi_markets(target):
    markets = []
    cursor = None
    sleeps = 1
    
    begin = int(time.time())
    with httpx.Client(timeout=10) as client:
        while len(markets) < target:
            url = f"{KALSHI_API_URL}&limit=100"
            if cursor:
                url += f"&cursor={cursor}"
        
            response = client.get(url)

            if response.status_code == 429:
                time.sleep(1)
                sleeps += 1
                continue
            
            data = response.json()
                        
            for m in data['markets']:
                parsed = kalshi_to_market(m)
                if parsed:
                    markets.append(parsed)
        
            cursor = data.get('cursor')
            if not cursor:
                break
    
    print(f"Kalshi targets found: {len(markets)} | Time Elapsed: {(int(time.time()) - begin)} sec")
    return markets

def find_markets(target=2000):
    kalshi = get_kalshi_markets(target=target)
    pm = get_polymarket_markets(target=target)
    return kalshi, pm