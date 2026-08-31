"""
Bug-hunting tests for the matching pipeline.

Each test below encodes what the CORRECT behavior should be. A failing
test means the current code has that bug. Run with:

    pytest tests/test_matching_bugs.py -v

and paste the output back for triage. Nothing in util/ was changed to
make these pass - they're diagnostic only.
"""
import sys
from pathlib import Path
from datetime import date
from unittest import mock

import pytest
import spacy

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from util.match_markets import CandidatePairGenerator
from util.market_processor import MarketPreprocessor, LookupTable

nlp = spacy.load("en_core_web_lg")

gen = CandidatePairGenerator(nlp)
pre = MarketPreprocessor(nlp)


class FakeOldMarket:
    """Stand-in for the `Market` dataclass in models.py, matching the
    duck-typed interface MarketPreprocessor.preprocess() expects."""
    def __init__(self, platform, market_id, question):
        self.platform = platform
        self.market_id = market_id
        self.question = question
        self.match_key = question
        self.url = ""


# ----------------------------------------------------------------------
# Bug 1: deadline qualifier (before/by/after) is picked by "does this
# word appear anywhere in the sentence", not by which one is actually
# attached to the date. before/by collapse to the same bucket in
# deadlines_match so mixing those two is harmless, but picking
# before/by over a real "after" (or vice versa) flips the comparison
# outcome entirely.
# ----------------------------------------------------------------------
QUALIFIER_PROXIMITY_TESTS = [
    (
        "Will the bill pass by unanimous vote after November 2026?",
        ("after", "11-01-2026"),
    ),
    (
        "Will the trade happen by Friday's deadline, after which talks resume, before December 2026?",
        ("before", "12-01-2026"),
    ),
]

@pytest.mark.parametrize("question, expected", QUALIFIER_PROXIMITY_TESTS)
def test_deadline_qualifier_matches_word_nearest_the_date(question, expected):
    qualifier, deadline, _ = gen.get_deadline(question)
    assert (qualifier, deadline) == expected, (
        "get_deadline picks the qualifier by scanning the whole sentence "
        "for 'before'/'by'/'after' in that fixed priority order, not by "
        "proximity to the actual date it extracted."
    )


# ----------------------------------------------------------------------
# Bug 2: "this month" resolves to next month (correct, since it means
# "before next month starts"), but doesn't roll the year over in
# December - it produces a January date in the CURRENT (already-past)
# year instead of the following year.
# ----------------------------------------------------------------------
def test_this_month_deadline_rolls_over_year_in_december():
    with mock.patch("util.match_markets.date") as mock_date:
        mock_date.today.return_value = date(2026, 12, 15)
        mock_date.side_effect = lambda *a, **kw: date(*a, **kw)

        result = gen.get_deadline("Will the announcement come this month?")

    qualifier, deadline, _ = result
    assert deadline == "01-01-2027", (
        "In December, 'this month' should roll over into January of "
        "NEXT year, not January of the current year (which is already "
        "in the past relative to the December question)."
    )


# ----------------------------------------------------------------------
# Bug 3: constants.YEARS is a hardcoded ["2026", "2027", "2028"] list.
# Any question mentioning a year outside that window fails to extract
# a deadline at all, even when the year is written explicitly.
# ----------------------------------------------------------------------
FAR_FUTURE_YEAR_TESTS = [
    "Will X happen by 2029?",
    "Will X happen by 2030?",
]

@pytest.mark.parametrize("question", FAR_FUTURE_YEAR_TESTS)
def test_explicit_future_year_outside_hardcoded_list_is_still_recognized(question):
    result = gen.get_deadline(question)
    assert result is not None, (
        "constants.YEARS only lists 2026-2028, so any explicitly stated "
        "year beyond that silently fails to parse as a deadline at all "
        "(get_deadline returns None even though a year is right there "
        "in the text)."
    )


# ----------------------------------------------------------------------
# Bug 4: has_negation() is a binary "contains any negation word" check.
# It doesn't track parity, so a double negation (which flips back to a
# positive/affirmative meaning) is indistinguishable from a single
# negation. Two questions with OPPOSITE real-world meanings can both
# be flagged has_negation=True and sail through the negation-mismatch
# guard as "consistent".
# ----------------------------------------------------------------------
def test_double_negation_is_distinguished_from_single_negation():
    single = "Will the deal fail to happen by December 2026?"
    double = "Will the deal not fail to happen by December 2026?"

    assert gen.has_even_negation(single) != gen.has_even_negation(double), (
        "'fail to happen' and 'not fail to happen' mean opposite things, "
        "but has_negation() just checks for presence of any negation "
        "word and returns True for both."
    )


def test_negation_mismatch_guard_rejects_opposite_meaning_pair():
    pm_q = "Will the merger fail to close by December 2026?"
    k_q = "Will the merger not fail to close by December 2026?"

    result = gen.create_candidate_pair("PM1", pm_q, "K1", k_q)
    assert result is None, (
        "These two questions are logical opposites (single vs. double "
        "negation), but create_candidate_pair's deterministic negation "
        "guard doesn't catch it - both sides register has_negation=True "
        "so the pair is waved through to the LLM stage instead of being "
        "rejected outright."
    )


