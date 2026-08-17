from enum import Enum
from dataclasses import dataclass
import re
from datetime import date
import spacy
from collections import defaultdict

# -----------------------------------------
#      CONSTANTS                          |
# -----------------------------------------

MONTHS = {
    'jan': '01', 'january': '01', 'feb': '02', 'february': '02',
    'mar': '03', 'march': '03', 'apr': '04', 'april': '04',
    'may': '05', 'jun': '06', 'june': '06', 'jul': '07', 'july': '07',
    'aug': '08', 'august': '08', 'sep': '09', 'september': '09',
    'oct': '10', 'october': '10', 'nov': '11', 'november': '11',
    'dec': '12', 'december': '12'
}

DAYS = {
    "first": 1,
    "second": 2,
    "third": 3,
    "fourth": 4,
    "fifth": 5,
    "sixth": 6,
    "seventh": 7,
    "eighth": 8,
    "ninth": 9,
    "tenth": 10,
    "eleventh": 11,
    "twelfth": 12,
    "thirteenth": 13,
    "fourteenth": 14,
    "fifteenth": 15,
    "sixteenth": 16,
    "seventeenth": 17,
    "eighteenth": 18,
    "nineteenth": 19,
    "twentieth": 20,
    "twenty-first": 21,    "twenty first": 21,
    "twenty-second": 22,    "twenty second": 22,
    "twenty-third": 23,    "twenty third": 23,
    "twenty-fourth": 24,    "twenty fourth": 24,
    "twenty-fifth": 25,    "twenty fifth": 25,
    "twenty-sixth": 26,    "twenty sixth": 26,
    "twenty-seventh": 27,    "twenty seventh": 27,
    "twenty-eighth": 28,    "twenty eighth": 28,
    "twenty-ninth": 29, "twenty ninth": 29, 
    "thirtieth": 30,
    "thirty-first": 31, "thirty first": 31,
}

YEARS = [
    "2026",
    "2027",
    "2028"
]

NOISE_WORDS = {
    "will", "the", "a", "an", "be", "to", "in", "on", "by", "at",
    "what", "who", "which", "when", "is", "are", "was", "were",
    "market", "prediction", "bet", "odds", "win", "winner", "s"
}

UNWANTED_ENT_LABELS = {
    "DATE", "MONEY", "PERCENT", "QUANTITY", "CARDINAL"
}

