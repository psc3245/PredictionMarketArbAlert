import re
import json
import os
import time
import httpx
from datetime import date
from rapidfuzz import fuzz
import fetch_markets as f

KEYWORD_GROUPS = [
    {"bitcoin", "btc", "150k"},
    {"gpt-6", "gpt6", "gpt 6"},
    {"gpt-5"},
    {"mythos"},
    {"gta vi", "gta6", "gta 6"},
    {"starship"},
    {"netanyahu"},
    {"starmer"},
    {"openai ipo"},
    {"anthropic ipo"},
    {"iranian nuclear", "nuclear deal", "iran nuclear"},
    {"trump leaves office", "trump out as president", "trump resign", "trump impeach"},
    {"trump putin"},
    {"mbappe", "mbappé"},
    {"messi"},
    {"ronaldo"},
    {"haaland"},
    {"fed rate cut", "fed rate hike", "federal reserve rate", "fomc rate"},
    {"nonfarm payroll", "jobs added"},
    {"nvidia largest", "nvidia market cap"},
    {"zelensky"},
    {"ukraine nato"},
]

def has_antonym(q1, q2):
    negation_words = [" not ", " won't ", " fail ", " no deal", " remain ", 
                      " stay ", "won't be", "will not", "fails to"]
    q1_neg = any(w in q1.lower() for w in negation_words)
    q2_neg = any(w in q2.lower() for w in negation_words)

    return q1_neg != q2_neg

def get_deadline_type(question):
    q = question.lower()
    event_deadlines = [
        "before gta vi", "before gta 6", "before gta6",
        "before bitcoin hits", "before the inauguration",
        "before election", "before super bowl"
    ]
    if any(e in q for e in event_deadlines):
        return "event"
    if re.search(r'\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}', q):
        return "date"
    if re.search(r'by (june|july|august|september|october|november|december)\b', q):
        return "date"
    return "unknown"

def find_keyword_candidates(kalshi_markets, polymarket_markets):
    candidates = []
    seen = set()
    SKIP_PREFIXES = ["what will", "who will say", "how many times will"]

    for km in kalshi_markets:
        k_text = km.match_key.lower()
        if any(k_text.startswith(p) for p in SKIP_PREFIXES):
            continue

        k_deadline = get_deadline_type(km.match_key)
        matched_groups = [g for g in KEYWORD_GROUPS if any(kw in k_text for kw in g)]
        if not matched_groups:
            continue

        for pm in polymarket_markets:
            p_text = pm.match_key.lower()
            p_deadline = get_deadline_type(pm.match_key)
            
            date_diff = abs((km.close_time - pm.close_time).days)
            # if date_diff > 7:
            #     continue

            if k_deadline != "unknown" and p_deadline != "unknown" and k_deadline != p_deadline:
                continue

            for group in matched_groups:
                if any(kw in p_text for kw in group):
                    key = (km.market_id, pm.market_id)
                    if key not in seen:
                        seen.add(key)
                        candidates.append((km, pm))
                    break

    print(f"  Keyword filter: {len(candidates)} candidate pairs from {len(kalshi_markets)} Kalshi × {len(polymarket_markets)} Polymarket")
    
    print(f"\n--- Candidates ---")
    for km, pm in candidates[:20]:
        print(f"  {km.match_key[:60]}")
        print(f"  {pm.match_key[:60]}")
        print()
    
    return candidates

def extract_numbers(text):
    nums = re.findall(r'\d+(?:\.\d+)?', text)
    result = set()
    for n in nums:
        try:
            val = float(n)
            if val in {2025.0, 2026.0, 2027.0}:
                continue
            if val == int(val) and 1 <= val <= 31:
                continue
            if val > 1000:
                from math import log10, floor
                magnitude = 10 ** (floor(log10(val)) - 1)
                val = round(val / magnitude) * magnitude
            result.add(val)
        except ValueError:
            continue
    return result

def deadlines_compatible(km, pm_m):
    """Returns False if one market clearly resolves before the other's deadline."""
    k_close = km.close_time
    p_close = pm_m.close_time
    diff = abs((k_close - p_close).days)
    
    if diff <= 3:
        return True
    
    event_keywords = ["before gta", "before bitcoin", "before inauguration"]
    k_text = km.match_key.lower()
    p_text = pm_m.match_key.lower()
    if any(kw in k_text for kw in event_keywords) != any(kw in p_text for kw in event_keywords):
        return False
    
    return True


