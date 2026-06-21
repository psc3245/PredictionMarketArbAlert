import re
import json
import fetch_markets as f
from rapidfuzz import fuzz
from google import genai
from dotenv import load_dotenv
from datetime import date
import os
import time
from groq import Groq
import httpx

MATCHES_FILE = "confirmed_matches.json"

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GROQ_API_KEY=os.getenv("GROQ_API_KEY_2")

# ── Normalization helpers ─────────────────────────────────────────

def normalize(text):
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    stop_words = {
        "will", "the", "a", "an", "of", "in", "for", "by", "before", "after", "to", "and",
        "is", "on", "this", "market", "resolve", "resolves", "resolved", "yes", "no",
        "if", "then", "according", "from", "that", "it", "be", "who", "what", "when",
        "where", "any", "at", "which", "has", "have", "with", "or", "than", "otherwise",
        "immediately", "result", "results", "occur", "occurs", "event", "events",
        "specified", "title", "contract", "question", "national", "team", "officially"
    }
    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words)

def extract_numbers(text):
    nums = re.findall(r'\d+(?:\.\d+)?', text)
    normalized_nums = []
    for n in nums:
        try:
            val = float(n)
            if val not in [2025.0, 2026.0, 2027.0]:
                normalized_nums.append(val)
        except ValueError:
            continue
    return set(normalized_nums)

# ── LLM matching ──────────────────────────────────────────────────

def llm_match_batch(kalshi_batch, polymarket_markets):
    k_list = "\n".join(f"{m.market_id}: {m.match_key}" for m in kalshi_batch)
    p_list = "\n".join(f"{m.market_id}: {m.match_key}" for m in polymarket_markets)

    prompt = f"""You are matching prediction markets across two platforms for arbitrage.

        TWO MARKETS MATCH ONLY IF they would ALWAYS resolve YES or NO together under every possible real-world outcome.

        STRICT RULES:
        - "Netherlands win World Cup" ≠ "Netherlands qualify for Semifinals" — different conditions
        - "OpenAI IPO before Aug 1" = "OpenAI announces IPO before August" — same event, fine
        - "Bitcoin above $150k by Jul 31" ≠ "Bitcoin above $150k by Dec 31" — different dates, NOT a match
        - Do NOT match markets just because they involve the same person/team/topic
        - Do NOT combine two separate real-world events into one match
        - When in doubt, return NO match

        KALSHI:
        {k_list}

        POLYMARKET:
        {p_list}

        Return ONLY valid JSON:
        {{"matches": [{{"kalshi_id": "...", "polymarket_id": "...", "reason": "..."}}]}}"""

    
    # response = client.models.generate_content(
    # model='gemini-2.5-flash',
    # contents={'text': prompt},
    # config={
    #     'temperature': 0,
    #     'top_p': 0.95,
    #     'top_k': 20,
    # },
    # )
    
    # response = client.chat.completions.create(
    #     model="llama-3.3-70b-versatile",
    #     messages=[{"role": "user", "content": prompt}],
    #     max_tokens=4096
    # )
    
    response = httpx.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_ctx": 8192}  # default 4096 is too small for your prompts
        },
        timeout=300  # local is slow, give it time
    )

    # text = response.text.strip()
    # text = response.choices[0].message.content.strip() 
    
    text = response.json()["response"].strip()
    print(f"    [debug] {text[:200]}")
    if "```" in text:
        text = text.split("```")[1].lstrip("json").strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        text = text[start:end]
        return json.loads(text).get("matches", [])
    except (ValueError, json.JSONDecodeError):
        print("    [warn] JSON parse failed")
        return []


