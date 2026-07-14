import sys
from pathlib import Path

# Add v2 directory to Python path so we import util/match_markets.py
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from util.match_markets import get_deadline


# ----------------------------
# Date extraction tests
# ----------------------------

def test_get_deadline_dates():

    tests = [
        (
            "US-Iran Final Nuclear Deal by August 31, 2026?",
            ("by", "08-31-2026")
        ),
        (
            "Will the Fed cut rates before September?",
            ("before", "09-01-2026")
        ),
        (
            "Will Bitcoin hit $150k before October?",
            ("before", "10-01-2026")
        ),
        (
            "Will GPT-6 release by Aug. 15, 2026?",
            ("by", "08-15-2026")
        ),
        (
            "Will the deal be signed by August 31st, 2026?",
            ("by", "08-31-2026")
        ),
        (
            "Will the deal happen before September, having missed the August deadline?",
            ("before", "09-01-2026")
        ),
        (
            "Will the announcement come this month?",
            (None, "07-01-2026")
        ),
        (
            "Will they win on the first attempt?",
            None
        ),
        (
            "Will X happen in 2027?",
            ("by", "12-31-2027")
        ),
        (
            "Will it happen by end of year, before December 2026?",
            ("before", "12-01-2026")
        ),
        (
            "Will the vote happen before the thirty-first of August?",
            ("before", "08-31-2026")
        ),
        (
            "Will Team A beat Team B in the championship?",
            None
        ),
        (
            "Will inflation numbers change the outlook?",
            None
        ),
        (
            "Will the 2026 deal be finalized, extending the 2027 negotiation window?",
            ("by", "12-31-2026")
        ),
        (
            "Will GPT-5.6 launch by July,31 2026?",
            ("by", "07-31-2026")
        ),
    ]

    for question, expected in tests:
        assert get_deadline(question) == expected