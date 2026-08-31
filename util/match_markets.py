from dataclasses import dataclass, field
import re
from datetime import date, timedelta
from collections import Counter
import util.constants as constants
import httpx
import spacy
import json


@dataclass
class MarketMatch:
    # PM Things
    polymarket_id: str
    polymarket_question: str
    # Kalshi Things
    kalshi_id: str
    kalshi_question: str
    
    # High level category: 
        # sports games (NFL, NBA, etc) 
        # elections 
        # award (oscar, MVP, etc)
    category: str | None
    
@dataclass
class CandidatePair:
    # PM Things
    polymarket_id: str
    polymarket_question: str
    pm_deadline: tuple[str, str]
    pm_cands: list[str]
    pm_rest: list[str]
    # Kalshi Things
    kalshi_id: str
    kalshi_question: str
    k_deadline: tuple[str, str]
    k_cands: list[str]
    k_rest: list[str]
    
class CandidatePairGenerator:
    
    def __init__(self):
        self.NLP = spacy.load("en_core_web_lg")
        self.reject_reasons = Counter()

    def normalize_text(self, text: str) -> str:
        """Normalize text for comparison."""
        text = text.lower()
        text = re.sub(r'[^\w\s]', ' ', text)
        return text

    def get_deadline(self, question: str) -> str:
        
        text_lower = self.normalize_text(question)
        tokens = text_lower.split()
        
        raw_tokens = []

        before_or_after = None
        month = None
        day = None
        year = None
        
        if "before" in tokens:
            before_or_after = "before"
        elif "by" in tokens:
            before_or_after = "by"
        elif "after" in tokens:
            before_or_after = "after"
            
        # Find the first month mentioned in the actual sentence
        # Sort longest-first so "august" beats "aug"
        found_month = None
        first_pos = len(text_lower)

        for month_name in sorted(constants.MONTHS.keys(), key=len, reverse=True):
            match = re.search(rf"\b{month_name}\b", text_lower)

            if match and match.start() < first_pos:
                first_pos = match.start()
                found_month = month_name

        if found_month:
            month = constants.MONTHS[found_month]
            raw_tokens.append(found_month)

            pattern = (
                rf'\b{found_month}\.?,?\s*'
                rf'(\d{{1,2}})'
                rf'(?:st|nd|rd|th)?'
                rf'(?:,?\s*(\d{{4}}))?\b'
            )

            d = re.search(pattern, text_lower)

            if d:
                day = d.group(1).zfill(2)
                raw_tokens.append(d)

                if d.group(2):
                    raw_tokens.append(d)
                    
                    year = d.group(2)

        
        if day is None:

            day_regex = "|".join(
                sorted(
                    [d.replace("-", "[- ]") for d in constants.DAYS.keys()],
                    key=len,
                    reverse=True
                )
            )

            for month_name in sorted(constants.MONTHS.keys(), key=len, reverse=True):

                pattern = rf'\b({day_regex})\s+of\s+{month_name}\b'

                m = re.search(pattern, text_lower)

                if m:
                    month = constants.MONTHS[month_name]
                    raw_tokens.append(month_name)
                    day = constants.DAYS[m.group(1)]
                    raw_tokens.append(m.group(1))
                    break

        
        if day is None:

            for d in sorted(constants.DAYS.keys(), key=len, reverse=True):

                if d in tokens:
                    day = constants.DAYS[d]
                    raw_tokens.append(d)
                    break
                
        
        if "this month" in text_lower:
            month = str(date.today().month % 12 + 1).zfill(2)
            raw_tokens.append("this month")
            
        if "this year" in text_lower:
            year = str(date.today().year)
            raw_tokens.append("this year")
            

        for token in tokens:
            if token in constants.YEARS:
                year = token
                raw_tokens.append(token)
                break

                
        if year is None and month is None and day is None:
            return None

        
        if day is None and month is not None:
            day = "01"

        
        if month is not None and year is None:
            year = str(date.today().year)

        
        if month is None and day is None and year is not None:
            before_or_after = "by"
            month = "12"
            day = "31"

        
        if day is not None and len(str(day)) == 1:
            day = "0" + str(day)

        
        if day is not None and month is None and year is None:
            return None
        
        # assume its this month? not sure how to handle this yet
        if day is not None and month is None and year is not None:
            month = str(date.today().month)

                
        return (before_or_after, f"{month}-{day}-{year}", raw_tokens)

    def get_candidates(self, question):
        SENTENCE_OPENERS = ["will", "what", "who", "how", "does", ]
        
        tokens = question.split()
        if tokens[0].lower() in SENTENCE_OPENERS:
            tokens = tokens[1:]
            
        stripped = ' '.join(tokens)
        
        doc = self.NLP(stripped)
        
        ents = []
        
        for e in doc.ents:
            if e.label_ not in constants.UNWANTED_ENT_LABELS:
                ents.append(e.text)

        
        return ents

    def get_whats_left(self, question):
        deadline = self.get_deadline(question)
        candidates = self.get_candidates(question)
        
        tokens = self.normalize_text(question).split()

        filtered = []

        entity_words = set()
        for entity in candidates:
            entity_words.update(self.normalize_text(entity).split())

        deadline_words = set()
        if deadline is not None:
            _, _, raw_tokens = deadline
            for token in raw_tokens:
                if isinstance(token, re.Match):
                    deadline_words.update(self.normalize_text(token.group(0)).split())
                else:
                    deadline_words.update(self.normalize_text(str(token)).split())
                    
        # print(f"  candidates: {candidates}")
        # print(f"  entity_words: {entity_words}") 

        for token in tokens:
            if token in constants.DAYS:
                continue
            elif token in {"before", "after", "by"}:
                continue
            elif token in constants.YEARS:
                continue
            elif token in constants.MONTHS:
                continue
            elif token in entity_words:
                continue
            elif token in deadline_words:
                continue

            filtered.append(token)

        return filtered

    def deadlines_match(self, before_or_after1, d1, before_or_after2, d2):
        m1, day1, y1 = map(int, d1.split("-"))
        date1 = date(year=y1, month=m1, day=day1)

        m2, day2, y2 = map(int, d2.split("-"))
        date2 = date(year=y2, month=m2, day=day2)

        q1 = "before" if before_or_after1 in {"before", "by", None} else before_or_after1
        q2 = "before" if before_or_after2 in {"before", "by", None} else before_or_after2 

        if q1 == q2:
            return abs((date1 - date2).days) <= constants.TOLERANCE_DAYS

        if q1 == "before" and q2 == "after":
            return date2 + timedelta(days=1) == date1

        if q1 == "after" and q2 == "before":
            return date1 + timedelta(days=1) == date2

        return False
    
    def has_negation(self, q1):
        normalized = self.normalize_text(q1)
        return any(
            re.search(rf'\b{re.escape(w)}\b', normalized)
            for w in constants.NEGATION_WORDS
        )


    def keyword_pool_overlap(self, pm_q, k_q):
        pm_normal = self.normalize_text(pm_q)
        k_normal = self.normalize_text(k_q)

        for keyword_group in constants.KEYWORD_GROUPS:
            pm_hit = any(re.search(rf'\b{re.escape(kw)}\b', pm_normal) for kw in keyword_group)
            k_hit = any(re.search(rf'\b{re.escape(kw)}\b', k_normal) for kw in keyword_group)
            if pm_hit and k_hit:
                return True

        return False

    def check_professional_matchup(self, question):
        text = self.normalize_text(question)

        leagues = [
            ("NFL", constants.NFL_TEAMS),
            ("NBA", constants.NBA_TEAMS),
            ("MLB", constants.MLB_TEAMS),
            ("NHL", constants.NHL_TEAMS),
        ]

        matches = []

        for league_name, league in leagues:
            for team, aliases in league.items():
                matched = False

                for alias in aliases:
                    if not re.search(rf"\b{re.escape(alias)}\b", text):
                        continue

                    if alias in constants.AMBIGUOUS_ALIASES:
                        if not any(
                            other != alias and re.search(rf"\b{re.escape(other)}\b", text)
                            for other in aliases
                        ):
                            continue

                    matched = True
                    break

                if matched:
                    matches.append((league_name, team))

        seen = set()
        deduped = []
        for league, team in matches:
            if team not in seen:
                deduped.append((league, team))
                seen.add(team)

        if not deduped:
            return []

        if len(deduped) == 1:
            return [deduped[0][1]]

        if len(deduped) == 2:
            if deduped[0][0] != deduped[1][0]:
                return []
            return [deduped[0][1], deduped[1][1]]

        leagues_found = {league for league, _ in deduped}
        if len(leagues_found) != 1:
            return []

        return list(team for _, team in deduped)
        
    def create_candidate_pair(self, pm_id, pm_q, k_id, k_q):
        pm_result = self.get_deadline(pm_q)
        k_result = self.get_deadline(k_q)

        pm_b_or_a, pm_deadline = (pm_result[0], pm_result[1]) if pm_result else (None, None)
        k_b_or_a, k_deadline = (k_result[0], k_result[1]) if k_result else (None, None)
        
        if pm_deadline is None and k_deadline is None:
            pass

        elif pm_deadline is None or k_deadline is None:
            self.reject_reasons["one_side_missing_deadline"] += 1
            return None

        elif not self.deadlines_match(pm_b_or_a, pm_deadline, k_b_or_a, k_deadline):
            self.reject_reasons["deadline_mismatch"] += 1
            return None

        pm_neg = self.has_negation(pm_q)
        k_neg = self.has_negation(k_q)
        if pm_neg != k_neg:
            self.reject_reasons["negation_mismatch"] += 1
            return None

        pm_teams = self.check_professional_matchup(pm_q)
        k_teams = self.check_professional_matchup(k_q)

        if pm_teams or k_teams:
            if not pm_teams or not k_teams:
                self.reject_reasons["one_side_missing_team"] += 1
                return None

            if set(pm_teams) != set(k_teams):
                self.reject_reasons["team_mismatch"] += 1
                return None

        pm_cands = self.get_candidates(pm_q)
        k_cands = self.get_candidates(k_q)
        
        pm_words = {
            w
            for c in pm_cands
            for w in self.normalize_text(c).split()
            if w not in constants.NOISE_WORDS
            and len(w) >= 2
        }
        k_words = {
            w for c in k_cands 
            for w in self.normalize_text(c).split()
            if w not in constants.NOISE_WORDS
            and len(w) >= 2
        }
        has_overlap = pm_words.intersection(k_words)
        enough_overlap = len(has_overlap) >= 2
        if enough_overlap and len(has_overlap) >= 2:
            # print(f"{pm_words} and {k_words}")
            ws = []
            for w in pm_words:
                if w in k_words:
                    ws.append(w)
            # print(f"words: {ws}")
        
        keyword_overlap = self.keyword_pool_overlap(pm_q, k_q)
        
        pm_rest = self.get_whats_left(pm_q)
        k_rest = self.get_whats_left(k_q)
        
        if enough_overlap or keyword_overlap:
            self.reject_reasons["accepted"] += 1
            return CandidatePair(polymarket_id=pm_id, polymarket_question=pm_q, pm_deadline=(pm_b_or_a, pm_deadline), pm_cands=pm_cands, pm_rest=pm_rest,
                                kalshi_id=k_id, kalshi_question=k_q, k_deadline=(k_b_or_a, k_deadline), k_cands=k_cands, k_rest=k_rest)
        else:
            self.reject_reasons["no_entity_or_keyword_overlap"] += 1
            return None
        
        