KEYWORD_GROUPS = [
    # --- Award/title names (NER mis-tags these as FAC/ORG/nothing - confirmed) ---
    {"golden ball", "golden boot", "silver ball", "silver boot",
     "bronze ball", "bronze boot", "golden glove", "best player",
     "player of the tournament", "top goalscorer", "top scorer",
     "leading scorer", "mvp", "most valuable player"},
    {"heisman", "heisman trophy"},
    {"nobel prize", "nobel peace prize", "nobel prize winner"},
    {"oscar", "academy award", "academy awards"},
    {"grammy", "grammy award", "grammy awards"},
    {"mvp award"},  # sports league regular-season/finals MVP, distinct from tournament MVP above

    # --- Recurring event types (structural, not tied to any one edition/year) ---
    {"world cup", "fifa world cup"},
    {"super bowl", "superbowl"},
    {"olympics", "olympic games", "summer olympics", "winter olympics"},
    {"champions league", "uefa champions league"},
    {"europa league", "uefa europa league"},
    {"nba finals"},
    {"stanley cup", "stanley cup finals"},
    {"world series", "mlb world series"},
    {"ncaa tournament", "march madness"},
    {"us open"},
    {"wimbledon"},
    {"french open", "roland garros"},
    {"australian open"},

    # --- US monetary policy / economic indicators ---
    {"fed", "fomc", "federal reserve", "fed rate", "federal funds rate",
     "interest rate decision", "interest rate", "rate cut", "rate hike",
     "rate cuts", "rate hikes"},
    {"nonfarm payroll", "nonfarm payrolls", "jobs report", "jobs added",
     "jobs created", "unemployment rate", "unemployment"},
    {"cpi", "inflation report", "consumer price index", "inflation rate"},
    {"ppi", "producer price index"},
    {"gdp report", "gdp growth", "gross domestic product"},
    {"retail sales"},
    {"consumer confidence"},
    {"jobless claims", "initial jobless claims"},
    {"housing starts", "housing start"},
    {"existing home sales", "new home sales"},
    {"ism", "ism manufacturing", "ism services"},
    {"recession", "economic recession"},

    # --- Elections / US government ---
    {"election", "presidential election", "general election"},
    {"primary election", "presidential primary"},
    {"midterm election", "midterms"},
    {"electoral college", "electoral votes"},
    {"impeachment", "impeach"},
    {"government shutdown", "shutdown"},
    {"debt ceiling", "debt limit"},
    {"government funding", "federal funding"},
    {"supreme court", "supreme court ruling"},
    {"executive order", "executive orders"},

    # --- Financial markets / corporate events ---
    {"ipo", "initial public offering"},
    {"stock split", "stock split announcement"},
    {"earnings report", "earnings call", "quarterly earnings",
     "earnings results"},
    {"merger", "acquisition", "merger and acquisition", "m&a"},
    {"bankruptcy", "bankruptcy filing"},
    {"dividend", "dividend payment"},
    {"buyback", "stock buyback", "share buyback"},

    # --- Crypto / financial assets ---
    {"bitcoin", "btc"},
    {"ethereum", "eth"},
    {"solana", "sol"},
    {"xrp", "ripple"},
    {"dogecoin", "doge"},
    {"nasdaq", "nasdaq composite"},
    {"s&p 500", "s&p500", "sp500"},
    {"dow jones", "dow", "djia"},
    {"russell 2000"},
    {"nvidia", "nvda"},
    {"tesla", "tsla"},
    {"apple", "aapl"},
    {"microsoft", "msft"},
    {"amazon", "amzn"},
    {"alphabet", "google", "googl", "goog"},
    {"meta", "meta platforms"},
    {"openai"},

    # --- International conflict / diplomacy ---
    {"ceasefire", "cease-fire", "peace deal", "peace agreement"},
    {"nuclear deal", "nuclear agreement", "nuclear talks"},
    {"sanctions", "economic sanctions"},
    {"nato", "north atlantic treaty organization"},
    {"united nations", "un", "un security council"},
    {"tariff", "tariffs", "trade tariff", "trade war"},
    {"peace talks", "peace negotiations"},
    {"military aid", "foreign aid"},
    {"invasion"},
    {"airstrike", "air strikes", "airstrikes"},

    # --- Hyphenated / cross-entity geopolitical phrasing (confirmed NER blind spot) ---
    {"us-iran", "u.s.-iran", "us and iran"},
    {"us-china", "u.s.-china", "us and china"},
    {"us-russia", "u.s.-russia", "us and russia"},
    {"us-israel", "u.s.-israel", "us and israel"},
    {"israel-hamas", "israel and hamas"},
    {"russia-ukraine", "russia and ukraine"},
    {"china-taiwan", "china and taiwan"},
    {"north korea-south korea", "north korea and south korea"},
    {"israel-iran", "israel and iran"},

    # --- Product/version jargon (NER has no PRODUCT category reliability here) ---
    {"gpt-6", "gpt6", "gpt 6"},
    {"gpt-5", "gpt5", "gpt 5"},
    {"claude", "mythos", "opus", "sonnet"},
    {"gemini"},
    {"llama"},
    {"gta vi", "gta6", "gta 6"},
    {"starship"},

    # --- Technology / AI releases ---
    {"artificial intelligence", "artificial intelligence model", "ai model"},
    {"large language model", "large language models", "llm", "llms"},
    {"chatgpt"},
    {"openai model", "openai models"},
    {"anthropic model", "anthropic models"},
    {"google ai", "google deepmind"},
    {"ai agent", "ai agents"},
    {"robotaxi", "robotaxis"},
    {"self-driving", "self driving", "autonomous driving"},

    # --- Major sports statistics / outcomes ---
    {"touchdown", "touchdowns"},
    {"home run", "home runs"},
    {"passing yards", "rushing yards", "receiving yards"},
    {"points per game", "ppg"},
    {"goals scored", "goals"},
    {"assists"},
    {"rebounds"},
    {"strikeouts", "strikeout"},
    {"wins", "win total"},
    {"regular season", "regular-season"},
    {"playoffs", "playoff"},
    {"championship", "championship game"},

    # --- Major entertainment releases / awards ---
    {"box office", "domestic box office", "worldwide box office"},
    {"opening weekend", "opening weekend box office"},
    {"streaming", "streaming release"},
    {"emmy", "emmy award", "emmy awards"},
    {"tony award", "tony awards"},
    {"bafta", "bafta awards"},
    {"golden globe", "golden globes"},

    # --- Weather / natural events ---
    {"hurricane", "tropical storm"},
    {"tornado", "tornadoes"},
    {"earthquake", "earthquakes"},
    {"wildfire", "wildfires"},
    {"landfall"},
    {"category 5", "category five"},

    # --- Space / launches ---
    {"spacex", "space x"},
    {"falcon 9", "falcon nine"},
    {"starship", "spacex starship"},
    {"rocket launch", "rocket launches"},
    {"moon landing", "lunar landing"},
    {"mars mission", "mars mission"},
]

