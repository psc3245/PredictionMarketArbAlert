from dataclasses import dataclass, field
import re
from datetime import date, timedelta
import spacy

TOLERANCE_DAYS = 1

NOISE_WORDS = {
    "will", "the", "a", "an", "be", "to", "in", "on", "by", "at",
    "what", "who", "which", "when", "is", "are", "was", "were",
    "market", "prediction", "bet", "odds", "win", "winner"
}

NFL_TEAMS = {
    "arizona cardinals": ["cardinals", "arizona", "ari"],
    "atlanta falcons": ["falcons", "atlanta", "atl"],
    "baltimore ravens": ["ravens", "baltimore", "bal"],
    "buffalo bills": ["bills", "buffalo", "buf"],
    "carolina panthers": ["panthers", "carolina", "car"],
    "chicago bears": ["bears", "chicago", "chi"],
    "cincinnati bengals": ["bengals", "cincinnati", "cin"],
    "cleveland browns": ["browns", "cleveland", "cle"],
    "dallas cowboys": ["cowboys", "dallas", "dal"],
    "denver broncos": ["broncos", "denver", "den"],
    "detroit lions": ["lions", "detroit", "det"],
    "green bay packers": ["packers", "green bay", "gb"],
    "houston texans": ["texans", "houston", "hou"],
    "indianapolis colts": ["colts", "indianapolis", "ind"],
    "jacksonville jaguars": ["jaguars", "jacksonville", "jax"],
    "kansas city chiefs": ["chiefs", "kansas city", "kc"],
    "las vegas raiders": ["raiders", "las vegas", "lv"],
    "los angeles chargers": ["chargers", "la chargers", "lac"],
    "los angeles rams": ["rams", "la rams", "lar"],
    "miami dolphins": ["dolphins", "miami", "mia"],
    "minnesota vikings": ["vikings", "minnesota", "min"],
    "new england patriots": ["patriots", "new england", "ne"],
    "new orleans saints": ["saints", "new orleans", "no"],
    "new york giants": ["giants", "ny giants", "nyg"],
    "new york jets": ["jets", "ny jets", "nyj"],
    "philadelphia eagles": ["eagles", "philadelphia", "phi"],
    "pittsburgh steelers": ["steelers", "pittsburgh", "pit"],
    "san francisco 49ers": ["49ers", "san francisco", "sf"],
    "seattle seahawks": ["seahawks", "seattle", "sea"],
    "tampa bay buccaneers": ["buccaneers", "tampa bay", "tb"],
    "tennessee titans": ["titans", "tennessee", "ten"],
    "washington commanders": ["commanders", "washington", "was"],
}

NBA_TEAMS = {
    "boston celtics": ["celtics", "boston"],
    "brooklyn nets": ["nets", "brooklyn"],
    "new york knicks": ["knicks", "new york"],
    "philadelphia 76ers": ["76ers", "sixers", "philadelphia"],
    "toronto raptors": ["raptors", "toronto"],
    "chicago bulls": ["bulls", "chicago"],
    "cleveland cavaliers": ["cavaliers", "cavs", "cleveland"],
    "detroit pistons": ["pistons", "detroit"],
    "indiana pacers": ["pacers", "indiana"],
    "milwaukee bucks": ["bucks", "milwaukee"],
    "atlanta hawks": ["hawks", "atlanta"],
    "charlotte hornets": ["hornets", "charlotte"],
    "miami heat": ["heat", "miami"],
    "orlando magic": ["magic", "orlando"],
    "washington wizards": ["wizards", "washington"],
    "denver nuggets": ["nuggets", "denver"],
    "minnesota timberwolves": ["timberwolves", "wolves", "minnesota"],
    "oklahoma city thunder": ["thunder", "okc"],
    "portland trail blazers": ["blazers", "portland"],
    "utah jazz": ["jazz", "utah"],
    "golden state warriors": ["warriors", "golden state"],
    "los angeles clippers": ["clippers", "la clippers"],
    "los angeles lakers": ["lakers", "la lakers"],
    "phoenix suns": ["suns", "phoenix"],
    "sacramento kings": ["kings", "sacramento"],
    "dallas mavericks": ["mavericks", "mavs", "dallas"],
    "houston rockets": ["rockets", "houston"],
    "memphis grizzlies": ["grizzlies", "memphis"],
    "new orleans pelicans": ["pelicans", "new orleans"],
    "san antonio spurs": ["spurs", "san antonio"],
}

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

