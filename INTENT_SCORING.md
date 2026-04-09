# Intent Scoring Model — STR Solutions AI

Scores indicate likelihood a host is open to professional STR management services.
Higher score = higher intent = prioritize for outreach.

## Scoring Signals

| Signal | Condition | Points | Notes |
|--------|-----------|--------|-------|
| **Recent Negative Reviews** | Review sentiment negative in last 90 days | +10 | Pain point — struggling with guest experience |
| **Time on Platform (New)** | Listed < 1 year | +15 | New host, likely overwhelmed, needs help |
| **Time on Platform (Mid)** | Listed 1–3 years | +10 | Established enough to see value, not yet entrenched |
| **Time on Platform (Old)** | Listed > 4 years | +3 | Likely set in their ways, lower conversion |
| **Revenue (High)** | ARR > $50K | +12 | Higher revenue = more to lose, more pain from mismanagement |
| **Revenue (Mid)** | ARR $25K–$50K | +8 | Sweet spot — earning enough to care, not enough to hire full team |
| **Revenue (Low)** | ARR < $25K | +3 | May not justify management fees |
| **New Listing** | First seen in current year | +15 | Just getting started — highest intent for help |
| **Occupancy Drop** | Occupancy rate declined >10% YoY | +10 | Struggling to fill — looking for solutions |
| **ADR Below Market** | ADR < market median for city/state | +8 | Underpricing — doesn't know the market |
| **Self-Managed (No PM)** | Property Manager field empty or matches host name | +12 | No professional help yet — our ICP |
| **Professional PM Detected** | Known brand (Vacasa, Evolve, etc.) | -50 | Already managed — disqualify |

## Score Tiers

| Tier | Score Range | Action |
|------|-------------|--------|
| 🔥 **Hot** | 40+ | Priority outreach — first in Instantly queue |
| 🟡 **Warm** | 25–39 | Standard outreach — normal campaign sequence |
| 🔵 **Cool** | 10–24 | Lower priority — batch campaigns, longer drip |
| ⚪ **Cold** | < 10 | Park — revisit quarterly or on signal change |

## Data Sources for Scoring

| Signal | Source | Available Now? |
|--------|--------|----------------|
| Time on platform | AirDNA `Reporting Month` (earliest) | ✅ Yes |
| Revenue / ARR | AirDNA `Revenue (USD)` × 12 | ✅ Yes |
| Occupancy | AirDNA `Occupancy Rate` | ✅ Yes |
| ADR vs market | AirDNA `ADR (USD)` vs city median | ✅ Yes (compute) |
| Self-managed | AirDNA `Property Manager` field | ✅ Yes |
| New listing | AirDNA `Reporting Month` = current year | ✅ Yes |
| Negative reviews | Airbnb scrape or API | ❌ Future (requires scraping) |
| Review count trend | AirDNA `Number of Reservations` trend | ✅ Partial |

## Future Signals (Phase 2+)

- **Price drops** — host lowering rates (desperation signal)
- **Response time** — slow responders on Airbnb (overwhelmed)
- **Multi-property host** — 2–5 properties = scaling pain, needs PM
- **Seasonal vacancy** — high blocked days in peak season
- **Listing quality** — poor photos, thin description (needs help)
- **Local regulation changes** — new STR laws in their city (compliance anxiety)

## How to Adjust

Edit scores in `ppd_pipeline.py` under the `score_intent()` function.
Tier thresholds can be tuned based on conversion data from Instantly campaigns.

---
*Last updated: 2026-03-17*