# ----------------------------------------------------------------------
# Bug 5: deadlines_match's before/after "crossing" case only accepts
# EXACT 1-day adjacency (date2 + 1 == date1). Two windows that
# genuinely overlap by more than a single day at the boundary are
# rejected as incompatible.
# ----------------------------------------------------------------------
def test_deadlines_match_accepts_genuinely_overlapping_before_after_windows():
    # "before Sept 2" covers ... through Sept 1.
    # "after Aug 30" covers Aug 31 onward.
    # These overlap on Aug 31 - Sept 1, so they should be compatible.
    d1 = gen.get_deadline("Will it happen before September 2, 2026?")
    d2 = gen.get_deadline("Will it happen after August 30, 2026?")

    result = gen.deadlines_match(d1[0], d1[1], d2[0], d2[1])
    assert result is True, (
        "deadlines_match only accepts a before/after crossing when the "
        "two boundary dates are exactly one day apart (date2+1==date1). "
        "It rejects windows that genuinely overlap by a wider margin."
    )


# ----------------------------------------------------------------------
# Bug 6: the LookupTable used to generate candidate pairs in production
# (generate_pairs.py -> MarketPreprocessor + LookupTable) indexes ONLY
# raw spaCy entities and the predefined KEYWORD_GROUPS - team name
# dictionaries (NFL_TEAMS, NBA_TEAMS, ...) are never part of the index.
# A pair that check_professional_matchup would confirm is the same
# matchup can therefore never even reach create_candidate_pair, because
# the blocking step drops it first.
# ----------------------------------------------------------------------
def test_lookup_table_surfaces_matches_the_verifier_would_confirm():
    pm_q = "Will the Chiefs beat the Bills?"
    k_q = "Kansas City Chiefs vs Buffalo Bills: Winner?"

    # Sanity check: the final verifier's own team-matching logic agrees
    # these describe the same matchup.
    assert gen.check_professional_matchup(pm_q) and gen.check_professional_matchup(k_q)
    assert set(gen.check_professional_matchup(pm_q)) == set(gen.check_professional_matchup(k_q))

    m_pm = pre.preprocess(FakeOldMarket("polymarket", "P1", pm_q))
    m_k = pre.preprocess(FakeOldMarket("kalshi", "K1", k_q))

    lookup_table = LookupTable()
    lookup_table.add(m_pm)
    lookup_table.add(m_k)

    candidates_for_k = lookup_table.lookup_by_market(m_k)
    assert m_pm in candidates_for_k, (
        "The LookupTable blocking step (used to build 'potential_matches' "
        "in generate_pairs.py) only indexes NER entities + KEYWORD_GROUPS. "
        "It has no notion of sports team aliases, so two questions about "
        "the exact same game never become a candidate pair in the first "
        "place - check_professional_matchup's alias-matching logic never "
        "gets a chance to run on them."
    )


# ----------------------------------------------------------------------
# Bug 7: entity extraction is done by two different spaCy pipelines
# that disagree with each other:
#   - CandidatePairGenerator.get_candidates uses en_core_web_lg, no
#     length filter. Used at final-verification time.
#   - MarketPreprocessor.get_candidates uses en_core_web_sm, filters
#     out anything shorter than MIN_ENTITY_LENGTH (3 chars). Used to
#     build the LookupTable index that decides what's even considered.
# Short-but-meaningful entities the final verifier's model would catch
# can be silently dropped at the indexing stage.
# ----------------------------------------------------------------------
def test_indexing_pipeline_entities_are_not_a_subset_of_verifier_entities():
    question = "Will the EU regulate AI this year?"

    verifier_cands = set(gen.get_candidates(question))
    index_cands = set(pre.get_candidates(question))

    assert index_cands, (
        "MarketPreprocessor (en_core_web_sm + MIN_ENTITY_LENGTH=3 filter) "
        "extracts nothing at all from this question, while "
        "CandidatePairGenerator (en_core_web_lg, no filter) finds "
        f"{verifier_cands or '{}'}. Since the LookupTable index is built "
        "from MarketPreprocessor's output, a pair with no shared "
        "KEYWORD_GROUPS hit and only short entities like this would never "
        "be indexed and so could never surface as a candidate."
    )


# ----------------------------------------------------------------------
# Bug 8 (lower severity): the two "leftover condition text" implementations
# disagree. CandidatePairGenerator.get_whats_left (whose output is what
# actually gets sent to the LLM in the verification prompt) does not
# filter constants.NOISE_WORDS, while MarketPreprocessor.get_whats_left
# does. The LLM prompt ends up noisier than intended.
# ----------------------------------------------------------------------
def test_get_whats_left_implementations_agree_after_noise_word_filtering():
    import util.constants as constants

    question = "Will the Fed cut interest rates before September?"

    verifier_rest = [w for w in gen.get_whats_left(question) if w not in constants.NOISE_WORDS]
    deadline = pre.get_deadline(question)
    cands = pre.get_candidates(question)
    index_rest = pre.get_whats_left(question, deadline, cands)

    assert verifier_rest == index_rest, (
        "CandidatePairGenerator.get_whats_left (used to build the LLM "
        "verification prompt's 'leftover condition text') doesn't strip "
        "constants.NOISE_WORDS the way MarketPreprocessor.get_whats_left "
        "does, so words like 'will'/'the' leak into what the LLM sees."
    )