KEYWORD_GROUPS = [
    # --- Award/title names (NER mis-tags these as FAC/ORG/nothing - confirmed) ---
    {"golden ball", "golden boot", "silver ball", "silver boot",
     "bronze ball", "bronze boot", "golden glove", "best player",
     "player of the tournament", "top goalscorer", "top scorer",
     "leading scorer", "mvp", "most valuable player"},
    {"heisman"},
    {"nobel prize", "nobel peace prize"},
    {"oscar", "academy award"},
    {"grammy"},
    {"mvp award"},  # sports league regular-season/finals MVP, distinct from tournament MVP above

    # --- Recurring event types (structural, not tied to any one edition/year) ---
    {"world cup", "fifa world cup"},
    {"super bowl"},
    {"olympics", "olympic games"},
    {"champions league"},
    {"fomc", "federal reserve", "fed rate", "interest rate decision",
     "rate cut", "rate hike"},
    {"nonfarm payroll", "jobs report", "jobs added", "unemployment rate"},
    {"cpi", "inflation report", "consumer price index"},
    {"gdp report", "gdp growth"},
    {"election", "presidential election", "general election"},
    {"impeachment", "impeach"},
    {"government shutdown"},
    {"ipo", "initial public offering"},
    {"stock split"},
    {"earnings report", "earnings call"},
    {"ceasefire", "peace deal", "peace agreement"},
    {"nuclear deal", "nuclear agreement"},
    {"sanctions"},
    {"nato"},

    # --- Hyphenated / cross-entity geopolitical phrasing (confirmed NER blind spot) ---
    {"us-iran", "u.s.-iran", "us and iran"},
    {"us-china", "u.s.-china", "us and china"},
    {"israel-hamas", "israel and hamas"},
    {"russia-ukraine", "russia and ukraine"},

    # --- Product/version jargon (NER has no PRODUCT category reliability here) ---
    {"gpt-6", "gpt6", "gpt 6"},
    {"gpt-5", "gpt5"},
    {"claude", "mythos", "opus", "sonnet"},
    {"gemini"},
    {"llama"},
    {"gta vi", "gta6", "gta 6"},
    {"starship"},

    # --- Financial thresholds / index-level questions (numbers + product/asset name) ---
    {"bitcoin", "btc"},
    {"ethereum", "eth"},
    {"nasdaq"},
    {"s&p 500", "s&p500", "sp500"},
    {"nvidia"},
]

@dataclass
class MarketMatch:
    # PM Things
    polymarket_id: str
    polymarket_question: str
    # Kalshi Things
    kalshi_id: str
    kalshi_question: str
    
    # Similarity Score
    similarity_score: float
    
    # High level category: 
        # sports games (NFL, NBA, etc) 
        # elections 
        # award (oscar, MVP, etc)
    category: str
    
@dataclass
class CandidatePair:
    # PM Things
    polymarket_id: str
    polymarket_question: str
    pm_deadline: tuple[str, str]
    pm_cands: list[str]
    # Kalshi Things
    kalshi_id: str
    kalshi_question: str
    k_deadline: tuple[str, str]
    k_cands: list[str]
    
