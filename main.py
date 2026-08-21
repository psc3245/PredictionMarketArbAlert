from generate_pairs import match, match_batch
import asyncio
import time


async def main():
    # ---------------------------------------------------------
    # Run original match()
    # ---------------------------------------------------------
    print("=" * 80)
    print("RUNNING match()")
    print("=" * 80)

    start = time.perf_counter()

    kalshi_matches, pm_matches = await match()

    match_time = time.perf_counter() - start

    print("\n" + "-" * 80)
    print("match() RESULTS")
    print("-" * 80)

    print(f"Kalshi matches : {len(kalshi_matches):,}")
    print(f"PM matches     : {len(pm_matches):,}")
    print(f"Total matches  : {len(kalshi_matches) + len(pm_matches):,}")
    print(f"Time           : {match_time:.2f}s")

    # ---------------------------------------------------------
    # Run match_batch()
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("RUNNING match_batch()")
    print("=" * 80)

    start = time.perf_counter()

    kalshi_batch_matches, pm_batch_matches = await match_batch()

    batch_time = time.perf_counter() - start

    print("\n" + "-" * 80)
    print("match_batch() RESULTS")
    print("-" * 80)

    print(f"Kalshi matches : {len(kalshi_batch_matches):,}")
    print(f"PM matches     : {len(pm_batch_matches):,}")
    print(
        f"Total matches  : "
        f"{len(kalshi_batch_matches) + len(pm_batch_matches):,}"
    )
    print(f"Time           : {batch_time:.2f}s")

    # ---------------------------------------------------------
    # Compare
    # ---------------------------------------------------------
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    normal_total = len(kalshi_matches) + len(pm_matches)
    batch_total = len(kalshi_batch_matches) + len(pm_batch_matches)

    print(f"{'':25} {'match()':>15} {'match_batch()':>15}")
    print("-" * 60)

    print(
        f"{'Kalshi matches':25} "
        f"{len(kalshi_matches):>15,} "
        f"{len(kalshi_batch_matches):>15,}"
    )

    print(
        f"{'PM matches':25} "
        f"{len(pm_matches):>15,} "
        f"{len(pm_batch_matches):>15,}"
    )

    print(
        f"{'Total matches':25} "
        f"{normal_total:>15,} "
        f"{batch_total:>15,}"
    )

    print(
        f"{'Runtime (seconds)':25} "
        f"{match_time:>15.2f} "
        f"{batch_time:>15.2f}"
    )

    if batch_time > 0:
        print(
            f"{'Speedup':25} "
            f"{'':>15} "
            f"{match_time / batch_time:>14.2f}x"
        )

    # ---------------------------------------------------------
    # Compare actual pair IDs
    # ---------------------------------------------------------
    normal_pairs = {
        (p.kalshi_id, p.polymarket_id)
        for p in kalshi_matches + pm_matches
    }

    batch_pairs = {
        (p.kalshi_id, p.polymarket_id)
        for p in kalshi_batch_matches + pm_batch_matches
    }

    print("\n" + "=" * 80)
    print("PAIR DIFFERENCES")
    print("=" * 80)

    only_normal = normal_pairs - batch_pairs
    only_batch = batch_pairs - normal_pairs
    both = normal_pairs & batch_pairs

    print(f"Pairs in both      : {len(both):,}")
    print(f"Only match()       : {len(only_normal):,}")
    print(f"Only match_batch() : {len(only_batch):,}")

    if only_normal:
        print("\nExamples only found by match():")

        for kalshi_id, pm_id in list(only_normal)[:10]:
            print(f"  {kalshi_id} <-> {pm_id}")

    if only_batch:
        print("\nExamples only found by match_batch():")

        for kalshi_id, pm_id in list(only_batch)[:10]:
            print(f"  {kalshi_id} <-> {pm_id}")


if __name__ == "__main__":
    asyncio.run(main())