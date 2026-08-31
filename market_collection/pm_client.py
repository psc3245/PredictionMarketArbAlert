from models import Market, MarketClient
from datetime import datetime
import httpx
import asyncio
import time
import json

PM_URL = f"https://gamma-api.polymarket.com/markets/keyset"

class PMClient(MarketClient):
    def __init__(self):
        self.http_client = httpx.Client(timeout=10)
        self.async_client = httpx.AsyncClient(timeout=10)
        
    async def get_order_book(self):
        pass
    
    async def list_all_markets(self):
        markets = []
        next_cursor = None
        begin = int(time.time())
        count_429 = 0
        seen_cursors = set()
        page = 0

        while len(markets) < 5000:
            page += 1
            url = f"{PM_URL}?limit=100&closed=false"

            if next_cursor:
                url += f"&after_cursor={next_cursor}"

            response = await self.async_client.get(url)

            if response.status_code == 429:
                print(f"[pm_client] 429 rate limited (count={count_429 + 1}), sleeping")
                count_429 += 1
                await asyncio.sleep(1)
                continue

            data = response.json()
            raw_count = len(data.get("markets", []))
            kept_before = len(markets)

            for m in data.get("markets", []):
                new = self.pm_clob_to_market(m)
                if new:
                    markets.append(new)

            next_cursor = data.get("next_cursor")

            # print(
            #     f"[pm_client] page {page} | raw={raw_count} "
            #     f"kept={len(markets) - kept_before} cumulative={len(markets)} "
            #     f"next_cursor={next_cursor!r}"
            # )

            if next_cursor and next_cursor in seen_cursors:
                print(
                    f"[pm_client] WARNING: cursor {next_cursor!r} seen before "
                    f"on page {page} - pagination may be stuck in a loop"
                )
            seen_cursors.add(next_cursor)

            if not next_cursor:
                break

        print(
            f"[pm_client] done: {len(markets)} markets kept across "
            f"{page} pages in {int(time.time()) - begin}s (429s={count_429})"
        )

        return markets # , count_429, float(time.time()) - begin
            
    
    async def _connect(self):
        pass
    
    async def _disconnect(self):
        pass
    
    async def _request(self):
        pass
    
    def pm_clob_to_market(self, clob_market):
        id = clob_market.get('id')
        question = clob_market.get('question')
        yes_ask = float(clob_market.get('bestAsk') or 0)
        yes_bid = float(clob_market.get('bestBid') or 0)
        volume_24h = clob_market.get('volume24hr')
        if volume_24h is None or float(volume_24h) < 10: 
            return None
        liquidity = float(clob_market.get('liquidity') or 0)
        if liquidity <= 500:
            return None
        url = None
        close_time = clob_market.get('endDate')
        
        
        title = clob_market.get('question', '')
        sub_title = clob_market.get('groupItemTitle', '')

        if sub_title and sub_title.lower() not in title.lower():
            match_key = f"{title} - {sub_title}"
        else:
            match_key = title
            
        return Market(
            platform="polymarket",
            market_id=id,
            question=question,
            match_key=match_key,
            yes_ask=yes_ask,
            yes_bid=yes_bid,
            volume_24h=volume_24h,
            liquidity=liquidity,
            url="",
            close_time=close_time
        )
    