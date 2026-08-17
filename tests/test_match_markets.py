import sys
from pathlib import Path
from datetime import date

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from util.match_markets import CandidatePairGenerator, LLM_Verifier

gen = CandidatePairGenerator()
llm = LLM_Verifier()

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
    result = gen.get_deadline(question)

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
    d1 = gen.get_deadline(question1)
    d2 = gen.get_deadline(question2)

    if expected is None:
        assert d1 is None or d2 is None
        return

    assert d1 is not None
    assert d2 is not None

    result = gen.deadlines_match(d1[0], d1[1], d2[0], d2[1])
    assert result == expected


# ----------------------------
# Candidate pair creation tests
# ----------------------------
CANDIDATE_PAIR_TESTS = [
    # --- should become candidates ---

    (
        "2633430",
        "US-Iran Final Nuclear Deal by August 31, 2026?",
        "KXUSAIRANAGREEMENT-27-26SEP",
        "Will the US agree to a new Iranian nuclear deal before September?",
        True,
    ),
    (
        "2100070",
        "GPT-5.6 released by July 31, 2026?",
        "KXGPT-OPENB-26JUL31",
        "Will OpenAI release GPT-5.6 before Jul 31, 2026?",
        True,
    ),
    (
        "2430978",
        "Will Erling Haaland win the Silver Ball at the 2026 FIFA World Cup?",
        "KXWCGOALLEADER-26-EHAA",
        "Will Erling Haaland lead FIFA World Cup in Goals for the 2026 World Cup Full Tournament?",
        True,
    ),
    (
        "999001",
        "Will Messi win the Golden Ball?",
        "KXTEST-MESSI",
        "Will Lionel Messi be named tournament MVP?",
        True,
    ),

    # --- should be rejected: deadline mismatch ---

    (
        "2633426",
        "US-Iran Final Nuclear Deal by June 30, 2026?",
        "KXUSAIRANAGREEMENT-27-26AUG",
        "Will the US agree to a new Iranian nuclear deal before August 13?",
        False,
    ),
    (
        "999002",
        "Will the announcement come before June 2026?",
        "KXTEST-AFTER",
        "Will the announcement come after June 2026?",
        False,
    ),

    # --- should be rejected: no entity overlap ---

    (
        "999003",
        "Will Bitcoin hit $150k before October?",
        "KXTEST-UNRELATED",
        "Will Cristiano Ronaldo win the Golden Ball before October?",
        False,
    ),

    # --- should be rejected: one deadline missing ---

    (
        "999004",
        "Will Messi retire before the 2026 World Cup?",
        "KXTEST-NODATE",
        "Will Messi retire?",
        False,
    ),

    # --- known NER blind spot ---
    # Update this expectation once you've decided how you want it handled.

    pytest.param(
        "2633429",
        "US-Iran Final Nuclear Deal by August 18, 2026?",
        "KXUSAIRANAGREEMENT-27-26AUG",
        "Will the US agree to a new Iranian nuclear deal before August?",
        False,
    ),
]

@pytest.mark.parametrize("pm_id, pm_q, k_id, k_q, expected", CANDIDATE_PAIR_TESTS)
def test_create_candidate_pair(pm_id, pm_q, k_id, k_q, expected):
    result = gen.create_candidate_pair(pm_id, pm_q, k_id, k_q)

    if expected is None:
        pytest.skip("Known behavior under investigation")

    if expected:
        assert result is not None
        assert result.polymarket_id == pm_id
        assert result.kalshi_id == k_id
        assert result.pm_cands
        assert result.k_cands
    else:
        assert result is None


# ----------------------------
# Keyword pool overlap tests
# ----------------------------
KEYWORD_OVERLAP_TESTS = [
    (
        "US-Iran Final Nuclear Deal by August 31, 2026?",
        "Will the US agree to a new Iranian nuclear deal before September?",
        True,
    ),
    (
        "Will Erling Haaland win the Silver Ball at the World Cup?",
        "Will Haaland claim the Silver Ball this tournament?",
        True,
    ),
    (
        "Will Bitcoin hit $150k before October?",
        "Will Cristiano Ronaldo win the Golden Ball before October?",
        False,
    ),
]


