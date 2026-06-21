import re
import json
import os
import time
import httpx
from datetime import date
from rapidfuzz import fuzz
import fetch_markets as f

# ── Keyword groups ────────────────────────────────────────────────
# Markets sharing keywords in the same group become candidates

KEYWORD_GROUPS = [
    {"bitcoin", "btc"},
    {"openai", "gpt-6", "gpt6"},
    {"anthropic", "claude", "mythos"},
    {"gta", "grand theft auto"},
    {"spacex", "starship"},
    {"netanyahu"},
    {"starmer"},
    {"trump"},
    {"mbappe", "mbappé", "kylian"},
    {"messi", "lionel"},
    {"ronaldo", "cristiano"},
    {"haaland", "erling"},
    {"cpi", "consumer price index"},
    {"federal reserve", "fed rate", "fomc"},
    {"unemployment", "payrolls", "nonfarm"},
    {"nvidia", "nvda"},
    {"zelensky", "ukraine", "nato"},
    {"iran", "nuclear deal"},
]

# ── Candidate generation ──────────────────────────────────────────

def find_keyword_candidates(kalshi_markets, polymarket_markets):
    candidates = []
    seen = set()

    for km in kalshi_markets:
        k_text = km.match_key.lower()
        matched_groups = [g for g in KEYWORD_GROUPS if any(kw in k_text for kw in g)]
        if not matched_groups:
            continue

        for pm in polymarket_markets:
            p_text = pm.match_key.lower()
            for group in matched_groups:
                if any(kw in p_text for kw in group):
                    key = (km.market_id, pm.market_id)
                    if key not in seen:
                        seen.add(key)
                        candidates.append((km, pm))
                    break

    print(f"  Keyword filter: {len(candidates)} candidate pairs from {len(kalshi_markets)} Kalshi × {len(polymarket_markets)} Polymarket")
    return candidates

def extract_numbers(text):
    nums = re.findall(r'\d+(?:\.\d+)?', text)
    result = set()
    for n in nums:
        try:
            val = float(n)
            if val in {2025.0, 2026.0, 2027.0} or (val == int(val) and 1 <= val <= 31):
                continue
            if val > 1000:
                from math import log10, floor
                magnitude = 10 ** (floor(log10(val)) - 1)
                val = round(val / magnitude) * magnitude
            result.add(val)
        except ValueError:
            continue
    return result

# ── LLM verification of specific pairs ───────────────────────────

def llm_verify_batch(pairs):
    pairs_text = "\n".join(
        f"PAIR {i+1}: Kalshi='{km.match_key}' | Polymarket='{pm.match_key}'"
        for i, (km, pm) in enumerate(pairs)
    )

    prompt = f"""For each pair, answer: do both markets resolve YES under the IDENTICAL real-world outcome?

{pairs_text}

Rules:
- Same event AND same resolution condition required
- Minor wording is fine: "before Aug 1" = "before August"
- NOT ok: "qualify for Final" vs "win tournament" — different conditions
- NOT ok: different date thresholds if they could resolve differently
- NOT ok: different numeric thresholds
- NOT ok: "before GTA VI" vs "before Sep 1" — one deadline is fixed, one depends on another event
- NOT ok: GPT-5.6 vs GPT-6 — different version numbers are different products

Return ONLY valid JSON:
{{"results": [{{"pair": 1, "match": true, "reason": "..."}}]}}"""

    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={"model": "llama3.1:8b", "prompt": prompt, "stream": False, "options": {"num_ctx": 4096}},
        timeout=120
    )
    text = response.json()["response"].strip()
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

# ── Persistence ───────────────────────────────────────────────────

MATCHES_FILE = "confirmed_matches.json"

def load_confirmed_matches():
    if not os.path.exists(MATCHES_FILE):
        return {}
    with open(MATCHES_FILE) as f_:
        content = f_.read().strip()
        return json.loads(content) if content else {}

def save_match(km, pm, reason, fuzzy_score, date_diff):
    confirmed = load_confirmed_matches()
    key = f"{km.market_id}::{pm.market_id}"
    confirmed[key] = {
        "kalshi_id": km.market_id,
        "polymarket_id": pm.market_id,
        "kalshi_question": km.match_key,
        "polymarket_question": pm.match_key,
        "reason": reason,
        "fuzzy_score": fuzzy_score,
        "added": str(date.today()),
        "date_diff_days": date_diff
    }
    with open(MATCHES_FILE, "w") as f_:
        json.dump(confirmed, f_, indent=2)

# ── Main ──────────────────────────────────────────────────────────
def match():
    kalshi, pm = f.find_markets(target=1000)
    matches = []

    candidates = find_keyword_candidates(kalshi, pm)
    candidates.sort(key=lambda pair: fuzz.token_sort_ratio(
        pair[0].match_key.lower(), pair[1].match_key.lower()
    ), reverse=True)
    confirmed = llm_verify_candidates(candidates, target=50)

    print(f"\nSaving confirmed matches:")
    print("=" * 70)
    saved = 0
    print(f"[matcher] LLM confirmed {len(confirmed)} matches, applying filters...")
    for m in confirmed:
        km, pm_m = m["kalshi"], m["polymarket"]
        score = fuzz.token_sort_ratio(
            km.match_key.lower(), pm_m.match_key.lower()
        )
        date_diff = abs((km.close_time - pm_m.close_time).days)
        nums_k = extract_numbers(km.match_key)
        nums_p = extract_numbers(pm_m.match_key)

        print(f"  score={score:.0f} date_diff={date_diff}d | {km.match_key[:40]} <-> {pm_m.match_key[:40]}")

        if nums_k and nums_p and nums_k.isdisjoint(nums_p):
            print(f"    → rejected: number mismatch {nums_k} vs {nums_p}")
            continue
        if score < 65:
            print(f"    → rejected: fuzzy too low")
            continue
        save_match(km, pm_m, m["reason"], score, date_diff)
        print(f"    → SAVED")
        # matches.append({"km": km, "pm_m": pm_m, "reason": m["reason"], "score": score, "date_diff": date_diff})
        
    # return matches