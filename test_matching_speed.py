import sys
import time
from dataclasses import dataclass

from generate_pairs import match, match_batch
import time

from util.match_markets import CandidatePairGenerator, LLM_Verifier
from util.market_processor import MarketPreprocessor, LookupTable
import fetch_markets as f

@dataclass
class RunResult:
    name: str
    elapsed_seconds: float
    kalshi_matches: list
    pm_matches: list
 
    @property
    def total_matches(self) -> int:
        return len(self.kalshi_matches) + len(self.pm_matches)
 
    @property
    def pair_set(self) -> set:
        """(kalshi_id, polymarket_id) tuples across both match lists."""
        pairs = set()
        for p in self.kalshi_matches:
            pairs.add((p.kalshi_id, p.polymarket_id))
        for p in self.pm_matches:
            pairs.add((p.kalshi_id, p.polymarket_id))
        return pairs
 
 
def run_and_time(fn, name, target) -> RunResult:
    print(f"Running {name}(target={target})...")
    start = time.perf_counter()
    kalshi_matches, pm_matches = fn(target=target)
    elapsed = time.perf_counter() - start
    print(f"  -> {name} finished in {elapsed:.3f}s")
    return RunResult(name=name, elapsed_seconds=elapsed,
                      kalshi_matches=kalshi_matches, pm_matches=pm_matches)
 
 
def print_summary_table(results: list):
    name_w = max(len(r.name) for r in results) + 2
    print()
    print(f"{'Function':<{name_w}}{'Runtime (s)':<15}{'Total Matches':<16}")
    print("-" * (name_w + 15 + 16))
    for r in results:
        print(f"{r.name:<{name_w}}{r.elapsed_seconds:<15.3f}{r.total_matches:<16}")
    print()
 
 
def print_diff(results: list):
    a, b = results[0], results[1]
    a_pairs, b_pairs = a.pair_set, b.pair_set
 
    both = a_pairs & b_pairs
    only_a = a_pairs - b_pairs
    only_b = b_pairs - a_pairs
 
    print(f"Matches in BOTH {a.name} and {b.name}: {len(both)}")
    for kalshi_id, pm_id in sorted(both):
        print(f"  kalshi={kalshi_id}  polymarket={pm_id}")
 
    print()
    print(f"Matches ONLY in {a.name}: {len(only_a)}")
    for kalshi_id, pm_id in sorted(only_a):
        print(f"  kalshi={kalshi_id}  polymarket={pm_id}")
 
    print()
    print(f"Matches ONLY in {b.name}: {len(only_b)}")
    for kalshi_id, pm_id in sorted(only_b):
        print(f"  kalshi={kalshi_id}  polymarket={pm_id}")
    print()
 
 
def main():
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
 
    results = [
        run_and_time(match, "match", target),
        run_and_time(match_batch, "match_batch", target),
    ]
 
    print_summary_table(results)
    print_diff(results)
 
 



