from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

class MarketClient:
    @abstractmethod
    async def list_all_markets(self):
        pass
    
    @abstractmethod
    async def market_by_id(self, market_id: str):
        pass
    
    @abstractmethod
    async def _connect(self):
        pass
    
    @abstractmethod
    async def _disconnect(self):
        pass
    
    @abstractmethod
    async def _request(self):
        pass
    
    
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