def llm_verify_batch(pairs):
    
    pairs_text = "\n".join(
        f"PAIR {i+1}: Kalshi='{km.match_key}' | Polymarket='{pm.match_key}'"
        for i, (km, pm) in enumerate(pairs)
    )
    prompt = f"""You are verifying prediction market pairs for cross-platform arbitrage.

    Two markets are a VALID MATCH only if they would ALWAYS resolve YES or NO together under EVERY possible real-world outcome. If ANY scenario exists where they resolve differently, return false.

    ANTONYM RULE (critical):
    - "Will X happen?" paired with "Will X NOT happen?" are OPPOSITES, not a match.
    - "Will GPT-5.6 release before July?" ≠ "Will GPT-5.6 NOT release before August?" — these move together, not against each other. NOT a match.
    - Watch for: "not", "fail to", "won't", "no deal", "remain", "stay" — these invert the resolution.

    DEADLINE RULES:
    - "before September" means "before September 1" = "by August 31". NOT "by September 30".
    - "before August" means "before August 1" = "by July 31".
    - "this year" is too vague — only match if the other market has the same implied deadline.
    - Different specific dates = different markets. "by June 30" ≠ "by August 13". Always reject.
    - A deal signed August 5 resolves "before August" NO but "by August 31" YES. NOT a match.

    SUBJECT RULES:
    - Same person/team/topic ≠ same market. The resolution condition must be identical.
    - "Messi or Ronaldo more goal contributions" ≠ "Messi and Ronaldo shake hands" — same names, completely different events.
    - "Will Haaland lead in goals?" ≠ "Will Haaland score 5+ goals?" — different conditions.
    - "Will X win Golden Ball?" ≠ "Will X be top goalscorer?" — different awards.

    VALID examples:
    - "Will GPT-5.6 release before Jul 31?" = "GPT-5.6 released by July 31?" ✓ same date, same event, no negation
    - "Will Haaland win Silver Ball?" = "Will Haaland win Silver Ball at 2026 FIFA World Cup?" ✓ same award
    - "Will Messi lead World Cup in goals?" = "Will Messi be top goalscorer at 2026 World Cup?" ✓ same condition
    - "Will X win Golden Boot?" = "Will X be top goalscorer?" ✓ Golden Boot IS the top scorer award
    

    INVALID examples:
    - "Will GPT-5.6 release before Jul 31?" ≠ "Will GPT-5.6 NOT release before August?" ✗ antonyms
    - "Will Iran deal happen before August?" ≠ "Iran deal by September 30?" ✗ before Aug = by Jul 31, not Sep 30
    - "Will Messi/Ronaldo have more goals?" ≠ "Will Messi and Ronaldo shake hands?" ✗ different events
    - "Will Haaland lead in goals?" ≠ "Will Haaland score 5+ goals?" ✗ different conditions
    - "Will X score 9+ goals?" ≠ "Will X be top goalscorer?" ✗ could lead with 8 goals
    - "Will X win Silver Boot?" ≠ "Will X be top goalscorer?" ✗ Silver Boot = 2nd top scorer, not 1st  
    - "Will X lead in goals?" ≠ "Will X be top goalscorer?" ✗ leading with fewer goals is possible

    {pairs_text}

    Return ONLY valid JSON:
    {{"results": [{{"pair": 1, "match": true, "reason": "..."}}]}}"""

    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={"model": "qwen2.5:14b", "prompt": prompt, "stream": False, "options": {"num_ctx": 4096}},
        timeout=120
    )
    text = response.json()["response"].strip()
    print(f"    [debug] {text}")
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        data = json.loads(text[start:end])
        return data.get("results", [])
    except (ValueError, json.JSONDecodeError):
        return []


