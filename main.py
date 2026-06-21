# main.py
import time
import threading
import match_markets as matcher
import calculate_arbs as checker

MATCH_INTERVAL  = 6 * 3600   # re-run matcher every 6 hours
POLL_INTERVAL   = 60          # check arb every 60 seconds
MATCH_TARGET    = 10          # how many confirmed matches to aim for

_matching_lock = threading.Lock()
_is_matching   = False

def run_matcher():
    global _is_matching
    with _matching_lock:
        if _is_matching:
            return
        _is_matching = True
    try:
        matcher.match()
    finally:
        with _matching_lock:
            _is_matching = False

def matcher_loop():
    while True:
        run_matcher()
        print(f"[matcher] Sleeping {MATCH_INTERVAL//3600}h until next run")
        time.sleep(MATCH_INTERVAL)

def arb_loop():
    while True:
        confirmed = matcher.load_confirmed_matches()
        if not confirmed:
            print("[arb] No confirmed matches yet, waiting...")
            time.sleep(POLL_INTERVAL)
            continue

        print(f"[arb] Checking {len(confirmed)} pairs...")
        alerts = checker.run_once(confirmed)
        if alerts:
            for alert in alerts:
                checker.print_alert(alert)
        else:
            print(f"[arb] No arb found.")

        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    # Run matcher once at startup in background, arb checker in foreground
    match_thread = threading.Thread(target=matcher_loop, daemon=True)
    match_thread.start()

    # Give matcher a few seconds to start fetching before arb loop tries to read
    time.sleep(5)

    arb_loop()