MIN_ENTITY_LENGTH = 3

class MarketType(Enum):
    KALSHI = 1
    POLYMARKET = 2
    
# dataclass the input should follow, will eventually be moved into a models class    
@dataclass
class Market:
    market_type: MarketType
    market_id: str
    question: str
    match_key: str
    url: str

@dataclass
class ProcessedMarket:
    market: Market
    deadline: tuple[str, str, str] | None
    cands: list[str]
    rest: list[str]
    keyword_group_ids: set[int]

    def __eq__(self, other):
        if not isinstance(other, ProcessedMarket):
            return NotImplemented

        return (
            self.market.market_type,
            self.market.market_id
        ) == (
            other.market.market_type,
            other.market.market_id
        )

    def __hash__(self):
        return hash((
            self.market.market_type,
            self.market.market_id
        ))
    
class MarketPreprocessor:

    def __init__(self):
        self.NLP = spacy.load("en_core_web_sm")

    def preprocess(self, market_old) -> ProcessedMarket:
        market_type = MarketType.KALSHI if market_old.platform == "kalshi" else MarketType.POLYMARKET
        market_id = market_old.market_id
        question = market_old.question
        match_key = market_old.match_key
        url = market_old.url
        market = Market(market_type=market_type, market_id=market_id, 
                        question=question, match_key=match_key, url=url)
        
        deadline = self.get_deadline(market.match_key)

        cands = self.get_candidates(market.match_key)

        rest = self.get_whats_left(market.match_key, deadline, cands)

        keyword_group_ids = self.get_keyword_group_ids(market.match_key)

        return ProcessedMarket(
            market=market,
            deadline=deadline,
            cands=cands,
            rest=rest,
            keyword_group_ids=keyword_group_ids
        )

    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        return text

    def get_deadline(self, question: str) -> tuple[str, str, str] | None:
        text_lower = self.normalize_text(question)
        tokens = text_lower.split()

        if not tokens:
            return None

        raw_tokens = []

        before_or_after = None
        month = None
        day = None
        year = None

        if "before" in tokens:
            before_or_after = "before"
        elif "by" in tokens:
            before_or_after = "by"
        elif "after" in tokens:
            before_or_after = "after"

        # Find the first month mentioned in the actual sentence.
        # Sort longest-first so "august" beats "aug".
        found_month = None
        first_pos = len(text_lower)

        for month_name in sorted(MONTHS.keys(), key=len, reverse=True):
            match = re.search(rf"\b{re.escape(month_name)}\b", text_lower)

            if match and match.start() < first_pos:
                first_pos = match.start()
                found_month = month_name

        if found_month:
            month = MONTHS[found_month]
            raw_tokens.append(found_month)

            pattern = (
                rf'\b{re.escape(found_month)}\.?,?\s*'
                rf'(\d{{1,2}})'
                rf'(?:st|nd|rd|th)?'
                rf'(?:,?\s*(\d{{4}}))?\b'
            )

            d = re.search(pattern, text_lower)

            if d:
                day = d.group(1).zfill(2)
                raw_tokens.append(d)

                if d.group(2):
                    year = d.group(2)

        # Handle "21st of August", "twenty-first of August", etc.
        if day is None:
            day_regex = "|".join(
                sorted(
                    [re.escape(d).replace(r"\-", "[- ]") for d in DAYS.keys()],
                    key=len,
                    reverse=True
                )
            )

            for month_name in sorted(MONTHS.keys(), key=len, reverse=True):
                pattern = (
                    rf'\b({day_regex})\s+of\s+'
                    rf'{re.escape(month_name)}\b'
                )

                m = re.search(pattern, text_lower)

                if m:
                    month = MONTHS[month_name]
                    raw_tokens.append(month_name)

                    day = DAYS[m.group(1)]

                    if isinstance(day, int):
                        day = str(day).zfill(2)

                    raw_tokens.append(m.group(1))
                    break

        # Handle standalone ordinal words such as "twenty-first".
        if day is None:
            for d in sorted(DAYS.keys(), key=len, reverse=True):
                if d in tokens:
                    day = str(DAYS[d]).zfill(2)
                    raw_tokens.append(d)
                    break

        if "this month" in text_lower:
            month = str(date.today().month % 12 + 1).zfill(2)
            raw_tokens.append("this month")

        if "this year" in text_lower:
            year = str(date.today().year)
            raw_tokens.append("this year")

        for token in tokens:
            if token in YEARS:
                year = token
                raw_tokens.append(token)
                break

        if year is None and month is None and day is None:
            return None

        # If only a month was specified, default to the first day.
        if day is None and month is not None:
            day = "01"

        # If a month was specified without a year, assume current year.
        if month is not None and year is None:
            year = str(date.today().year)

        # If only a year was specified, interpret it as the end of
        # that year.
        if month is None and day is None and year is not None:
            before_or_after = "by"
            month = "12"
            day = "31"

        if day is not None and month is None:
            return None

        return (
            before_or_after,
            f"{month}-{day}-{year}",
            raw_tokens
        )

    def get_candidates(self, question: str) -> list[str]:
        SENTENCE_OPENERS = {
            "will",
            "what",
            "who",
            "how",
            "does",
        }

        tokens = question.split()

        if not tokens:
            return []

        if tokens[0].lower() in SENTENCE_OPENERS:
            tokens = tokens[1:]

        stripped = " ".join(tokens)

        doc = self.NLP(stripped)

        ents = []

        for e in doc.ents:
            if e.label_ in UNWANTED_ENT_LABELS:
                continue
            candidate = e.text.strip()
            if len(self.normalize_text(candidate).strip()) < MIN_ENTITY_LENGTH:
                continue
            ents.append(candidate)

        return ents

    def get_whats_left(self, question: str, deadline, candidates) -> list[str]:

        tokens = self.normalize_text(question).split()

        filtered = []

        entity_words = set()

        for entity in candidates:
            entity_words.update(
                self.normalize_text(entity).split()
            )

        deadline_words = set()

        if deadline is not None:
            _, _, raw_tokens = deadline

            for token in raw_tokens:
                if isinstance(token, re.Match):
                    deadline_words.update(
                        self.normalize_text(token.group(0)).split()
                    )
                else:
                    deadline_words.update(
                        self.normalize_text(str(token)).split()
                    )

        for token in tokens:
            if token in DAYS:
                continue

            if token in {"before", "after", "by"}:
                continue

            if token in YEARS:
                continue

            if token in MONTHS:
                continue

            if token in entity_words:
                continue

            if token in deadline_words:
                continue
            
            if token in NOISE_WORDS:
                continue

            filtered.append(token)

        return filtered

    def question_matches_keyword_group(
        self,
        question: str,
        keyword_group: set[str]
    ) -> bool:
        normalized_question = self.normalize_text(question)

        for keyword in keyword_group:
            normalized_keyword = self.normalize_text(keyword)

            pattern = rf"\b{re.escape(normalized_keyword)}\b"
            if re.search(pattern, normalized_question):
                return True

        return False

    def get_keyword_group_ids(self, question: str) -> set[int]:
        group_ids = set()

        for i, group in enumerate(KEYWORD_GROUPS):
            if self.question_matches_keyword_group(question, group):
                group_ids.add(i)

        return group_ids
    
