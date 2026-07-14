from dataclasses import dataclass, field
import re
from datetime import date

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
    
def normalize_text(text: str) -> str:
    """Normalize text for comparison."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    # words = text.split()
    # words = [w for w in words if w not in self.NOISE_WORDS]
    # return ' '.join(words)
    return text

def get_deadline(question: str) -> str:
    
    text_lower = normalize_text(question)
    tokens = text_lower.split()

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

            if d.group(2):
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
                day = DAYS[m.group(1)]
                break

    
    # Support standalone ordinal words
    if day is None:

        for d in sorted(DAYS.keys(), key=len, reverse=True):

            if d in tokens:
                day = DAYS[d]
                break
            
    
    # Relative dates
    if "this month" in text_lower:
        month = str(date.today().month).zfill(2)
        
    if "this year" in text_lower:
        year = str(date.today().year)
        

    # Extract years in sentence order
    for token in tokens:
        if token in YEARS:
            year = token
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

            
    return (before_or_after, f"{month}-{day}-{year}")