def benchmark_batch_vs_individual(
    target=1000,
    batch_sizes=(3, 5, 10),
    repeats=3,
):
    pair_generator = CandidatePairGenerator()
    llm_verifier = LLM_Verifier()
    preprocessor = MarketPreprocessor()
    lookup_table = LookupTable()

    # ---------------------------------------------------------
    # Build markets
    # ---------------------------------------------------------

    print("Building markets...")

    kalshi, pm = f.find_markets(target=target)

    kalshi_processed_markets = []
    pm_processed_markets = []

    for k in kalshi:
        market = preprocessor.preprocess(k)
        lookup_table.add(market)
        kalshi_processed_markets.append(market)

    for p in pm:
        market = preprocessor.preprocess(p)
        lookup_table.add(market)
        pm_processed_markets.append(market)

    # ---------------------------------------------------------
    # Build test pairs
    # ---------------------------------------------------------

    max_batch_size = max(batch_sizes)

    print("Building candidate pairs...")

    test_pairs = []

    for k in kalshi_processed_markets:
        potential_matches = lookup_table.sorted_lookup_by_market(k)

        for potential in potential_matches:
            pm_market = potential[2]

            pair = pair_generator.create_candidate_pair(
                pm_id=pm_market.market.market_id,
                pm_q=pm_market.market.match_key,
                k_id=k.market.market_id,
                k_q=k.market.match_key,
            )

            if pair:
                test_pairs.append(pair)

            if len(test_pairs) >= max_batch_size:
                break

        if len(test_pairs) >= max_batch_size:
            break

    if len(test_pairs) < max_batch_size:
        print(
            f"Could only build {len(test_pairs)} pairs, "
            f"but need {max_batch_size}."
        )
        return

    test_pairs = test_pairs[:max_batch_size]

    # ---------------------------------------------------------
    # Print test pairs
    # ---------------------------------------------------------

    print()
    print("=" * 80)
    print("TEST PAIRS")
    print("=" * 80)

    for i, pair in enumerate(test_pairs):
        print()
        print(f"PAIR {i}")
        print("-" * 80)

        print(f"Kalshi ID:     {pair.kalshi_id}")
        print(f"Kalshi:        {pair.kalshi_question}")

        print()

        print(f"Polymarket ID: {pair.polymarket_id}")
        print(f"Polymarket:    {pair.polymarket_question}")

        print()

        print(f"Kalshi deadline:      {pair.k_deadline}")
        print(f"Polymarket deadline:  {pair.pm_deadline}")

        print(f"Kalshi entities:      {pair.k_cands}")
        print(f"Polymarket entities:  {pair.pm_cands}")

        print(f"Kalshi leftover:      {' '.join(pair.k_rest)}")
        print(f"Polymarket leftover:  {' '.join(pair.pm_rest)}")

    # ---------------------------------------------------------
    # Results storage
    # ---------------------------------------------------------

    individual_times = []
    individual_results = []

    batch_times = {
        size: []
        for size in batch_sizes
    }

    batch_results = {
        size: []
        for size in batch_sizes
    }

    # ---------------------------------------------------------
    # Warm-up
    # ---------------------------------------------------------

    print()
    print("=" * 80)
    print("WARM-UP")
    print("=" * 80)

    print("Running throwaway individual call...")

    llm_verifier.llm_check_pair(test_pairs[0])

    print("Running throwaway batch call...")

    llm_verifier.llm_check_batch(test_pairs[:max_batch_size])

    print("Warm-up complete.")

    # ---------------------------------------------------------
    # Individual benchmark
    # ---------------------------------------------------------

    print()
    print("=" * 80)
    print("INDIVIDUAL CALL BENCHMARK")
    print("=" * 80)

    for repeat in range(repeats):
        print()
        print(f"Individual repeat {repeat + 1}/{repeats}")

        results = []

        start = time.perf_counter()

        for i, pair in enumerate(test_pairs):
            result = llm_verifier.llm_check_pair(pair)
            results.append(result)

            print(
                f"  pair {i}: "
                f"{result!r}"
            )

        elapsed = time.perf_counter() - start

        individual_times.append(elapsed)
        individual_results.append(results)

        print(
            f"  total: {elapsed:.2f}s | "
            f"average: {elapsed / len(test_pairs):.2f}s/pair"
        )

    # ---------------------------------------------------------
    # Batch benchmarks
    # ---------------------------------------------------------

    for batch_size in batch_sizes:
        print()
        print("=" * 80)
        print(f"BATCH SIZE {batch_size}")
        print("=" * 80)

        for repeat in range(repeats):
            print()
            print(
                f"Batch size {batch_size}, "
                f"repeat {repeat + 1}/{repeats}"
            )

            results = {}

            start = time.perf_counter()

            for batch_start in range(
                0,
                len(test_pairs),
                batch_size,
            ):
                batch = test_pairs[
                    batch_start:batch_start + batch_size
                ]

                batch_verdicts = (
                    llm_verifier.llm_check_batch(batch)
                )

                for batch_index, verdict in batch_verdicts.items():
                    original_index = batch_start + batch_index
                    results[original_index] = verdict

            elapsed = time.perf_counter() - start

            batch_times[batch_size].append(elapsed)
            batch_results[batch_size].append(results)

            print(
                f"  total: {elapsed:.2f}s | "
                f"average: {elapsed / len(test_pairs):.2f}s/pair"
            )

    # ---------------------------------------------------------
    # Timing summary
    # ---------------------------------------------------------

    print()
    print("=" * 80)
    print("TIMING SUMMARY")
    print("=" * 80)

    individual_average = (
        sum(individual_times)
        / len(individual_times)
    )

    print()
    print(
        f"Individual average: "
        f"{individual_average:.2f}s"
    )

    print(
        f"Individual per pair: "
        f"{individual_average / len(test_pairs):.2f}s"
    )

    for batch_size in batch_sizes:
        times = batch_times[batch_size]

        average = sum(times) / len(times)

        speedup = individual_average / average

        print()
        print(f"Batch size {batch_size}:")
        print(
            f"  average total: "
            f"{average:.2f}s"
        )
        print(
            f"  average per pair: "
            f"{average / len(test_pairs):.2f}s"
        )
        print(
            f"  speedup vs individual: "
            f"{speedup:.2f}x"
        )

    # ---------------------------------------------------------
    # Verdict comparison
    # ---------------------------------------------------------

    print()
    print("=" * 80)
    print("VERDICT COMPARISON")
    print("=" * 80)

    # Use the first individual run as the baseline.
    baseline = individual_results[0]

    for batch_size in batch_sizes:
        print()
        print(f"BATCH SIZE {batch_size}")

        for repeat, results in enumerate(
            batch_results[batch_size]
        ):
            disagreements = []

            for i in range(len(test_pairs)):
                individual = baseline[i]
                batch = results.get(i)

                if individual != batch:
                    disagreements.append(
                        (
                            i,
                            individual,
                            batch,
                        )
                    )

            print(
                f"  repeat {repeat + 1}: "
                f"{len(disagreements)} "
                f"disagreements"
            )

            for (
                pair_index,
                individual,
                batch,
            ) in disagreements:
                pair = test_pairs[pair_index]

                print()
                print(
                    f"    PAIR {pair_index}"
                )
                print(
                    f"    Individual: {individual!r}"
                )
                print(
                    f"    Batch:      {batch!r}"
                )

                print(
                    f"    Kalshi:     "
                    f"{pair.kalshi_question}"
                )

                print(
                    f"    Polymarket: "
                    f"{pair.polymarket_question}"
                )

    # ---------------------------------------------------------
    # Aggregate verdict statistics
    # ---------------------------------------------------------

    print()
    print("=" * 80)
    print("AGGREGATE RESULTS")
    print("=" * 80)

    print()
    print("Individual results:")

    for i in range(len(test_pairs)):
        results_for_pair = [
            run[i]
            for run in individual_results
        ]

        print(
            f"  pair {i}: "
            f"{results_for_pair}"
        )

    for batch_size in batch_sizes:
        print()
        print(
            f"Batch size {batch_size}:"
        )

        for i in range(len(test_pairs)):
            results_for_pair = [
                run.get(i)
                for run in batch_results[batch_size]
            ]

            print(
                f"  pair {i}: "
                f"{results_for_pair}"
            )

    print()
    print("=" * 80)
    print("DONE")
    print("=" * 80)
 
if __name__ == "__main__":
    benchmark_batch_vs_individual(
        target=1000,
        batch_sizes=(3, 5, 10),
        repeats=3,
    )