class LookupTable:

    def __init__(self):
        self.kalshi_by_entity = defaultdict(list)
        self.pm_by_entity = defaultdict(list)

        self.kalshi_by_keyword_group = defaultdict(list)
        self.pm_by_keyword_group = defaultdict(list)

    # Single entry point.
    def add(self, market: ProcessedMarket):
        if market.market.market_type == MarketType.KALSHI:
            self.kalshi_add(market)
        else:
            self.pm_add(market)

    def kalshi_add(self, market: ProcessedMarket):
        for cand in market.cands:
            self.kalshi_by_entity[self.normalize_entity(cand)].append(market)

        for group_id in market.keyword_group_ids:
            self.kalshi_by_keyword_group[group_id].append(market)

    def pm_add(self, market: ProcessedMarket):
        for cand in market.cands:
            self.pm_by_entity[self.normalize_entity(cand)].append(market)

        for group_id in market.keyword_group_ids:
            self.pm_by_keyword_group[group_id].append(market)
            
    def normalize_entity(self, entity: str) -> str:
        entity = entity.lower()
        entity = re.sub(r'[^\w\s]', ' ', entity)
        return entity.strip()

    # Return all markets from a specific broker that
    # contain a particular entity.
    def lookup_by_entity(
        self,
        entity: str,
        type: MarketType
    ) -> list[ProcessedMarket]:

        if type == MarketType.KALSHI:
            return self.kalshi_by_entity[self.normalize_entity(entity)]

        return self.pm_by_entity[self.normalize_entity(entity)]

    # Return all markets from a specific broker that
    # belong to a particular keyword group.
    def lookup_by_keyword_group(
        self,
        group_id: int,
        type: MarketType
    ) -> list[ProcessedMarket]:

        if type == MarketType.KALSHI:
            return self.kalshi_by_keyword_group[group_id]

        return self.pm_by_keyword_group[group_id]

    # Return all markets from the opposite broker that
    # may potentially match this market.
    #
    # Candidates come from either:
    #   1. shared entities
    #   2. shared keyword groups
    #
    # The set automatically removes duplicates when a market
    # matches through both mechanisms.
    def lookup_by_market(
        self,
        market: ProcessedMarket
    ) -> set[ProcessedMarket]:

        candidates = set()

        if market.market.market_type == MarketType.KALSHI:
            entity_index = self.pm_by_entity
            group_index = self.pm_by_keyword_group
        else:
            entity_index = self.kalshi_by_entity
            group_index = self.kalshi_by_keyword_group

        for cand in market.cands:
            candidates.update(entity_index[self.normalize_entity(cand)])

        for group_id in market.keyword_group_ids:
            candidates.update(group_index[group_id])

        return candidates

    # Return candidate markets sorted by matching strength.
    #
    # Entity overlap is kept separate from keyword-group overlap
    # because an exact/shared entity is generally a stronger signal
    # than merely belonging to the same broad keyword group.
    def sorted_lookup_by_market(
        self,
        market: ProcessedMarket
    ) -> list[tuple[int, int, ProcessedMarket]]:

        candidates = self.lookup_by_market(market)

        ret = []

        market_entities = {self.normalize_entity(c) for c in market.cands}

        for candidate in candidates:
            candidate_entities = {self.normalize_entity(c) for c in candidate.cands}
            entity_overlap = len(candidate_entities & market_entities)

            keyword_group_overlap = len(
                candidate.keyword_group_ids
                & market.keyword_group_ids
            )

            ret.append((
                entity_overlap,
                keyword_group_overlap,
                candidate
            ))

        ret.sort(
            key=lambda x: (x[0], x[1]),
            reverse=True
        )

        return ret