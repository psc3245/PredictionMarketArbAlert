import sys
from pathlib import Path
from datetime import date

import pytest

# Add v2 directory to Python path so we import util/match_markets.py
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from util.match_markets import get_deadline, deadlines_match


# ----------------------------
# Date extraction tests
# ----------------------------

DATE_TESTS = [
    (
        "US-Iran Final Nuclear Deal by August 31, 2026?",
        ("by", "08-31-2026"),
    ),
    (
        "Will the Fed cut rates before September?",
        ("before", "09-01-2026"),
    ),
    (
        "Will Bitcoin hit $150k before October?",
        ("before", "10-01-2026"),
    ),
    (
        "Will GPT-6 release by Aug. 15, 2026?",
        ("by", "08-15-2026"),
    ),
    (
        "Will the deal be signed by August 31st, 2026?",
        ("by", "08-31-2026"),
    ),
    (
        "Will the deal happen before September, having missed the August deadline?",
        ("before", "09-01-2026"),
    ),
    (
        "Will the announcement come this month?",
        (None, f"{str(date.today().month+1).zfill(2)}-01-{date.today().year}"),
    ),
    (
        "Will they win on the first attempt?",
        None,
    ),
    (
        "Will X happen in 2027?",
        ("by", "12-31-2027"),
    ),
    (
        "Will it happen by end of year, before December 2026?",
        ("before", "12-01-2026"),
    ),
    (
        "Will the vote happen before the thirty-first of August?",
        ("before", "08-31-2026"),
    ),
    (
        "Will Team A beat Team B in the championship?",
        None,
    ),
    (
        "Will inflation numbers change the outlook?",
        None,
    ),
    (
        "Will the 2026 deal be finalized, extending the 2027 negotiation window?",
        ("by", "12-31-2026"),
    ),
    (
        "Will GPT-5.6 launch by July,31 2026?",
        ("by", "07-31-2026"),
    ),
]


@pytest.mark.parametrize("question, expected", DATE_TESTS)
def test_get_deadline(question, expected):
    result = get_deadline(question)

    if expected is None:
        assert result is None
    else:
        qualifier, deadline, _ = result
        assert (qualifier, deadline) == expected


# ----------------------------
# Deadline matching tests
# ----------------------------

DEADLINE_PAIRS = [
    # Compatible
    (
        "Will the Fed cut rates before October?",
        "Fed rate cut by September 30, 2026?",
        True,
    ),
    (
        "Will GPT-6 release before Aug 1, 2026?",
        "GPT-6 released by July 31, 2026?",
        True,
    ),
    (
        "Will the US agree to a new Iranian deal this year?",
        "US-Iran nuclear deal by December 31, 2026?",
        True,
    ),
    (
        "Will Bitcoin hit $150k before September 1, 2026?",
        "Bitcoin all-time high by August 31, 2026?",
        True,
    ),

    # Incompatible
    (
        "Will the Iran deal happen before August 13, 2026?",
        "US-Iran deal by September 30, 2026?",
        False,
    ),
    (
        "Will the announcement come before June 2026?",
        "Will the announcement come after June 2026?",
        False,
    ),
    (
        "Will Team A win the championship by August 5, 2026?",
        "Team A championship win by August 25, 2026?",
        False,
    ),

    # Missing deadlines
    (
        "Will Messi retire before the 2026 World Cup?",
        "Will Messi retire?",
        None,
    ),
    (
        "Will Team A beat Team B in the championship?",
        "Will Team A win the trophy?",
        None,
    ),
    (
        "Will Haaland win the Golden Ball by December 2026?",
        "Will Haaland win the Golden Ball?",
        None,
    ),
]


@pytest.mark.parametrize("question1, question2, expected", DEADLINE_PAIRS)
def test_deadlines_match(question1, question2, expected):
    d1 = get_deadline(question1)
    d2 = get_deadline(question2)

    if expected is None:
        assert d1 is None or d2 is None
        return

    assert d1 is not None
    assert d2 is not None

    result = deadlines_match(
        d1[0],
        d1[1],
        d2[0],
        d2[1],
    )

    assert result == expected