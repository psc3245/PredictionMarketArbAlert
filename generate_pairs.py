from util.match_markets import CandidatePairGenerator, LLM_Verifier
from util.market_processor import MarketPreprocessor, LookupTable
from market_collection.kalshi_client import KalshiClient
from market_collection.pm_client import PMClient
import spacy


async def match(target=1500):
    kalshi_client = KalshiClient()
    pm_client = PMClient()
    
    nlp = spacy.load("en_core_web_lg")
    
    preprocessor = MarketPreprocessor(nlp)
    lookup_table = LookupTable()
    
    pair_generator = CandidatePairGenerator(nlp)
    llm_verifier = LLM_Verifier()

    kalshi = await kalshi_client.list_all_markets()
    pm = await pm_client.list_all_markets()

    print(
        f"[match] fetched kalshi={len(kalshi)} "
        f"(unique ids={len({m.market_id for m in kalshi})}) | "
        f"pm={len(pm)} (unique ids={len({m.market_id for m in pm})})"
    )

    kalshi_matched_ids = set()
    pm_matched_ids = set()

    kalshi_processed_markets = []
    pm_processed_markets = []

    print("Building Kalshi Lookup Table")
    for k in kalshi:
        market = preprocessor.preprocess(k)
        lookup_table.add(market)
        kalshi_processed_markets.append(market)

    print("Building Polymarket Lookup Table")
    for p in pm:
        market = preprocessor.preprocess(p)
        lookup_table.add(market)
        pm_processed_markets.append(market)

    print("Lookup table complete")
    print(
        f"[match] lookup table sizes | "
        f"kalshi_by_entity keys={len(lookup_table.kalshi_by_entity)} "
        f"pm_by_entity keys={len(lookup_table.pm_by_entity)} "
        f"kalshi_by_keyword_group keys={len(lookup_table.kalshi_by_keyword_group)} "
        f"pm_by_keyword_group keys={len(lookup_table.pm_by_keyword_group)}"
    )
    print()
    print("-" * 50)
    print()
    print("Create Kalshi Matching Pairs")
    confirmed_kalshi_matches = []
    its = 0
    total_potential = 0
    total_candidates = 0
    for k in kalshi_processed_markets:
        if k.market.market_id in kalshi_matched_ids:
            continue
        potential_matches = lookup_table.sorted_lookup_by_market(k)
        total_potential += len(potential_matches)
        pairs = []
        for p in potential_matches:
            if p[2].market.market_id in pm_matched_ids:
                continue
            pair = pair_generator.create_candidate_pair(pm_id=p[2].market.market_id, pm_q=p[2].market.match_key,
                                                        k_id=k.market.market_id, k_q=k.market.match_key)
            if pair:
                pairs.append(pair)
        total_candidates += len(pairs)
        for p in pairs:
            conf = llm_verifier.llm_check_pair(p)
            if conf:
                confirmed_kalshi_matches.append(p)
                kalshi_matched_ids.add(p.kalshi_id)
                pm_matched_ids.add(p.polymarket_id)
        if its % 200 == 0 or len(potential_matches) > 0:
            print(
                f"[match] kalshi it={its} id={k.market.market_id} "
                f"potential_matches={len(potential_matches)} "
                f"candidate_pairs={len(pairs)}"
            )
        its += 1
        if its % 500 == 0:
            print(
                f"[match] running totals | its={its} "
                f"total_potential={total_potential} "
                f"total_candidates={total_candidates} "
                f"confirmed={len(confirmed_kalshi_matches)}"
            )
            print(f"[match] reject_reasons so far: {dict(pair_generator.reject_reasons)}")
            print(f"[match] llm outcomes so far: {dict(llm_verifier.call_outcomes)}")

    print(
        f"[match] KALSHI PASS DONE | its={its} "
        f"total_potential={total_potential} total_candidates={total_candidates} "
        f"confirmed={len(confirmed_kalshi_matches)}"
    )
    print(f"[match] reject_reasons: {dict(pair_generator.reject_reasons)}")
    print(f"[match] llm outcomes: {dict(llm_verifier.call_outcomes)}")

    print() 
    print("-" * 50) 
    print() 
    print("Create Polymarket Matching Pairs")
    confirmed_pm_matches = []
    its = 0
    total_potential = 0
    total_candidates = 0
    for p in pm_processed_markets:
        if p.market.market_id in pm_matched_ids:
            continue
        potential_matches = lookup_table.sorted_lookup_by_market(p)
        total_potential += len(potential_matches)
        pairs = []
        for potential in potential_matches:
            if potential[2].market.market_id in kalshi_matched_ids:
                continue
            pair = pair_generator.create_candidate_pair( k_id=p.market.market_id, k_q=p.market.match_key,
                                                        pm_id=potential[2].market.market_id, pm_q=potential[2].market.match_key)
            if pair:
                pairs.append(pair)
        total_candidates += len(pairs)
        for pair in pairs:
            conf = llm_verifier.llm_check_pair(pair)
            if conf:
                confirmed_pm_matches.append(pair)
                kalshi_matched_ids.add(pair.kalshi_id)
                pm_matched_ids.add(pair.polymarket_id)
        if its % 200 == 0 or len(potential_matches) > 0:
            print(
                f"[match] pm it={its} id={p.market.market_id} "
                f"potential_matches={len(potential_matches)} "
                f"candidate_pairs={len(pairs)}"
            )
        its += 1
        if its % 500 == 0:
            print(
                f"[match] running totals | its={its} "
                f"total_potential={total_potential} "
                f"total_candidates={total_candidates} "
                f"confirmed={len(confirmed_pm_matches)}"
            )
            print(f"[match] reject_reasons so far: {dict(pair_generator.reject_reasons)}")
            print(f"[match] llm outcomes so far: {dict(llm_verifier.call_outcomes)}")

    print(
        f"[match] PM PASS DONE | its={its} "
        f"total_potential={total_potential} total_candidates={total_candidates} "
        f"confirmed={len(confirmed_pm_matches)}"
    )
    print(f"[match] reject_reasons: {dict(pair_generator.reject_reasons)}")
    print(f"[match] llm outcomes: {dict(llm_verifier.call_outcomes)}")

    return confirmed_kalshi_matches, confirmed_pm_matches

