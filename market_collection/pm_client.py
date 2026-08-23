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
    
    async def list_all_markets(self, target=100):
        markets = []
        next_cursor = None
        begin = int(time.time())
        count_429 = 0

        while True:
            url = f"{PM_URL}?limit=100"

            if next_cursor:
                url += f"&after_cursor={next_cursor}"

            response = await self.async_client.get(url)

            if response.status_code == 429:
                print("429!")
                count_429 += 1
                await asyncio.sleep(1)
                continue

            data = response.json()
            pretty_json = json.dumps(data, indent=4, sort_keys=True)
            # print(pretty_json)

            for m in data.get("markets", []):

                markets.append(m)

                if len(markets) >= target:
                    break

            next_cursor = data.get("next_cursor")

            if not next_cursor:
                break
            
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
        yes_ask = float(clob_market.get('bestAsk'))
        yes_bid = float(clob_market.get('bestBid'))
        volume_24h = clob_market.get('volume')
        liquidity = float(clob_market.get('liquidity'))
        url = None
        close_time = clob_market.get('endDate')
        
        
        title = clob_market.get('title', '')
        sub_title = clob_market.get('yes_sub_title', '')

        if sub_title and sub_title.lower() not in title.lower():
            match_key = f"{title} - {sub_title}"
        else:
            match_key = title
            
        return Market(
            platform='polymarket',
            market_id=id,
            question=question,
            match_key=question,
            yes_ask=yes_ask,
            yes_bid=yes_bid,
            volume_24h=volume_24h,
            liquidity=liquidity,
            url="",
            close_time=close_time
        )
    