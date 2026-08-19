from models import MarketClient, Market
from datetime import datetime
import httpx
import asyncio
import time


today = int(time.time())
one_twenty_days = today + (120 * 24 * 60 * 60)
KALSHI_API_URL = f"https://external-api.kalshi.com/trade-api/v2/markets?status=open&min_close_ts={today}&max_close_ts={one_twenty_days}"
VOLUME_THRESHOLD = 1
SLEEP_TIMER = 2.5

class KalshiClient(MarketClient):
    def __init__(self):
        self.http_client = httpx.Client(timeout=10)
        self.async_client = httpx.AsyncClient(timeout=10)
    
    async def list_all_markets(self, sleep):
        markets = []
        cursor = None
        begin = int(time.time())
        count_429 = 0
    
        while True:
            url = f"{KALSHI_API_URL}&limit=1000"
            if cursor:
                url += f"&cursor={cursor}"

            response = await self.async_client.get(url)

            if response.status_code == 429:
                count_429 += 1
                await asyncio.sleep(sleep)
                continue

            data = response.json()

            for m in data['markets']:
                parsed = self.kalshi_to_market(m)
                if parsed:
                    markets.append(parsed)
                    
            cursor = data.get('cursor')
            if not cursor:
                break
    
                
        return markets, count_429, float(time.time()) - begin
    
    async def market_by_id(self, market_id: str):
        pass
    
    async def _connect(self):
        pass
    
    async def _disconnect(self):
        pass
    
    def kalshi_to_market(self, d):
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