async def match_batch(target=1000):
    kalshi_client = KalshiClient()
    pm_client = PMClient()
    
    preprocessor = MarketPreprocessor()
    lookup_table = LookupTable()
    
    pair_generator = CandidatePairGenerator()
    llm_verifier = LLM_Verifier()

    kalshi = await kalshi_client.list_all_markets()
    pm = await pm_client.list_all_markets()

    print(
        f"[match_batch] fetched kalshi={len(kalshi)} "
        f"(unique ids={len({m.market_id for m in kalshi})}) | "
        f"pm={len(pm)} (unique ids={len({m.market_id for m in pm})})"
    )

    kalshi_matched_ids = set()
    pm_matched_ids = set()

    kalshi_processed_markets = []
    pm_processed_markets = []

    print("Building Kalshi Lookup Table")
    for k in kalshi:
        market = preprocessor.preprocess(k)
        lookup_table.add(market)
        kalshi_processed_markets.append(market)

    print("Building Polymarket Lookup Table")
    for p in pm:
        market = preprocessor.preprocess(p)
        lookup_table.add(market)
        pm_processed_markets.append(market)

    print("Lookup table complete")
    print(
        f"[match_batch] lookup table sizes | "
        f"kalshi_by_entity keys={len(lookup_table.kalshi_by_entity)} "
        f"pm_by_entity keys={len(lookup_table.pm_by_entity)} "
        f"kalshi_by_keyword_group keys={len(lookup_table.kalshi_by_keyword_group)} "
        f"pm_by_keyword_group keys={len(lookup_table.pm_by_keyword_group)}"
    )
    print()
    print("-" * 50)
    print()

    BATCH_SIZE = 5

    print("Create Kalshi Matching Pairs")

    confirmed_kalshi_matches = []
    its = 0
    total_potential = 0

    for k in kalshi_processed_markets:
        if k.market.market_id in kalshi_matched_ids:
            continue

        # Get ALL potential matches for this market from the lookup table.
        potential_matches = lookup_table.sorted_lookup_by_market(k)
        total_potential += len(potential_matches)

        pairs = []

        for potential in potential_matches:
            pm = potential[2]

            if pm.market.market_id in pm_matched_ids:
                continue

            pair = pair_generator.create_candidate_pair(
                pm_id=pm.market.market_id,
                pm_q=pm.market.match_key,
                k_id=k.market.market_id,
                k_q=k.market.match_key,
            )

            if pair:
                pairs.append(pair)

        print(
            f"iteration: {its} | "
            f"Kalshi {k.market.market_id} | "
            f"potential_matches: {len(potential_matches)} | "
            f"candidate pairs: {len(pairs)}"
        )

        # ALL candidate pairs for this lookup-table result are evaluated.
        verdicts = llm_verifier.check_pairs_in_batches(
            pairs,
            batch_size=BATCH_SIZE,
        )

        unresolved = 0

        for pair_index, match in verdicts.items():
            pair = pairs[pair_index]

            if match is None:
                unresolved += 1
                print(
                    f"  [unresolved] "
                    f"{pair.kalshi_id} / {pair.polymarket_id}"
                )
                continue

            if match is False:
                continue

            # match is True
            if pair.kalshi_id in kalshi_matched_ids:
                continue

            if pair.polymarket_id in pm_matched_ids:
                continue

            confirmed_kalshi_matches.append(pair)
            kalshi_matched_ids.add(pair.kalshi_id)
            pm_matched_ids.add(pair.polymarket_id)

        print(
            f"total confirmed matched: "
            f"{len(confirmed_kalshi_matches)}"
        )

        if unresolved:
            print(f"  unresolved pairs: {unresolved}")

        if (
            len(confirmed_kalshi_matches) % 10 == 0
            and confirmed_kalshi_matches
        ):
            print(
                confirmed_kalshi_matches[
                    max(0, len(confirmed_kalshi_matches) - 10):
                ]
            )

        its += 1

        if its % 500 == 0:
            print(
                f"[match_batch] running totals | its={its} "
                f"total_potential={total_potential} "
                f"confirmed={len(confirmed_kalshi_matches)}"
            )
            print(f"[match_batch] reject_reasons so far: {dict(pair_generator.reject_reasons)}")
            print(f"[match_batch] llm outcomes so far: {dict(llm_verifier.call_outcomes)}")

    print(
        f"[match_batch] KALSHI PASS DONE | its={its} "
        f"total_potential={total_potential} confirmed={len(confirmed_kalshi_matches)}"
    )
    print(f"[match_batch] reject_reasons: {dict(pair_generator.reject_reasons)}")
    print(f"[match_batch] llm outcomes: {dict(llm_verifier.call_outcomes)}")

    print()
    print("-" * 50)
    print()

    print("Create Polymarket Matching Pairs")

    confirmed_pm_matches = []
    its = 0
    total_potential = 0

    for p in pm_processed_markets:
        if p.market.market_id in pm_matched_ids:
            continue

        # Get ALL potential matches for this market from the lookup table.
        potential_matches = lookup_table.sorted_lookup_by_market(p)
        total_potential += len(potential_matches)

        pairs = []

        for potential in potential_matches:
            k = potential[2]

            if k.market.market_id in kalshi_matched_ids:
                continue

            pair = pair_generator.create_candidate_pair(
                k_id=k.market.market_id,
                k_q=k.market.match_key,
                pm_id=p.market.market_id,
                pm_q=p.market.match_key,
            )

            if pair:
                pairs.append(pair)

        print(
            f"iteration: {its} | "
            f"Polymarket {p.market.market_id} | "
            f"potential_matches: {len(potential_matches)} | "
            f"candidate pairs: {len(pairs)}"
        )

        # ALL candidate pairs for this lookup-table result are evaluated.
        verdicts = llm_verifier.check_pairs_in_batches(
            pairs,
            batch_size=BATCH_SIZE,
        )

        unresolved = 0

        for pair_index, match in verdicts.items():
            pair = pairs[pair_index]

            if match is None:
                unresolved += 1
                print(
                    f"  [unresolved] "
                    f"{pair.kalshi_id} / {pair.polymarket_id}"
                )
                continue

            if match is False:
                continue

            # match is True
            if pair.kalshi_id in kalshi_matched_ids:
                continue

            if pair.polymarket_id in pm_matched_ids:
                continue

            confirmed_pm_matches.append(pair)
            kalshi_matched_ids.add(pair.kalshi_id)
            pm_matched_ids.add(pair.polymarket_id)

        print(
            f"total confirmed matched: "
            f"{len(confirmed_pm_matches)}"
        )

        if unresolved:
            print(f"  unresolved pairs: {unresolved}")

        if (
            len(confirmed_pm_matches) % 10 == 0
            and confirmed_pm_matches
        ):
            print(
                confirmed_pm_matches[
                    max(0, len(confirmed_pm_matches) - 10):
                ]
            )

        its += 1

        if its % 500 == 0:
            print(
                f"[match_batch] running totals | its={its} "
                f"total_potential={total_potential} "
                f"confirmed={len(confirmed_pm_matches)}"
            )
            print(f"[match_batch] reject_reasons so far: {dict(pair_generator.reject_reasons)}")
            print(f"[match_batch] llm outcomes so far: {dict(llm_verifier.call_outcomes)}")

    print(
        f"[match_batch] PM PASS DONE | its={its} "
        f"total_potential={total_potential} confirmed={len(confirmed_pm_matches)}"
    )
    print(f"[match_batch] reject_reasons: {dict(pair_generator.reject_reasons)}")
    print(f"[match_batch] llm outcomes: {dict(llm_verifier.call_outcomes)}")

    return confirmed_kalshi_matches, confirmed_pm_matches
