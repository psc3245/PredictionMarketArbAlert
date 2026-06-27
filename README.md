# PredictionMarketArbAlert

A Python service that identifies cross-platform arbitrage opportunities between [Kalshi](https://kalshi.com) and [Polymarket](https://polymarket.com) prediction markets. It runs continuously, discovering matched market pairs and alerting when price discrepancies create a risk-free profit opportunity.

---

## What is prediction market arbitrage?

Arbitrage occurs when the same underlying event is priced differently across two platforms. By buying YES on the cheaper platform and NO on the other (or vice versa), a trader locks in a guaranteed profit regardless of how the event resolves — as long as both markets resolve to the same outcome.

**Example:**
- Kalshi: "Will GPT-6 release before Aug 1?" — YES at $0.12
- Polymarket: "GPT-6 released by July 31?" — NO at $0.49
- Buy YES on Kalshi + NO on Polymarket = $0.61 spent, $1.00 guaranteed payout = **$0.39 profit per dollar wagered**

---

## Architecture

The program runs two loops concurrently:

### Matcher (runs every 6 hours)
1. Fetches ~1600 Kalshi markets and ~1500 Polymarket markets
2. Filters candidates using keyword groups (bitcoin, gpt-6, netanyahu, haaland, etc.)
3. Sends candidate pairs to a local LLM (Qwen 2.5:14b via Ollama) for semantic verification
4. Applies post-LLM filters: fuzzy score, number mismatch, shared entity check
5. Saves confirmed pairs to `confirmed_matches.json`

### Arb Checker (runs every 60 seconds)
1. Loads confirmed pairs from `confirmed_matches.json`
2. Fetches fresh live prices for each pair from both platforms
3. Calculates profit for both legs (YES Kalshi/NO Poly and NO Kalshi/YES Poly)
4. Alerts when profit exceeds the minimum threshold (default: $0.03 per dollar wagered)

---

## Requirements

**Python:** 3.13+

**pip dependency:**
```
pip install rapidfuzz httpx
```

**Ollama** (local LLM — no API key required):
```bash
brew install ollama
ollama pull qwen2.5:14b
ollama serve
```

Qwen 2.5:14b requires approximately 8GB of RAM and runs on Apple Silicon via Metal. It is slow (~20-60 seconds per batch) but has no rate limits or cost.

No API keys are required for Kalshi or Polymarket.

---

## Files

| File | Purpose |
|------|---------|
| `main.py` | Entry point — runs matcher and arb checker concurrently |
| `fetch_markets.py` | Fetches and normalizes markets from Kalshi and Polymarket |
| `match_markets.py` | Keyword filtering, LLM verification, persistence |
| `arb_checker.py` | Fetches live prices and calculates arb opportunities |
| `confirmed_matches.json` | Persisted list of verified cross-platform market pairs |

---

## Running

```bash
# Start Ollama in a separate terminal first
ollama serve

# Run the main program
python3 main.py
```

The matcher runs immediately on startup then every 6 hours. The arb checker starts after a 5-second delay and polls every 60 seconds.

---

## Swapping the LLM

The LLM call is in `match_markets.py` around line 171:

```python
response = httpx.post(
    "http://localhost:11434/api/generate",
    json={"model": "qwen2.5:14b", "prompt": prompt, "stream": False, "options": {"num_ctx": 4096}},
    timeout=120
)
text = response.json()["response"].strip()
```

To use a paid API instead (faster, more accurate):

**Groq (free tier):**
```python
from groq import Groq
client = Groq(api_key="YOUR_KEY")
response = client.chat.completions.create(
    model="llama-3.3-70b-versatile",
    messages=[{"role": "user", "content": prompt}]
)
text = response.choices[0].message.content.strip()
```

**Anthropic Claude:**
```python
import anthropic
client = anthropic.Anthropic(api_key="YOUR_KEY")
response = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=4096,
    messages=[{"role": "user", "content": prompt}]
)
text = response.content[0].text.strip()
```

---

## Configuration

Key constants in `fetch_markets.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `one_twenty_days` | 120 days out | Maximum market close date window |
| `VOLUME_THRESHOLD` | 1 | Minimum 24h volume to include a market |

Key constants in `match_markets.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `batch_size` | 10 | Markets per LLM verification batch |
| `target` | 20 | Confirmed matches to find per matcher run |
| `min_fuzzy` | 50 | Minimum fuzzy string similarity score |

Key constants in `arb_checker.py`:

| Constant | Default | Description |
|----------|---------|-------------|
| `MIN_PROFIT` | 0.03 | Minimum profit per dollar to trigger alert |
| `POLL_INTERVAL` | 60 | Seconds between arb checks |
| `MATCH_INTERVAL` | 21600 | Seconds between matcher runs (6 hours) |

---

## Limitations

- Matching quality depends on the LLM. Qwen 2.5:14b is conservative and occasionally misses valid pairs or approves invalid ones. Post-LLM filters (fuzzy score, number mismatch, entity sharing) catch most false positives.
- Polymarket's gamma API caps at offset 2100, limiting discovery to ~1500 markets regardless of target.
- Kalshi fetching is slow (~80 seconds for 1600 markets) due to cursor-based pagination.
- The arb checker does not execute trades — it is an alert system only.
- Prices stored in `confirmed_matches.json` go stale. The arb checker always fetches live prices before calculating profit.