class CandidatePairGenerator:
    
    def __init__(self):
        self.NLP = spacy.load("en_core_web_lg")
        
    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        # words = text.split()
        # words = [w for w in words if w not in self.NOISE_WORDS]
        # return ' '.join(words)
        return text

    def get_deadline(self, question: str) -> str:
        
        text_lower = self.normalize_text(question)
        tokens = text_lower.split()
        
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
            
        # Find the first month mentioned in the actual sentence
        # Sort longest-first so "august" beats "aug"
        found_month = None
        first_pos = len(text_lower)

        for month_name in sorted(MONTHS.keys(), key=len, reverse=True):
            match = re.search(rf"\b{month_name}\b", text_lower)

            if match and match.start() < first_pos:
                first_pos = match.start()
                found_month = month_name

        if found_month:
            month = MONTHS[found_month]
            raw_tokens.append(found_month)

            # Extract day/year when month is found
            pattern = (
                rf'\b{found_month}\.?,?\s*'
                rf'(\d{{1,2}})'
                rf'(?:st|nd|rd|th)?'
                rf'(?:,?\s*(\d{{4}}))?\b'
            )

            d = re.search(pattern, text_lower)

            if d:
                day = d.group(1).zfill(2)
                raw_tokens.append(d)

                if d.group(2):
                    raw_tokens.append(d)
                    
                    year = d.group(2)

        
        # Support "thirty-first of August"
        if day is None:

            day_regex = "|".join(
                sorted(
                    [d.replace("-", "[- ]") for d in DAYS.keys()],
                    key=len,
                    reverse=True
                )
            )

            for month_name in sorted(MONTHS.keys(), key=len, reverse=True):

                pattern = rf'\b({day_regex})\s+of\s+{month_name}\b'

                m = re.search(pattern, text_lower)

                if m:
                    month = MONTHS[month_name]
                    raw_tokens.append(month_name)
                    day = DAYS[m.group(1)]
                    raw_tokens.append(m.group(1))
                    break

        
        # Support standalone ordinal words
        if day is None:

            for d in sorted(DAYS.keys(), key=len, reverse=True):

                if d in tokens:
                    day = DAYS[d]
                    raw_tokens.append(d)
                    break
                
        
        # Relative dates
        if "this month" in text_lower:
            month = str(date.today().month % 12 + 1).zfill(2)
            raw_tokens.append("this month")
            
        if "this year" in text_lower:
            year = str(date.today().year)
            raw_tokens.append("this year")
            

        # Extract years in sentence order
        for token in tokens:
            if token in YEARS:
                year = token
                raw_tokens.append(token)
                break

                
        # No date found
        if year is None and month is None and day is None:
            return None

        
        # If month exists but day does not, assume first of month
        if day is None and month is not None:
            day = "01"

        
        # If month exists but year does not, assume current year
        if month is not None and year is None:
            year = str(date.today().year)

        
        # If only year exists, assume end of year
        if month is None and day is None and year is not None:
            before_or_after = "by"
            month = "12"
            day = "31"

        
        # Pad single digit days
        if day is not None and len(str(day)) == 1:
            day = "0" + str(day)

        
        # A standalone day is probably not a deadline
        if day is not None and month is None and year is None:
            return None

                
        return (before_or_after, f"{month}-{day}-{year}", raw_tokens)

    def get_candidates(self, question):
        SENTENCE_OPENERS = ["will", "what", "who", "how", "does", ]
        
        tokens = question.split()
        if tokens[0].lower() in SENTENCE_OPENERS:
            tokens = tokens[1:]
            
        stripped = ' '.join(tokens)
        
        doc = self.NLP(stripped)
        
        ents = [e.text for e in doc.ents if e.label_ != "DATE"]
        
        return ents

    def get_whats_left(self, question):
        deadline = self.get_deadline(question)
        candidates = self.get_candidates(question)
        
        tokens = self.normalize_text(question).split()

        filtered = []

        entity_words = set()
        for entity in candidates:
            entity_words.update(self.normalize_text(entity).split())

        deadline_words = set()
        if deadline is not None:
            _, _, raw_tokens = deadline
            for token in raw_tokens:
                if isinstance(token, re.Match):
                    deadline_words.update(self.normalize_text(token.group(0)).split())
                else:
                    deadline_words.update(self.normalize_text(str(token)).split())
                    
        print(f"  candidates: {candidates}")
        print(f"  entity_words: {entity_words}") 

        for token in tokens:
            if token in DAYS:
                continue
            elif token in {"before", "after", "by"}:
                continue
            elif token in YEARS:
                continue
            elif token in MONTHS:
                continue
            elif token in entity_words:
                continue
            elif token in deadline_words:
                continue

            filtered.append(token)

        return filtered

    def deadlines_match(self, before_or_after1, d1, before_or_after2, d2):
        m1, day1, y1 = map(int, d1.split("-"))
        date1 = date(year=y1, month=m1, day=day1)

        m2, day2, y2 = map(int, d2.split("-"))
        date2 = date(year=y2, month=m2, day=day2)

        q1 = "before" if before_or_after1 in {"before", "by"} else before_or_after1
        q2 = "before" if before_or_after2 in {"before", "by"} else before_or_after2

        if q1 == q2:
            return abs((date1 - date2).days) <= TOLERANCE_DAYS

        if q1 == "before" and q2 == "after":
            return date2 + timedelta(days=1) == date1

        if q1 == "after" and q2 == "before":
            return date1 + timedelta(days=1) == date2

        return False

    def keyword_pool_overlap(self, pm_q, k_q):
        pm_normal = self.normalize_text(pm_q)
        k_normal = self.normalize_text(k_q)

        for keyword_group in KEYWORD_GROUPS:
            for keyword in keyword_group:
                pattern = rf'\b{re.escape(keyword)}\b'
                if re.search(pattern, pm_normal) and re.search(pattern, k_normal):
                    return True

        return False
        
        
    def create_candidate_pair(self, pm_id, pm_q, k_id, k_q):
        pm_result = self.get_deadline(pm_q)
        k_result = self.get_deadline(k_q)

        pm_b_or_a, pm_deadline = (pm_result[0], pm_result[1]) if pm_result else (None, None)
        k_b_or_a, k_deadline = (k_result[0], k_result[1]) if k_result else (None, None)
        
        if pm_deadline is None and k_deadline is None:
            pass

        elif pm_deadline is None or k_deadline is None:
            return None

        elif not self.deadlines_match(pm_b_or_a, pm_deadline, k_b_or_a, k_deadline):
            return None
        
        pm_cands = self.get_candidates(pm_q)
        k_cands = self.get_candidates(k_q)
        
        pm_words = {w for c in pm_cands for w in self.normalize_text(c).split()}
        k_words = {w for c in k_cands for w in self.normalize_text(c).split()}
        has_overlap = bool(pm_words & k_words)
        
        keyword_overlap = self.keyword_pool_overlap(pm_q, k_q)
        
        if has_overlap or keyword_overlap:
            return CandidatePair(polymarket_id=pm_id, polymarket_question=pm_q, pm_deadline=(pm_b_or_a, pm_deadline), pm_cands=pm_cands,
                                kalshi_id=k_id, kalshi_question=k_q, k_deadline=(k_b_or_a, k_deadline), k_cands=k_cands)
        else:
            return None