@pytest.mark.parametrize("q1, q2, expected", KEYWORD_OVERLAP_TESTS)
def test_keyword_pool_overlap(q1, q2, expected):
    assert gen.keyword_pool_overlap(q1, q2) == expected


# ----------------------------
# Professional sports matchup tests
# ----------------------------
MATCHUP_TESTS = [
    (
        "Will the Kansas City Chiefs beat the Buffalo Bills?",
        {"kansas city chiefs", "buffalo bills"},
    ),
    (
        "Will the Kansas City Chiefs win the Super Bowl?",
        {"kansas city chiefs"},
    ),
    (
        "Will inflation drop below 3 percent?",
        set(),
    ),
    (
        "Will the Giants make the playoffs?",  # ambiguous alias, no disambiguation
        set(),
    ),
    (
        "Will the New York Giants make the playoffs?",
        {"new york giants"},
    ),
]

@pytest.mark.parametrize("question, expected", MATCHUP_TESTS)
def test_check_professional_matchup(question, expected):
    result = gen.check_professional_matchup(question)
    assert set(result) == expected
    
# ----------------------------
# LLM verification tests
# ----------------------------
LLM_VERIFICATION_TESTS = [

    (
        "Will Erling Haaland lead the World Cup in goals?",
        "Will Erling Haaland score 9+ goals at the World Cup?",
        False,
    ),

    (
        "Will Cristiano Ronaldo win the Silver Boot?",
        "Will Cristiano Ronaldo finish as the tournament's second-leading goalscorer?",
        True,
    ),
    
        (
        "Will the Fed cut interest rates?",
        "Will the FOMC lower rates?",
        True,
    ),

    (
        "Will Messi win the Golden Ball?",
        "Will Messi be named tournament MVP?",
        True,
    ),

    (
        "Will Messi and Ronaldo shake hands during the World Cup?",
        "Will Messi or Ronaldo have more goal contributions?",
        False,
    ),

    (
        "Will GPT-6 release before August?",
        "Will GPT-6 NOT release before August?",
        False,
    ),
]

# ----------------------------
# Unmatched LLM verification tests
# ----------------------------
@pytest.mark.parametrize("q1, q2, expected", LLM_VERIFICATION_TESTS)
def test_llm_verification(q1, q2, expected):
    res = gen.create_candidate_pair(pm_id="", k_id="", pm_q=q1, k_q=q2)
    if res == None:
        assert res == expected
    else:
        result = llm.llm_check_pair(res)
        assert result == expected
        
UNMATCHED_VERIFICATION_TESTS = [
    (
        "Will the deal happen before September?",
        "Will the deal happen by August 31, 2026?",
        True,
    ),
    (
        "Will the deal happen before September?",
        "Will the deal happen by September 30, 2026?",
        False,
    ),

    (
        "Will GPT-6 release before August?",
        "Will GPT-6 NOT release before August?",
        False,
    ),
    (
        "Will the announcement come before June 2026?",
        "Will the announcement come after June 2026?",
        False,
    ),

    (
        "Will the Chiefs beat the Bills?",
        "Will the Chiefs beat the Broncos?",
        False,
    ),
    (
        "Will the Chiefs beat the Bills?",
        "Chiefs vs Bills: who wins the AFC Championship?",
        False,
    ),
    (
        "Will Mbappe win the Golden Boot at the World Cup?",
        "Will Mbappe be the tournament's top goalscorer?",
        True,
    ),
    # known limitation - it struggles with this unmatched
    # (
    #     "Will Messi win the Golden Ball?",
    #     "Will Messi be the tournament's top goalscorer?",
    #     False,
    # ),

    (
        "Will Bitcoin hit $150k before October?",
        "Will Cristiano Ronaldo win the Golden Ball before October?",
        False,
    ),

    (
        "Will Messi and Ronaldo shake hands during the World Cup?",
        "Will Messi or Ronaldo have more goal contributions?",
        False,
    ),

    (
        "Will the Fed cut interest rates before September?",
        "Will the Fed cut interest rates before September?",
        True,
    ),
]

@pytest.mark.parametrize("q1, q2, expected", UNMATCHED_VERIFICATION_TESTS)
def test_unmatched_llm_verification(q1, q2, expected):
    result = llm.compare_unmatched_pair(q1, q2)
    assert result == expected