class LLM_Verifier:

    def __init__(self):
        self.call_outcomes = Counter()
    
    def build_pair_verification_prompt(self, pair: CandidatePair) -> str:
        pm_deadline_str = (
            f"{pair.pm_deadline[0]} {pair.pm_deadline[1]}"
            if pair.pm_deadline and pair.pm_deadline[1] else "none stated"
        )
        k_deadline_str = (
            f"{pair.k_deadline[0]} {pair.k_deadline[1]}"
            if pair.k_deadline and pair.k_deadline[1] else "none stated"
        )

        pm_rest_str = " ".join(pair.pm_rest) if pair.pm_rest else "(nothing left after extraction)"
        k_rest_str = " ".join(pair.k_rest) if pair.k_rest else "(nothing left after extraction)"

        return f"""You are verifying whether two prediction market questions describe the exact same real-world resolution condition, for cross-platform arbitrage matching.

    CONTEXT — already verified deterministically before this pair reached you, so do NOT re-check these:
    - Deadlines have already been confirmed compatible (or both are open-ended with no stated deadline).
    - If both mention specific sports teams, those teams have already been confirmed to match.
    - Negation/antonym phrasing has already been checked — these two questions are not opposites.

    YOUR ONLY JOB: decide whether the actual resolution CONDITION is the same event, using real-world domain knowledge where needed (e.g. knowing which sports awards are objectively stat-based vs. subjectively voted).

    PAIR TO EVALUATE:

    Polymarket question: "{pair.polymarket_question}"
    extracted deadline: {pm_deadline_str}
    extracted entities: {pair.pm_cands}
    leftover condition text: "{pm_rest_str}"

    Kalshi question: "{pair.kalshi_question}"
    extracted deadline: {k_deadline_str}
    extracted entities: {pair.k_cands}
    leftover condition text: "{k_rest_str}"

    The "leftover condition text" is what remains after entities and dates were stripped out — it's noisy and may include stray filler words, but it isolates the part of each question describing WHAT must happen, which is the part you're judging. Use the full original questions as ground truth if the leftover text seems incomplete or unclear.

    Two markets are a MATCH only if they would resolve YES/NO identically under every realistic outcome. Notable domain-knowledge cases:
    - "Golden Boot" / "top goalscorer" are the same objective stat-based outcome — IS a match.
    - "Golden Ball" / "MVP" / "Player of the Tournament" are subjectively voted — NOT interchangeable with objective stat outcomes (goals scored, leading scorer), even for the same person.
    - "Golden Ball" / "MVP", "Michael Jordan Trophy" / "MVP"  - these resolve to the same outcome. Referring to winning an award by the name of the trophy representing it IS the same as winning the award title.
    - "Lead the tournament in X" and "score N+ X" are NEVER a match, regardless of whether N seems high enough to plausibly guarantee the lead. Leading is a relative comparison against whoever else is in the tournament; a specific numeric threshold is an absolute count. Do not reason about whether N is "probably enough" to lead — always treat these as different conditions.
    - "Silver Boot" means second-highest scorer specifically, not "top" — do not confuse with Golden Boot/top scorer.
    - Rate-related phrasing ("Fed cuts rates" / "FOMC lowers rates" / "rate cut") describing the same underlying decision IS a match regardless of which institution name is used.

    Return ONLY valid JSON, no preamble, no markdown fences:
    {{"match": true or false, "reason": "one sentence, state the specific rule or domain fact that determined this, not just a restatement of the two questions"}}"""
    
    def llm_check_pair(self, pair):
        prompt = self.build_pair_verification_prompt(pair)

        print(
            f"  [llm_check_pair] calling ollama for "
            f"kalshi={pair.kalshi_id} pm={pair.polymarket_id}"
        )

        try:
            response = httpx.post(
                "http://localhost:11434/api/generate",
                json={"model": "qwen2.5:14b", "prompt": prompt, "stream": False, "options": {"num_ctx": 4096}},
                timeout=120
            )
            response.raise_for_status()
        except httpx.HTTPError as e:
            print(f"  [llm_check_pair] [request failure] {type(e).__name__}: {e}")
            self.call_outcomes["request_failure"] += 1
            return None

        text = response.json()["response"].strip()
        # print(text)
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            print(f"  [parse failure] raw response: {text}")
            self.call_outcomes["parse_failure"] += 1
            return None

        match = data.get("match")
        print(f"  [llm_check_pair] verdict={match} reason={data.get('reason')!r}")
        self.call_outcomes[f"match_{match}"] += 1

        return match
    
    def build_batch_verification_prompt(self, pairs: list[CandidatePair]) -> str:
        ret = """You are identifying pairs of prediction markets that describe the exact same real-world resolution condition, for cross-platform arbitrage matching.

    CONTEXT — already verified deterministically before this pair reached you, so do NOT re-check these:
    - Deadlines have already been confirmed compatible (or both are open-ended with no stated deadline).
    - If both mention specific sports teams, those teams have already been confirmed to match.
    - Negation/antonym phrasing has already been checked — these two questions are not opposites.

    YOUR ONLY JOB: identify a pair where the actual CONDITION for RESOLUTION is the SAME REAL WORLD EVENT, ONLY IF PRESENT, using real-world domain knowledge where needed (e.g. knowing which sports awards are objectively stat-based vs. subjectively voted).

    Market Pairs to Evaluate:
    """

        for i, pair in enumerate(pairs):
            pm_deadline_str = (
                f"{pair.pm_deadline[0]} {pair.pm_deadline[1]}"
                if pair.pm_deadline and pair.pm_deadline[1]
                else "none stated"
            )

            k_deadline_str = (
                f"{pair.k_deadline[0]} {pair.k_deadline[1]}"
                if pair.k_deadline and pair.k_deadline[1]
                else "none stated"
            )

            pm_rest_str = (
                " ".join(pair.pm_rest)
                if pair.pm_rest
                else "(nothing left after extraction)"
            )

            k_rest_str = (
                " ".join(pair.k_rest)
                if pair.k_rest
                else "(nothing left after extraction)"
            )

            ret += f"""
    Pair index: {i}

    Polymarket Id: "{pair.polymarket_id}"
    Polymarket question: "{pair.polymarket_question}"
    extracted deadline: {pm_deadline_str}
    extracted entities: {pair.pm_cands}
    leftover condition text: "{pm_rest_str}"

    Kalshi Id: "{pair.kalshi_id}"
    Kalshi question: "{pair.kalshi_question}"
    extracted deadline: {k_deadline_str}
    extracted entities: {pair.k_cands}
    leftover condition text: "{k_rest_str}"

    """

        ret += """
    The "leftover condition text" is what remains after entities and dates were stripped out — it's noisy and may include stray filler words, but it isolates the part of each question describing WHAT must happen, which is the part you're judging. Use the full original questions as ground truth if the leftover text seems incomplete or unclear.

    Two markets are a MATCH only if they would resolve YES/NO identically under every realistic outcome.

    Notable domain-knowledge cases:
    - "Golden Boot" / "top goalscorer" are the same objective stat-based outcome — IS a match.
    - "Golden Ball" / "MVP" / "Player of the Tournament" are subjectively voted — NOT interchangeable with objective stat outcomes (goals scored, leading scorer), even for the same person.
    - "Golden Ball" / "MVP", "Michael Jordan Trophy" / "MVP" — these resolve to the same outcome. Referring to winning an award by the name of the trophy representing it IS the same as winning the award title.
    - "Lead the tournament in X" and "score N+ X" are NEVER a match, regardless of whether N seems high enough to plausibly guarantee the lead. Leading is a relative comparison against whoever else is in the tournament; a specific numeric threshold is an absolute count. Do not reason about whether N is "probably enough" to lead — always treat these as different conditions.
    - "Silver Boot" means second-highest scorer specifically, not "top" — do not confuse with Golden Boot/top scorer.
    - Rate-related phrasing ("Fed cuts rates" / "FOMC lowers rates" / "rate cut") describing the same underlying decision IS a match regardless of which institution name is used.

    Return ONLY valid JSON. No preamble. No markdown fences.

    Return exactly one result for every pair listed above, in the same order, using its pair index:

    {
        "results": [
            {
                "pair_index": 0,
                "match": true,
                "reason": "one sentence explaining the decision"
            }
        ]
    }

    "match" must be a JSON boolean: true or false.
    """

        return ret


    def llm_check_batch(self, pairs: list[CandidatePair]) -> dict[int, bool | None]:
        """
        Returns one entry for every input pair.

        {
            0: True,
            1: False,
            2: None,  # no usable verdict
        }

        None means the model did not provide a valid verdict for that pair.
        """

        # Give every pair a default None verdict.
        # This guarantees the caller always gets the same shape.
        verdicts = {i: None for i in range(len(pairs))}

        if not pairs:
            return verdicts

        print(f"  [llm_check_batch] calling ollama for {len(pairs)} pairs")

        prompt = self.build_batch_verification_prompt(pairs)

        try:
            response = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "qwen2.5:14b",
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_ctx": 4096
                    },
                },
                timeout=120,
            )

            response.raise_for_status()

            text = response.json()["response"].strip()

        except (httpx.HTTPError, KeyError, TypeError, ValueError) as e:
            print(
                f"  [batch request failure] "
                f"{len(pairs)} pairs affected: {e}"
            )
            self.call_outcomes["batch_request_failure"] += len(pairs)
            return verdicts

        # Find the first position at which a valid JSON object can be decoded.
        #
        # This is safer than:
        #     text.index("{")
        #     text.rindex("}")
        #
        # because it doesn't assume the first/last brace in the response
        # belongs to the JSON object.
        data = None
        decoder = json.JSONDecoder()

        for start in (i for i, char in enumerate(text) if char == "{"):
            try:
                candidate, _ = decoder.raw_decode(text[start:])
            except json.JSONDecodeError:
                continue

            if isinstance(candidate, dict):
                data = candidate
                break

        if data is None:
            print(
                f"  [batch parse failure] "
                f"{len(pairs)} pairs affected; raw response: {text}"
            )
            return verdicts

        results = data.get("results")

        if not isinstance(results, list):
            print(
                f"  [batch validation failure] "
                f"{len(pairs)} pairs expected; 'results' is not a list: {data}"
            )
            return verdicts

        seen_indices = set()

        for result in results:
            # Validate the individual result rather than letting malformed
            # entries cause KeyError/IndexError downstream.
            if not isinstance(result, dict):
                print(
                    f"  [invalid batch result] expected dict, "
                    f"got {type(result).__name__}: {result}"
                )
                continue

            pair_index = result.get("pair_index")
            match = result.get("match")
            reason = result.get("reason")

            if not isinstance(pair_index, int) or isinstance(pair_index, bool):
                print(
                    f"  [invalid batch result] invalid pair_index: "
                    f"{pair_index!r}"
                )
                continue

            if pair_index not in verdicts:
                print(
                    f"  [invalid batch result] pair_index {pair_index} "
                    f"is outside batch range 0-{len(pairs) - 1}"
                )
                continue

            if pair_index in seen_indices:
                print(
                    f"  [duplicate batch result] "
                    f"pair_index {pair_index}"
                )
                continue

            if not isinstance(match, bool):
                print(
                    f"  [invalid batch result] pair_index {pair_index} "
                    f"has non-boolean match: {match!r}"
                )
                continue

            if not isinstance(reason, str):
                print(
                    f"  [invalid batch result] pair_index {pair_index} "
                    f"has invalid reason: {reason!r}"
                )
                continue

            seen_indices.add(pair_index)
            verdicts[pair_index] = match
            self.call_outcomes[f"match_{match}"] += 1

        missing = set(verdicts) - seen_indices

        if missing:
            print(
                f"  [incomplete batch response] "
                f"received {len(seen_indices)}/{len(pairs)} valid verdicts; "
                f"missing indices: {sorted(missing)}"
            )
            self.call_outcomes["batch_missing_verdict"] += len(missing)

        return verdicts
    
    def check_pairs_in_batches(
    self,
    pairs: list[CandidatePair],
    batch_size: int = 5,
) -> dict[int, bool | None]:
        """
        Evaluate all candidate pairs in batches.

        The indices in the returned dictionary refer to the original
        `pairs` list, not the individual batches.

        None means the LLM failed to provide a usable verdict.
        """

        verdicts = {i: None for i in range(len(pairs))}

        for start in range(0, len(pairs), batch_size):
            batch = pairs[start:start + batch_size]

            batch_verdicts = self.llm_check_batch(batch)

            for batch_index, verdict in batch_verdicts.items():
                original_index = start + batch_index
                verdicts[original_index] = verdict

        return verdicts
    
    def build_unmatched_verification_prompt(self, k_q, pm_q):
        return f"""You are verifying whether two prediction market questions describe the exact same real-world resolution condition, for cross-platform arbitrage matching.

    IMPORTANT: unlike normal verification, NOTHING about these two questions has been pre-checked. You must independently verify ALL of the following before considering this a match:
    - The deadlines must resolve to the same real-world date/timeframe. "Before September" means before September 1 (i.e. by August 31), not by September 30.
    - The questions must not be negations/antonyms of each other (watch for "not", "won't", "fail to", "remain", "stay").
    - If both mention specific sports teams, they must be the exact same two teams / same matchup.
    - The actual resolution CONDITION must be the same event — use domain knowledge where relevant (e.g. "Golden Boot" = top goalscorer, an objective stat; "Golden Ball"/"MVP" are subjective awards NOT interchangeable with objective stats, even for the same person).

    Two markets are a MATCH only if they would resolve YES/NO identically under every realistic outcome. Notable domain-knowledge cases:
    - "Golden Boot" / "top goalscorer" are the same objective stat-based outcome — IS a match.
    - "Golden Ball" / "MVP" / "Player of the Tournament" are subjectively voted — NOT interchangeable with objective stat outcomes (goals scored, leading scorer), even for the same person.
    - "Golden Ball" / "MVP", "Michael Jordan Trophy" / "MVP"  - these resolve to the same outcome. Referring to winning an award by the name of the trophy representing it IS the same as winning the award title.
    - "Lead the tournament in X" and "score N+ X" are NEVER a match, regardless of whether N seems high enough to plausibly guarantee the lead. Leading is a relative comparison against whoever else is in the tournament; a specific numeric threshold is an absolute count. Do not reason about whether N is "probably enough" to lead — always treat these as different conditions.
    - "Silver Boot" means second-highest scorer specifically, not "top" — do not confuse with Golden Boot/top scorer.
    - Rate-related phrasing ("Fed cuts rates" / "FOMC lowers rates" / "rate cut") describing the same underlying decision IS a match regardless of which institution name is used.

    Kalshi question: "{k_q}"
    Polymarket question: "{pm_q}"

    Return ONLY valid JSON, no preamble, no markdown fences:
    {{"match": true or false, "reason": "one sentence, name the specific deadline/negation/team/domain-knowledge rule that determined this"}}"""
    
    def compare_unmatched_pair(self, k_q, pm_q):
        prompt = self.build_unmatched_verification_prompt(k_q, pm_q)
        response = httpx.post(
            "http://localhost:11434/api/generate",
            json={"model": "qwen2.5:14b", "prompt": prompt, "stream": False, "options": {"num_ctx": 4096}},
            timeout=120
        )
        text = response.json()["response"].strip()
        # print(text)
        try:
            start = text.index("{")
            end = text.rindex("}") + 1
            data = json.loads(text[start:end])
        except (ValueError, json.JSONDecodeError):
            print(f"  [parse failure] raw response: {text}")
            return None
        
        return data.get("match")