def llm_match_markets(kalshi_markets, polymarket_markets, batch_size=30):
    # client = genai.Client(api_key=GEMINI_API_KEY)s
    # client = Groq(api_key=GROQ_API_KEY)
    all_matches = []
    seen = set()

    batches = [kalshi_markets[i:i+batch_size] for i in range(0, len(kalshi_markets), batch_size)]
    print(f"\n--- LLM Matching ({len(batches)} batches) ---")

    start = time.time()
    for i, batch in enumerate(batches):
        batch_start = time.time()
        print(f"  Batch {i+1}/{len(batches)} ({len(batch)} Kalshi markets)...")
        
        retries = 0
        while retries < 3:
            try:
                matches = llm_match_batch(batch, polymarket_markets)
                for m in matches:
                    key = (m["kalshi_id"], m["polymarket_id"])
                    if key not in seen:
                        seen.add(key)
                        all_matches.append(m)
                print(f"  → {len(matches)} matches found")
                break
            except Exception as e:
                retries += 1
                print(f"  Model unavailable (attempt {retries}/3), sleeping...")
                time.sleep(2 ** retries)
        else:
            print(f"  Batch {i+1} failed after 3 attempts, skipping")
        print(f"Time elapsed for batch {i+1}: {time.time() - batch_start} s")
    
    print(f"Total Time: {time.time() - start} s")

    return all_matches


def verify_llm_matches(matches, kalshi_markets, polymarket_markets):
    k_by_id = {m.market_id: m for m in kalshi_markets}
    p_by_id = {m.market_id: m for m in polymarket_markets}

    verified = []
    for match in matches:
        km = k_by_id.get(match["kalshi_id"])
        pm = p_by_id.get(match["polymarket_id"])
        if not km or not pm:
            print(f"  [warn] ID not found: {match['kalshi_id']} / {match['polymarket_id']}")
            continue

        score = fuzz.token_sort_ratio(
            normalize(km.match_key),
            normalize(pm.match_key)
        )
        confidence = "HIGH" if score > 60 else "MEDIUM" if score > 30 else "SUSPICIOUS"

        verified.append({
            "kalshi": km,
            "polymarket": pm,
            "reason": match.get("reason", ""),
            "fuzzy_score": score,
            "confidence": confidence
        })

    for v in verified:
        add_confirmed_match(v["kalshi"], v["polymarket"], v["reason"], v["fuzzy_score"])
    return verified

# ── Fuzzy matching (fallback / supplement) ────────────────────────

def find_matches_fuzzy(kalshi_markets, polymarket_markets, min_score=80):
    matches = []

    for km in kalshi_markets:
        raw_k = km.question.lower()
        norm_k = normalize(km.question)
        nums_k = extract_numbers(km.question)

        for pm in polymarket_markets:
            raw_p = pm.question.lower()
            norm_p = normalize(pm.question)

            score_set  = fuzz.token_set_ratio(norm_k, norm_p)
            score_sort = fuzz.token_sort_ratio(normalize(km.match_key), normalize(pm.match_key))
            score = (score_set + score_sort) / 2

            if score < min_score:
                continue

            date_diff = abs((km.close_time - pm.close_time).days)
            nums_p = extract_numbers(pm.question)

            number_mismatch = bool(nums_k) and bool(nums_p) and nums_k.isdisjoint(nums_p)

            elimination_words = {"eliminat", "exit", "knocked"}
            win_words         = {"win", "wins", "winner", "champion"}
            k_elim = any(w in norm_k for w in elimination_words)
            p_win  = any(w in norm_p for w in win_words)
            k_win  = any(w in norm_k for w in win_words)
            p_elim = any(w in norm_p for w in elimination_words)
            antonym_mismatch = (k_elim and p_win and not k_win) or (p_elim and k_win and not p_elim)

            sport_tags = {"t20", "cricket", "tennis", "rugby", "nba", "nfl", "wnba"}
            k_sports = {s for s in sport_tags if s in norm_k}
            p_sports = {s for s in sport_tags if s in norm_p}
            wrong_sport = bool(k_sports) and bool(p_sports) and k_sports.isdisjoint(p_sports)

            scope_terms = {"1st half", "first half", "group b", "group a", "round of", "group stage"}
            k_scope = any(t in raw_k for t in scope_terms)
            p_scope = any(t in raw_p for t in scope_terms)

            confederation_terms = {"caf", "uefa", "conmebol", "concacaf", "afc", "ofc"}
            k_continent = any(t in norm_k for t in confederation_terms)
            p_continent = any(t in norm_p for t in confederation_terms)

            derivative_markers = ["best host", "furthest", "no prior", "first time", "furthest advancing", "best performing"]
            k_deriv = any(m in raw_k for m in derivative_markers)
            p_deriv = any(m in raw_p for m in derivative_markers)
            
            # "team from group" (generic group winner) ≠ specific team group stage win
            team_from_group_k = "team from group" in raw_k
            team_from_group_p = "team from group" in raw_p
            group_structure_mismatch = team_from_group_k != team_from_group_p

            dealbreakers = [
                ("qualify" in norm_k) != ("qualify" in norm_p),
                ("final"   in norm_k) != ("final"   in norm_p),
                antonym_mismatch,
                wrong_sport,
                k_scope != p_scope,
                k_continent != p_continent,
                k_deriv != p_deriv,
                group_structure_mismatch,
            ]

            if date_diff <= 50 and not number_mismatch and not any(dealbreakers):
                matches.append((km, pm, score))

    return sorted(matches, key=lambda x: x[2], reverse=True)