def llm_verify_candidates(candidates, batch_size=10, target=10):
    confirmed = []
    batches = [candidates[i:i+batch_size] for i in range(0, len(candidates), batch_size)]
    print(f"\n--- LLM Verification ({len(batches)} batches, target={target}) ---")

    for i, batch in enumerate(batches):
        if len(confirmed) >= target:
            print(f"  Target of {target} matches reached, stopping early")
            break

        print(f"  Batch {i+1}/{len(batches)} | confirmed so far: {len(confirmed)}/{target}...")
        retries = 0
        while retries < 3:
            try:
                results = llm_verify_batch(batch)
                for r in results:
                    idx = r.get("pair", 0) - 1
                    if 0 <= idx < len(batch) and r.get("match"):
                        km, pm = batch[idx]
                        confirmed.append({"kalshi": km, "polymarket": pm, "reason": r.get("reason", "")})
                        print(f"    ✓ {km.match_key[:50]} <-> {pm.match_key[:50]}")
                        if len(confirmed) >= target:
                            break
                break
            except Exception as e:
                retries += 1
                print(f"  Retry {retries}/3: {e}")
                time.sleep(2 ** retries)
        else:
            print(f"  Batch {i+1} skipped")

    return confirmed

def shares_entity(q1, q2):
    ignore = {"will", "the", "before", "after", "when", "what", "who",
              "how", "any", "that", "this", "from", "with", "have",
              "been", "than", "their", "they", "would", "could", "should"}
    
    def get_tokens(q):
        words = re.findall(r'\b[a-zA-Z]{4,}\b', q.lower())
        return {w for w in words if w not in ignore}
    
    t1 = get_tokens(q1)
    t2 = get_tokens(q2)
    
    if t1 & t2:
        return True
    
    for w1 in t1:
        for w2 in t2:
            if w1 in w2 or w2 in w1:
                return True
    
    return False

MATCHES_FILE = "confirmed_matches.json"

def load_confirmed_matches():
    if not os.path.exists(MATCHES_FILE):
        return {}
    with open(MATCHES_FILE) as f_:
        content = f_.read().strip()
        return json.loads(content) if content else {}

def save_match(km, pm, reason, fuzzy_score, date_diff=0):
    confirmed = load_confirmed_matches()
    key = f"{km.market_id}::{pm.market_id}"
    confirmed[key] = {
        "kalshi_id": km.market_id,
        "polymarket_id": pm.market_id,
        "kalshi_question": km.match_key,
        "polymarket_question": pm.match_key,
        "reason": reason,
        "fuzzy_score": fuzzy_score,
        "date_diff_days": date_diff,
        "added": str(date.today())
    }
    with open(MATCHES_FILE, "w") as f_:
        json.dump(confirmed, f_, indent=2)

def match():
    kalshi, pm = f.find_markets(target=500)

    candidates = find_keyword_candidates(kalshi, pm)
    candidates.sort(
        key=lambda pair: fuzz.token_sort_ratio(
            pair[0].match_key.lower(), pair[1].match_key.lower()
        ),
        reverse=True
    )

    confirmed = llm_verify_candidates(candidates, batch_size=10, target=100)

    print(f"\nSaving confirmed matches:")
    print("=" * 70)
    saved = 0
    for m in confirmed:
        km, pm_m = m["kalshi"], m["polymarket"]
        score = fuzz.token_sort_ratio(km.match_key.lower(), pm_m.match_key.lower())
        date_diff = abs((km.close_time - pm_m.close_time).days)
        
        nums_k = extract_numbers(km.match_key)
        nums_p = extract_numbers(pm_m.match_key)

        print(f"  score={score:.0f} date_diff={date_diff}d | {km.match_key[:40]} <-> {pm_m.match_key[:40]}")

        if nums_k and nums_p and nums_k.isdisjoint(nums_p):
            print(f"    → rejected: number mismatch {nums_k} vs {nums_p}")
            continue

        if score < 50 and not shares_entity(km.match_key, pm_m.match_key):
            print(f"    → rejected: low fuzzy and no shared entity")
            continue
        if score < 40:
            print(f"    → rejected: fuzzy too low")
            continue
        if not deadlines_compatible(km, pm_m):
            print(f"    → rejected: deadline type mismatch")
            continue
            
        if has_antonym(km.match_key, pm_m.match_key):
            print(f"    → rejected: antonym questions")
            continue

        save_match(km, pm_m, m["reason"], score, date_diff)
        saved += 1
        print(f"    → SAVED")

    print(f"\n{saved} matches saved to {MATCHES_FILE}")
    
match()