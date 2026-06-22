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

def llm_verify_batch(pairs):
    
    pairs_text = "\n".join(
        f"PAIR {i+1}: Kalshi='{km.match_key}' | Polymarket='{pm.match_key}'"
        for i, (km, pm) in enumerate(pairs)
    )

    prompt = f"""You are matching prediction markets across two platforms for arbitrage.

TWO MARKETS MATCH ONLY IF they would ALWAYS resolve YES or NO together under every possible real-world outcome.

STRICT RULES — read carefully:
- "before Aug 1" ≠ "before GTA VI" — one is a fixed date, one depends on another event. NEVER match these.
- "GPT-5.6" ≠ "GPT-6" — different model versions. NEVER match.
- "qualify for Round of 16" ≠ "win the World Cup" — different conditions.
- "What will Trump say during X speech?" is about speech content, NOT about Trump leaving office.
- Different specific dates = different markets ("by June 30" ≠ "by August 1").
- Same topic ≠ same market. Both must resolve YES under the identical real-world scenario.
- When in doubt, return false.

PASS examples:
- "Will GPT-6 release before Sep 1?" = "Will GPT-6 release by September 2026?" ✓ same deadline
- "Will Netanyahu leave office before Aug 1?" = "Will Netanyahu be out by August?" ✓ same event and deadline

FAIL examples:
- "Will GPT-6 release before Aug 1?" ≠ "Will GPT-6 release before GTA VI?" ✗ different deadline types
- "Will 5 Trump endorsees lose primaries?" ≠ "Will Trump meet Putin in US?" ✗ completely different events
- "Will GPT-5.6 release before Jul 31?" ≠ "Will GPT-6 release before GTA VI?" ✗ different model versions

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
    """Check if two questions share a meaningful named entity."""
    entities1 = set(re.findall(r'\b[A-Z][a-z]+\b|\b\d+(?:\.\d+)?[kKmMbBtT]?\b', q1))
    entities2 = set(re.findall(r'\b[A-Z][a-z]+\b|\b\d+(?:\.\d+)?[kKmMbBtT]?\b', q2))
    
    ignore = {"Will", "The", "Before", "After", "When", "What", "Who", 
              "How", "Any", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"}
    entities1 -= ignore
    entities2 -= ignore
    
    return bool(entities1 & entities2)

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
    kalshi, pm = f.find_markets(target=2000)

    candidates = find_keyword_candidates(kalshi, pm)
    candidates.sort(
        key=lambda pair: fuzz.token_sort_ratio(
            pair[0].match_key.lower(), pair[1].match_key.lower()
        ),
        reverse=True
    )

    confirmed = llm_verify_candidates(candidates, batch_size=10, target=50)

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

        if score < 55 and not shares_entity(km.match_key, pm_m.match_key):
            print(f"    → rejected: low fuzzy and no shared entity")
            continue

        if score < 40:
            print(f"    → rejected: fuzzy too low")
            continue

        save_match(km, pm_m, m["reason"], score, date_diff)
        saved += 1
        print(f"    → SAVED")

    print(f"\n{saved} matches saved to {MATCHES_FILE}")