# ── Display helpers ───────────────────────────────────────────────

def print_llm_results(verified):
    print(f"\nLLM found {len(verified)} verified matches:")
    print("=" * 70)
    for v in verified:
        km, pm = v["kalshi"], v["polymarket"]
        print(f"[{v['confidence']} | fuzzy={v['fuzzy_score']}]")
        print(f"  Kalshi:  {km.market_id} | {km.match_key[:80]}")
        print(f"  Poly:    {pm.market_id} | {pm.match_key[:80]}")
        print(f"  Reason:  {v['reason']}")
        print("-" * 70)

def print_fuzzy_results(matches):
    print(f"\nFuzzy found {len(matches)} matches (top 20):")
    print("=" * 70)
    for km, pm, score in matches[:20]:
        print(f"[{score:.1f}%]")
        print(f"  Kalshi: {km.market_id} | {km.match_key[:80]}")
        print(f"  Poly:   {pm.market_id} | {pm.match_key[:80]}")
        print("-" * 70)

def load_confirmed_matches():
    if not os.path.exists(MATCHES_FILE):
        return {}
    with open(MATCHES_FILE) as f:
        content = f.read().strip()
        if not content:
            return {}
        return json.loads(content)

def save_confirmed_matches(matches_dict):
    with open(MATCHES_FILE, "w") as f:
        json.dump(matches_dict, f, indent=2)

def add_confirmed_match(km, pm, reason, fuzzy_score):
    confirmed = load_confirmed_matches()
    key = f"{km.market_id}::{pm.market_id}"
    confirmed[key] = {
        "kalshi_id": km.market_id,
        "polymarket_id": pm.market_id,
        "kalshi_question": km.match_key,
        "polymarket_question": pm.match_key,
        "reason": reason,
        "fuzzy_score": fuzzy_score,
        "added": str(date.today())
    }
    save_confirmed_matches(confirmed)
    
    
if __name__ == "__main__":
    kalshi, pm = f.find_markets(target=150)

    # Primary: LLM matching
    raw_matches = llm_match_markets(kalshi, pm)
    verified    = verify_llm_matches(raw_matches, kalshi, pm)
    print_llm_results(verified)

    # Secondary: fuzzy matching (supplement / sanity check)
    print("\n--- Fuzzy Matching (supplement) ---")
    fuzzy_matches = find_matches_fuzzy(kalshi, pm, min_score=80)
    print_fuzzy_results(fuzzy_matches)