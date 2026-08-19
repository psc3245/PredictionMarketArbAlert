from market_collection.kalshi_client import KalshiClient
import asyncio
import time


async def main():
    kalshi_client = KalshiClient()

    results = []
    sleep = 0.3125

    for _ in range(7):
        print("-" * 60)
        print(f"Testing sleep time: {sleep:.4f}s")

        start = time.perf_counter()
        markets, count, elapsed = await kalshi_client.list_all_markets(sleep)

        markets_found = len(markets)
        markets_per_sec = markets_found / elapsed if elapsed > 0 else 0

        results.append({
            "sleep": sleep,
            "markets": markets_found,
            "429s": count,
            "time": elapsed,
            "markets/sec": markets_per_sec,
        })

        print(f"Markets found : {markets_found:,}")
        print(f"429s          : {count:,}")
        print(f"Time elapsed  : {elapsed:.2f}s")
        print(f"Markets/sec   : {markets_per_sec:.2f}")

        # sleep /= 2

    # Sort by sleep time for display
    results.sort(key=lambda x: x["sleep"], reverse=True)

    print("\n" + "=" * 80)
    print("RESULTS")
    print("=" * 80)

    print(
        f"{'Sleep':>10} "
        f"{'Markets':>10} "
        f"{'429s':>8} "
        f"{'Time (s)':>12} "
        f"{'Markets/s':>12}"
    )
    print("-" * 80)

    for result in results:
        print(
            f"{result['sleep']:>10.4f} "
            f"{result['markets']:>10,} "
            f"{result['429s']:>8,} "
            f"{result['time']:>12.2f} "
            f"{result['markets/sec']:>12.2f}"
        )

    # Best individual runs
    most_markets = max(results, key=lambda x: x["markets"])
    fewest_429s = min(results, key=lambda x: x["429s"])
    fastest = min(results, key=lambda x: x["time"])
    best_throughput = max(results, key=lambda x: x["markets/sec"])

    print("\n" + "=" * 80)
    print("BEST RESULTS")
    print("=" * 80)

    print(
        f"Most markets     : {most_markets['sleep']:.4f}s "
        f"({most_markets['markets']:,} markets)"
    )

    print(
        f"Fewest 429s      : {fewest_429s['sleep']:.4f}s "
        f"({fewest_429s['429s']:,} 429s)"
    )

    print(
        f"Fastest           : {fastest['sleep']:.4f}s "
        f"({fastest['time']:.2f}s)"
    )

    print(
        f"Best throughput   : {best_throughput['sleep']:.4f}s "
        f"({best_throughput['markets/sec']:.2f} markets/s)"
    )


if __name__ == "__main__":
    asyncio.run(main())