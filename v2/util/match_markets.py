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

NLP = spacy.load("en_core_web_lg")

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

def get_candidates(question):
    SENTENCE_OPENERS = ["will", "what", "who", "how", "does", ]
    
    tokens = question.split()
    if tokens[0].lower() in SENTENCE_OPENERS:
        tokens = tokens[1:]
        
    stripped = ' '.join(tokens)
    
    doc = NLP(stripped)
    
    ents = [e.text for e in doc.ents if e.label_ != "DATE"]
    
    return ents

def get_whats_left(question):
    deadline = get_deadline(question)
    candidates = get_candidates(question)
    
    tokens = normalize_text(question).split()

    filtered = []

    entity_words = set()
    for entity in candidates:
        entity_words.update(normalize_text(entity).split())

    deadline_words = set()
    if deadline is not None:
        _, _, raw_tokens = deadline
        for token in raw_tokens:
            if isinstance(token, re.Match):
                deadline_words.update(normalize_text(token.group(0)).split())
            else:
                deadline_words.update(normalize_text(str(token)).split())
                
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

def deadlines_match(before_or_after1, d1, before_or_after2, d2):
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
    
    
def create_candidate_pair(pm_id, pm_q, k_id, k_q):
    pm_result = get_deadline(pm_q)
    k_result = get_deadline(k_q)

    pm_b_or_a, pm_deadline = (pm_result[0], pm_result[1]) if pm_result else (None, None)
    k_b_or_a, k_deadline = (k_result[0], k_result[1]) if k_result else (None, None)
    
    if pm_deadline is None and k_deadline is None:
        pass

    elif pm_deadline is None or k_deadline is None:
        return None

    elif not deadlines_match(pm_b_or_a, pm_deadline, k_b_or_a, k_deadline):
        return None
    
    pm_cands = get_candidates(pm_q)
    k_cands = get_candidates(k_q)
    
    pm_words = {w for c in pm_cands for w in normalize_text(c).split()}
    k_words = {w for c in k_cands for w in normalize_text(c).split()}
    has_overlap = bool(pm_words & k_words)
    
    if has_overlap:
        return CandidatePair(polymarket_id=pm_id, polymarket_question=pm_q, pm_deadline=(pm_b_or_a, pm_deadline), pm_cands=pm_cands,
                            kalshi_id=k_id, kalshi_question=k_q, k_deadline=(k_b_or_a, k_deadline), k_cands=k_cands)
    else:
        return None
    
CANDIDATE_PAIR_TESTS = [
    # --- should become candidates (deadline compatible + entity overlap) ---

    # same entity, same condition, phrasing-convention date difference
    ("2633430", "US-Iran Final Nuclear Deal by August 31, 2026?",
     "KXUSAIRANAGREEMENT-27-26SEP", "Will the US agree to a new Iranian nuclear deal before September?"),

    # same entity, exact matching date, different formatting
    ("2100070", "GPT-5.6 released by July 31, 2026?",
     "KXGPT-OPENB-26JUL31", "Will OpenAI release GPT-5.6 before Jul 31, 2026?"),

    # same entity, DIFFERENT condition - should still become a candidate,
    # since condition-matching is the LLM's job, not this step's
    ("2430978", "Will Erling Haaland win the Silver Ball at the 2026 FIFA World Cup?",
     "KXWCGOALLEADER-26-EHAA", "Will Erling Haaland lead FIFA World Cup in Goals for the 2026 World Cup Full Tournament?"),

    # neither side has an extractable deadline - should still pass through
    # (both-None case, testing the fix from last round)
    ("999001", "Will Messi win the Golden Ball?",
     "KXTEST-MESSI", "Will Lionel Messi be named tournament MVP?"),

    # --- should be rejected: deadline mismatch (hard reject) ---

    # same entity/topic, meaningfully different explicit dates
    ("2633426", "US-Iran Final Nuclear Deal by June 30, 2026?",
     "KXUSAIRANAGREEMENT-27-26AUG", "Will the US agree to a new Iranian nuclear deal before August 13?"),

    # same topic, opposite qualifier direction, same date
    ("999002", "Will the announcement come before June 2026?",
     "KXTEST-AFTER", "Will the announcement come after June 2026?"),

    # --- should be rejected: no entity overlap ---

    # unrelated topics entirely, no shared entities, dates may or may not match
    ("999003", "Will Bitcoin hit $150k before October?",
     "KXTEST-UNRELATED", "Will Cristiano Ronaldo win the Golden Ball before October?"),

    # --- should be rejected: one side has a date, other doesn't (per your policy) ---

    ("999004", "Will Messi retire before the 2026 World Cup?",
     "KXTEST-NODATE", "Will Messi retire?"),

    # --- known NER blind spot - worth seeing how it behaves, not asserting an outcome ---

    # hyphenated entity + award name in both - overlap depends entirely on
    # whether "US" alone is enough shared signal, or whether this silently
    # fails due to spaCy missing "Iran" as its own entity
    ("2633429", "US-Iran Final Nuclear Deal by August 18, 2026?",
     "KXUSAIRANAGREEMENT-27-26AUG", "Will the US agree to a new Iranian nuclear deal before August?"),
]


def print_candidate_pairs():
    for pm_id, pm_q, k_id, k_q in CANDIDATE_PAIR_TESTS:
        result = create_candidate_pair(pm_id, pm_q, k_id, k_q)
        status = "CANDIDATE" if result else "rejected"
        print(f"[{status}] PM: {pm_q}")
        print(f"           K:  {k_q}")
        if result:
            print(f"           pm_cands={result.pm_cands}  k_cands={result.k_cands}")
        print()


print_candidate_pairs()