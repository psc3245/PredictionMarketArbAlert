import httpx
import json
import time
from match_markets import load_confirmed_matches

def fetch_kalshi_price(market_id):
    response = httpx.get(
        f"https://external-api.kalshi.com/trade-api/v2/markets/{market_id}",
        timeout=10
    )
    m = response.json()["market"]
    return {
        "yes_ask": float(m["yes_ask_dollars"]),
        "yes_bid": float(m["yes_bid_dollars"]),
        "no_ask": round(1 - float(m["yes_bid_dollars"]), 4),
        "no_bid": round(1 - float(m["yes_ask_dollars"]), 4),
    }

def fetch_polymarket_price(market_id):
    response = httpx.get(
        f"https://gamma-api.polymarket.com/markets/{market_id}",
        timeout=10
    )
    d = response.json()

    yes_ask = float(d.get("bestAsk") or 0)
    yes_bid = float(d.get("bestBid") or 0)

    if yes_ask == 0 or yes_bid == 0:
        return None

    return {
        "yes_ask": yes_ask,
        "yes_bid": yes_bid,
        "no_ask": round(1 - yes_bid, 4),
        "no_bid": round(1 - yes_ask, 4),
    }

MIN_PROFIT = 0.03

def check_arb(kp, pp, match):
    if kp is None or pp is None:
        return None

    # Leg A: buy YES on Kalshi, buy NO on Polymarket
    cost_a = kp["yes_ask"] + pp["no_ask"]
    profit_a = round(1 - cost_a, 4)

    # Leg B: buy NO on Kalshi, buy YES on Polymarket
    cost_b = kp["no_ask"] + pp["yes_ask"]
    profit_b = round(1 - cost_b, 4)

    best_profit = max(profit_a, profit_b)
    if best_profit < MIN_PROFIT:
        return None

    leg = "YES Kalshi / NO Poly" if profit_a > profit_b else "NO Kalshi / YES Poly"
    return {
        "kalshi_id":          match["kalshi_id"],
        "polymarket_id":      match["polymarket_id"],
        "kalshi_question":    match["kalshi_question"],
        "polymarket_question": match["polymarket_question"],
        "leg":                leg,
        "profit_per_dollar":  best_profit,
        "kalshi_prices":      kp,
        "poly_prices":        pp,
    }

def run_once(confirmed):
    alerts = []
    for key, match in confirmed.items():
        try:
            kp = fetch_kalshi_price(match["kalshi_id"])
            pp = fetch_polymarket_price(match["polymarket_id"])
            if pp is None:
                print(f"  [skip] {match['kalshi_id']} — Polymarket inactive")
                continue
            result = check_arb(kp, pp, match)
            if result:
                alerts.append(result)
        except Exception as e:
            print(f"  [error] {match['kalshi_id']}: {e}")
    return alerts

def print_alert(alert):
    print("\n🚨 ARB OPPORTUNITY FOUND 🚨")
    print(f"  Kalshi:     {alert['kalshi_question']}")
    print(f"  Polymarket: {alert['polymarket_question']}")
    print(f"  Leg:        {alert['leg']}")
    print(f"  Profit:     ${alert['profit_per_dollar']:.4f} per $1 wagered")
    print(f"  K prices:   yes_ask={alert['kalshi_prices']['yes_ask']} no_ask={alert['kalshi_prices']['no_ask']}")
    print(f"  P prices:   yes_ask={alert['poly_prices']['yes_ask']} no_ask={alert['poly_prices']['no_ask']}")

if __name__ == "__main__":
    POLL_INTERVAL = 60  # seconds

    print("Starting arb checker...")
    while True:
        confirmed = load_confirmed_matches()
        if not confirmed:
            print("No confirmed matches yet — run match_markets.py first")
            time.sleep(POLL_INTERVAL)
            continue

        print(f"Checking {len(confirmed)} confirmed pairs...")
        alerts = run_once(confirmed)

        if alerts:
            for alert in alerts:
                print_alert(alert)
        else:
            print(f"  No arb found. Next check in {POLL_INTERVAL}s")

        time.sleep(POLL_INTERVAL)