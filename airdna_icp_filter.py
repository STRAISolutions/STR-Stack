#!/usr/bin/env python3
"""
AirDNA ICP Pre-Filter & Lead Scoring Engine
=============================================
Reads raw AirDNA CSV/CSV.GZ exports (4M+ records) and applies a
research-backed scoring model to identify the highest-propensity
sole-proprietor hosts likely to convert to professional management.

Target: Reduce 4M → 200-400K qualified leads before enrichment.
Goal: 3,000 signed homeowner clients.

Scoring Model Based On:
- STR industry conversion data (55K-85K sole props convert annually)
- Trigger events: burnout, declining reviews, regulatory pressure
- 2025-2026 market conditions: oversupply, ADR compression, algorithm changes
- Demographics: 2-5 properties, 18-36 months hosting, absentee owners

Author: STR Solutions USA / Generated for STR Stack
"""

import argparse
import csv
import gzip
import io
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

OUTPUT_DIR = Path("./filtered_output")
LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"

# Markets with new/tightening STR regulations (2024-2026)
# These hosts face compliance burden → higher conversion propensity
REGULATED_MARKETS = {
    # Cities/Counties with strict new STR ordinances
    "new york", "nyc", "manhattan", "brooklyn",
    "los angeles", "santa monica", "west hollywood",
    "nashville", "davidson county",
    "austin", "dallas", "san antonio", "houston",
    "denver", "colorado springs",
    "miami", "miami beach", "fort lauderdale", "broward",
    "new orleans", "orleans parish",
    "honolulu", "maui", "hawaii",
    "san francisco", "san diego",
    "chicago", "portland", "seattle",
    "savannah", "charleston", "asheville",
    "scottsdale", "sedona", "flagstaff",
    "park city", "big bear", "lake tahoe",
    "jersey city", "atlantic city",
    "key west", "destin", "panama city beach",
    "gatlinburg", "pigeon forge", "sevierville",  # Smoky Mountains
    "orlando", "kissimmee", "davenport",  # Central FL oversupply
    "gulf shores", "orange beach",
    "myrtle beach", "hilton head",
    "cape cod", "nantucket", "martha's vineyard",
    "outer banks", "virginia beach",
    "lake havasu", "palm springs", "joshua tree",
    "breckenridge", "steamboat springs", "vail", "aspen",
}

# Oversaturated markets where ADR/occupancy are declining (2025-2026)
# Hosts here feel revenue pressure → higher conversion propensity
OVERSATURATED_MARKETS = {
    "gatlinburg", "pigeon forge", "sevierville",  # Smoky Mountains
    "gulf shores", "orange beach",
    "orlando", "kissimmee", "davenport",
    "panama city beach", "destin",
    "myrtle beach", "north myrtle beach",
    "scottsdale", "phoenix",
    "branson",
    "big bear",
    "poconos", "pocono",
    "lake of the ozarks",
    "galveston",
    "fort myers", "cape coral",
    "puerto rico",
}

# States with complex STR tax regimes
HIGH_TAX_COMPLEXITY_STATES = {
    "CA", "NY", "HI", "FL", "CO", "TN", "TX", "AZ", "OR", "WA",
    "NV", "SC", "NC", "GA", "LA", "MA", "NJ", "CT", "VT", "ME",
}

# Property types most likely to be sole-prop managed
PREFERRED_PROPERTY_TYPES = {
    "house", "entire home", "cabin", "condo", "condominium",
    "apartment", "townhouse", "villa", "cottage", "bungalow",
    "chalet", "loft", "guest house", "guesthouse", "ranch",
    "farmhouse", "tiny house", "yurt", "treehouse", "a-frame",
}

# Corporate/institutional indicators (lower priority)
CORPORATE_INDICATORS = re.compile(
    r"\b(llc|l\.l\.c|inc|corp|ltd|lp|llp|trust|holdings|"
    r"ventures|enterprises|capital|equity|realty|"
    r"group|partners|vacasa|evolve|sonder|turnkey|"
    r"casago|avantstar|hipcamp|company|co\.|"
    r"property management|pm company)\b",
    re.IGNORECASE,
)


def safe_float(val: Any, default: float = 0.0) -> float:
    if val is None or val == "":
        return default
    try:
        # Handle percentage strings like "65.3%"
        s = str(val).strip().rstrip("%")
        return float(s)
    except (ValueError, TypeError):
        return default


def safe_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip()


# ---------------------------------------------------------------------------
# Scoring Model
# ---------------------------------------------------------------------------

class ICPScorer:
    """
    Research-backed lead scoring model for STR management client acquisition.

    Score ranges:
      90-100: Tier 1 — Highest propensity, immediate outreach
      70-89:  Tier 2 — High propensity, priority outreach
      50-69:  Tier 3 — Moderate propensity, nurture sequence
      30-49:  Tier 4 — Low propensity, long-term drip
      0-29:   DISCARD — Not ICP fit
    """

    def score(self, row: Dict[str, str]) -> Tuple[int, List[str], Dict[str, Any]]:
        """
        Score a single AirDNA row.
        Returns (score, reasons[], extracted_fields{}).
        """
        score = 0
        reasons = []

        # --- Extract fields ---
        revenue = safe_float(
            row.get("Revenue LTM (USD)") or row.get("Revenue (USD)")
            or row.get("Revenue Potential LTM (USD)") or row.get("revenue") or 0
        )
        occupancy = safe_float(
            row.get("Occupancy Rate LTM") or row.get("Occupancy Rate")
            or row.get("occupancy_rate") or 0
        )
        adr = safe_float(
            row.get("ADR (USD)") or row.get("ADR (Native)")
            or row.get("Average Daily Rate") or 0
        )
        rating = safe_float(
            row.get("Overall Rating") or row.get("Rating")
            or row.get("rating") or row.get("Average Rating") or 0
        )
        num_reviews = safe_float(
            row.get("Number of Reviews") or row.get("Reviews")
            or row.get("review_count") or row.get("Total Reviews") or 0
        )
        num_properties = safe_float(
            row.get("Number of Properties") or row.get("Number of Units")
            or row.get("# Properties") or row.get("Num Properties")
            or row.get("Properties") or row.get("Number of Listings")
            or row.get("Listing Count") or row.get("Total Listings") or 0
        )
        bedrooms = safe_float(
            row.get("Bedrooms") or row.get("bedrooms") or 0
        )
        property_type = safe_str(
            row.get("Property Type") or row.get("Listing Type") or ""
        ).lower()
        listing_title = safe_str(
            row.get("Listing Title") or row.get("Property Name") or ""
        )
        market = safe_str(
            row.get("AirDNA Market") or row.get("Metropolitan Statistical Area")
            or row.get("Market") or ""
        ).lower()
        city = safe_str(row.get("City") or row.get("city") or "").lower()
        state = safe_str(row.get("State") or row.get("state") or "").upper()
        lat = safe_float(row.get("Latitude") or row.get("latitude") or 0)
        lng = safe_float(row.get("Longitude") or row.get("longitude") or 0)
        listing_url = safe_str(
            row.get("Listing URL") or row.get("listing_url") or ""
        )

        # Days since first review (proxy for listing age)
        first_review = safe_str(
            row.get("First Review Date") or row.get("Created Date")
            or row.get("first_review") or ""
        )

        # Revenue potential vs actual (if available)
        rev_potential = safe_float(
            row.get("Revenue Potential LTM (USD)") or row.get("Revenue Potential (USD)") or 0
        )

        fields = {
            "revenue": revenue, "occupancy": occupancy, "adr": adr,
            "rating": rating, "num_reviews": num_reviews,
            "num_properties": num_properties, "bedrooms": bedrooms,
            "property_type": property_type, "market": market,
            "city": city, "state": state, "listing_title": listing_title,
            "lat": lat, "lng": lng, "listing_url": listing_url,
            "rev_potential": rev_potential,
        }

        # ===================================================================
        # HARD FILTERS (instant disqualify)
        # ===================================================================

        # Must have lat/lng
        if not lat and not lng:
            return (0, ["NO_COORDS"], fields)

        # Must be in the US (rough lat/lng bounds)
        if lat and lng:
            if not (24.0 <= lat <= 49.5 and -125.0 <= lng <= -66.0):
                # Allow Hawaii and Alaska
                if not (18.0 <= lat <= 23.0 and -161.0 <= lng <= -154.0):  # Hawaii
                    if not (51.0 <= lat <= 72.0 and -180.0 <= lng <= -130.0):  # Alaska
                        if not (17.5 <= lat <= 18.6 and -67.5 <= lng <= -65.0):  # Puerto Rico
                            return (0, ["NOT_US"], fields)

        # ===================================================================
        # TIER 1 SIGNALS (20+ points each) — Strongest conversion indicators
        # ===================================================================

        # --- Revenue underperformance (biggest pain point) ---
        if revenue > 0 and revenue < 25000:
            # Below median — likely struggling
            score += 15
            reasons.append("LOW_REVENUE_BELOW_25K")

        if rev_potential > 0 and revenue > 0:
            performance_ratio = revenue / rev_potential
            if performance_ratio < 0.60:
                score += 25
                reasons.append(f"SEVERE_UNDERPERFORMANCE_{performance_ratio:.0%}")
            elif performance_ratio < 0.75:
                score += 18
                reasons.append(f"UNDERPERFORMING_{performance_ratio:.0%}")
            elif performance_ratio < 0.85:
                score += 10
                reasons.append(f"SLIGHT_UNDERPERFORMANCE_{performance_ratio:.0%}")

        # --- Low occupancy (calendar gaps = revenue leak) ---
        if occupancy > 0:
            if occupancy < 35:
                score += 25
                reasons.append(f"VERY_LOW_OCCUPANCY_{occupancy:.0f}%")
            elif occupancy < 50:
                score += 20
                reasons.append(f"LOW_OCCUPANCY_{occupancy:.0f}%")
            elif occupancy < 60:
                score += 12
                reasons.append(f"BELOW_AVG_OCCUPANCY_{occupancy:.0f}%")

        # --- Portfolio size (2-5 = sweet spot for conversion) ---
        if num_properties > 0:
            if 2 <= num_properties <= 5:
                score += 20
                reasons.append(f"SWEET_SPOT_{num_properties:.0f}_PROPERTIES")
            elif num_properties == 1:
                score += 5
                reasons.append("SINGLE_PROPERTY")
            elif num_properties > 5:
                # Large operator — less likely to convert but still viable
                score -= 10
                reasons.append(f"LARGE_OPERATOR_{num_properties:.0f}")

        # --- Declining reviews (operational fatigue signal) ---
        if rating > 0:
            if rating < 4.2:
                score += 22
                reasons.append(f"POOR_RATING_{rating:.1f}")
            elif rating < 4.5:
                score += 18
                reasons.append(f"BELOW_THRESHOLD_RATING_{rating:.1f}")
            elif rating < 4.7:
                score += 8
                reasons.append(f"AVERAGE_RATING_{rating:.1f}")

        # ===================================================================
        # TIER 2 SIGNALS (10-15 points each)
        # ===================================================================

        # --- Regulated market (compliance burden) ---
        market_lower = market.lower()
        city_lower = city.lower()
        in_regulated = any(
            rm in market_lower or rm in city_lower
            for rm in REGULATED_MARKETS
        )
        if in_regulated:
            score += 15
            reasons.append("REGULATED_MARKET")

        # --- Oversaturated market (revenue pressure) ---
        in_oversaturated = any(
            om in market_lower or om in city_lower
            for om in OVERSATURATED_MARKETS
        )
        if in_oversaturated:
            score += 12
            reasons.append("OVERSATURATED_MARKET")

        # --- High tax complexity state ---
        if state in HIGH_TAX_COMPLEXITY_STATES:
            score += 8
            reasons.append(f"HIGH_TAX_STATE_{state}")

        # --- Property type fit ---
        type_match = any(pt in property_type for pt in PREFERRED_PROPERTY_TYPES)
        if type_match:
            score += 10
            reasons.append("PREFERRED_PROPERTY_TYPE")
        elif "hotel" in property_type or "hostel" in property_type:
            score -= 15
            reasons.append("HOTEL_TYPE_DISQUALIFY")

        # --- Review count (proxy for listing maturity) ---
        if num_reviews > 0:
            if 10 <= num_reviews <= 60:
                # 18-36 month sweet spot (roughly 1-2 reviews/month)
                score += 12
                reasons.append("OPTIMAL_MATURITY_WINDOW")
            elif num_reviews < 10:
                score += 3
                reasons.append("NEW_LISTING")
            elif num_reviews > 100:
                score += 5
                reasons.append("ESTABLISHED_LISTING")

        # --- Revenue tier (must be worth managing) ---
        if revenue >= 40000:
            score += 15
            reasons.append("HIGH_REVENUE_PROPERTY")
        elif revenue >= 25000:
            score += 10
            reasons.append("MODERATE_REVENUE")
        elif revenue > 0 and revenue < 15000:
            score -= 5
            reasons.append("LOW_VALUE_PROPERTY")

        # --- Bedroom count (2-5 BR most manageable) ---
        if 2 <= bedrooms <= 5:
            score += 8
            reasons.append(f"IDEAL_SIZE_{bedrooms:.0f}BR")
        elif bedrooms == 1:
            score += 2
            reasons.append("STUDIO_1BR")
        elif bedrooms > 5:
            score += 5
            reasons.append("LARGE_PROPERTY")

        # ===================================================================
        # TIER 3 SIGNALS (5-10 points each)
        # ===================================================================

        # --- ADR analysis (flat/low ADR = no dynamic pricing) ---
        if adr > 0 and revenue > 0 and occupancy > 0:
            # If ADR is significantly below market potential
            expected_rev = adr * 365 * (occupancy / 100)
            if revenue < expected_rev * 0.7:
                score += 10
                reasons.append("REVENUE_BELOW_ADR_POTENTIAL")

        # --- Corporate name detection (lower priority) ---
        if CORPORATE_INDICATORS.search(listing_title):
            score -= 10
            reasons.append("CORPORATE_NAME_DETECTED")

        # ===================================================================
        # COMPOSITE SCORING BONUSES
        # ===================================================================

        # Triple threat: low occupancy + low rating + regulated market
        if occupancy > 0 and occupancy < 55 and rating > 0 and rating < 4.5 and in_regulated:
            score += 15
            reasons.append("TRIPLE_THREAT_BONUS")

        # Revenue gap + sweet spot portfolio
        if (rev_potential > 0 and revenue > 0 and revenue / rev_potential < 0.75
                and 2 <= num_properties <= 5):
            score += 15
            reasons.append("UNDERPERFORMING_MULTI_PROPERTY_BONUS")

        # High value + struggling (best ROI for management)
        if revenue >= 30000 and occupancy > 0 and occupancy < 55:
            score += 12
            reasons.append("HIGH_VALUE_STRUGGLING")

        # Clamp score
        score = max(0, min(100, score))

        return (score, reasons, fields)


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

class ICPFilterPipeline:
    """Read AirDNA CSVs, score, filter, and output qualified leads."""

    def __init__(self, input_paths: List[str], output_dir: Path,
                 min_score: int = 30, top_n: int = 0):
        self.input_paths = input_paths
        self.output_dir = output_dir
        self.min_score = min_score
        self.top_n = top_n
        self.scorer = ICPScorer()
        self.log = logging.getLogger("ICP_Filter")

        output_dir.mkdir(parents=True, exist_ok=True)

    def iter_csv(self, path: str):
        """Stream CSV or CSV.GZ rows one at a time (memory efficient)."""
        path_lower = path.lower()
        is_gzip = path_lower.endswith(".gz") or path_lower.endswith(".gz.csv")

        if is_gzip:
            fh = io.TextIOWrapper(gzip.open(path, "rb"), encoding="utf-8-sig")
        else:
            fh = open(path, "r", encoding="utf-8-sig")

        try:
            reader = csv.DictReader(fh)
            for row in reader:
                yield row
        finally:
            fh.close()

    def run(self) -> Dict[str, Any]:
        """Execute the full filter pipeline (streaming to disk — constant memory)."""
        start = datetime.now()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.log.info("=" * 70)
        self.log.info("ICP FILTER PIPELINE STARTED (streaming to disk)")
        self.log.info("Min score: %d | Top N: %s", self.min_score,
                       self.top_n or "unlimited")
        self.log.info("=" * 70)

        # Open output CSVs per tier — write directly to disk
        out_path = self.output_dir / f"icp_qualified_{timestamp}.csv"
        tier_paths = {
            "tier1": self.output_dir / f"icp_tier1_hot_{timestamp}.csv",
            "tier2": self.output_dir / f"icp_tier2_high_{timestamp}.csv",
            "tier3": self.output_dir / f"icp_tier3_moderate_{timestamp}.csv",
            "tier4": self.output_dir / f"icp_tier4_nurture_{timestamp}.csv",
        }

        # Stats tracking (no row data in memory)
        total_rows = 0
        qualified = 0
        tier_counts = {"tier1": 0, "tier2": 0, "tier3": 0, "tier4": 0}
        score_sum = 0
        scores_hist = [0] * 101  # histogram of scores 0-100
        reason_counts = {}
        state_counts = {}
        revenue_sum = 0
        revenue_count = 0
        occupancy_sum = 0
        occupancy_count = 0
        occ_below_50 = 0
        occ_below_60 = 0
        rating_below_45 = 0
        file_count = 0

        # Fieldnames for output
        fieldnames = [
            "icp_score", "icp_tier", "icp_reasons",
            "Latitude", "Longitude", "Listing URL", "Listing Title",
            "Revenue LTM (USD)", "Occupancy Rate LTM", "ADR (USD)",
            "Overall Rating", "Number of Reviews",
            "Number of Properties", "Bedrooms",
            "Property Type", "City", "State", "AirDNA Market",
            "Revenue Potential LTM (USD)",
        ]
        extra_fields_added = False
        out_fh = open(out_path, "w", newline="", encoding="utf-8")
        out_writer = None
        tier_fhs = {k: open(v, "w", newline="", encoding="utf-8") for k, v in tier_paths.items()}
        tier_writers = {}

        try:
            for path in self.input_paths:
                file_count += 1
                self.log.info("Reading file %d: %s", file_count, path)
                file_rows = 0

                for row in self.iter_csv(path):
                    total_rows += 1
                    file_rows += 1

                    # Add extra fields from first row
                    if not extra_fields_added:
                        for k in row:
                            if k not in fieldnames:
                                fieldnames.append(k)
                        out_writer = csv.DictWriter(out_fh, fieldnames=fieldnames, extrasaction="ignore")
                        out_writer.writeheader()
                        for k in tier_fhs:
                            tier_writers[k] = csv.DictWriter(tier_fhs[k], fieldnames=fieldnames, extrasaction="ignore")
                            tier_writers[k].writeheader()
                        extra_fields_added = True

                    score, reasons, fields = self.scorer.score(row)

                    if score >= self.min_score:
                        qualified += 1
                        score_sum += score
                        scores_hist[min(score, 100)] += 1

                        # Determine tier
                        if score >= 90:
                            tier = "tier1"
                            tier_label = "T1_HOT"
                        elif score >= 70:
                            tier = "tier2"
                            tier_label = "T2_HIGH"
                        elif score >= 50:
                            tier = "tier3"
                            tier_label = "T3_MODERATE"
                        else:
                            tier = "tier4"
                            tier_label = "T4_NURTURE"
                        tier_counts[tier] += 1

                        # Write to disk immediately
                        out_row = dict(row)
                        out_row["icp_score"] = score
                        out_row["icp_tier"] = tier_label
                        out_row["icp_reasons"] = "|".join(reasons)
                        out_writer.writerow(out_row)
                        tier_writers[tier].writerow(out_row)

                        # Update stats
                        for r in reasons:
                            reason_counts[r] = reason_counts.get(r, 0) + 1
                        st = fields.get("state", "??")
                        state_counts[st] = state_counts.get(st, 0) + 1
                        rev = fields.get("revenue", 0)
                        if rev > 0:
                            revenue_sum += rev
                            revenue_count += 1
                        occ = fields.get("occupancy", 0)
                        if occ > 0:
                            occupancy_sum += occ
                            occupancy_count += 1
                            if occ < 50:
                                occ_below_50 += 1
                            if occ < 60:
                                occ_below_60 += 1
                        rat = fields.get("rating", 0)
                        if rat > 0 and rat < 4.5:
                            rating_below_45 += 1

                    # Progress every 100K rows
                    if total_rows % 100000 == 0:
                        self.log.info("  Progress: %dk rows | %d qualified (%.1f%%) | T1:%d T2:%d T3:%d T4:%d",
                                      total_rows // 1000, qualified,
                                      qualified / total_rows * 100,
                                      tier_counts["tier1"], tier_counts["tier2"],
                                      tier_counts["tier3"], tier_counts["tier4"])

                self.log.info("  File: %d rows | Total qualified: %d", file_rows, qualified)

        finally:
            out_fh.close()
            for fh in tier_fhs.values():
                fh.close()

        # --- Compute summary from streaming stats (no in-memory data) ---
        elapsed = (datetime.now() - start).total_seconds()

        # Compute median score from histogram
        median_score = 0
        if qualified > 0:
            half = qualified // 2
            running = 0
            for i in range(100, -1, -1):
                running += scores_hist[i]
                if running >= half:
                    median_score = i
                    break

        avg_score = score_sum / max(qualified, 1)
        avg_revenue = revenue_sum / max(revenue_count, 1)
        avg_occupancy = occupancy_sum / max(occupancy_count, 1)

        summary = {
            "total_rows_scanned": total_rows,
            "qualified_leads": qualified,
            "qualification_rate": f"{qualified / max(total_rows, 1) * 100:.1f}%",
            "tiers": {
                "tier1_hot_90plus": tier_counts["tier1"],
                "tier2_high_70_89": tier_counts["tier2"],
                "tier3_moderate_50_69": tier_counts["tier3"],
                "tier4_nurture_30_49": tier_counts["tier4"],
            },
            "score_stats": {
                "mean": round(avg_score, 1),
                "median": median_score,
                "max": max((i for i in range(101) if scores_hist[i] > 0), default=0),
                "min": min((i for i in range(101) if scores_hist[i] > 0), default=0),
            },
            "revenue_stats": {
                "mean": round(avg_revenue, 2),
                "total_addressable_revenue": round(revenue_sum, 2),
                "leads_with_revenue": revenue_count,
            },
            "occupancy_stats": {
                "mean": round(avg_occupancy, 1),
                "below_50pct": occ_below_50,
                "below_60pct": occ_below_60,
            },
            "rating_stats": {
                "below_4_5": rating_below_45,
            },
            "top_reasons": dict(sorted(reason_counts.items(),
                                        key=lambda x: -x[1])[:20]),
            "top_states": dict(sorted(state_counts.items(),
                                       key=lambda x: -x[1])[:15]),
            "enrichment_cost_estimate": {
                "airdna_contacts_1_dollar": f"${qualified * 1:,}",
                "airdna_contacts_2_dollar": f"${qualified * 2:,}",
                "tracerfy_batch_mode": f"${qualified * 0.02:,.0f}",
                "tracerfy_lookup_mode": f"${qualified * 0.10:,.0f}",
                "millionverifier": f"${qualified * 0.0013:,.0f}",
            },
            "conversion_projections": {
                "at_1pct_conversion": int(qualified * 0.01),
                "at_2pct_conversion": int(qualified * 0.02),
                "at_3pct_conversion": int(qualified * 0.03),
                "at_5pct_conversion": int(qualified * 0.05),
                "leads_needed_for_3000_at_1pct": 300000,
                "leads_needed_for_3000_at_2pct": 150000,
                "leads_needed_for_3000_at_3pct": 100000,
                "leads_needed_for_3000_at_5pct": 60000,
            },
            "output_files": {
                "all_qualified": str(out_path),
                "tier1": str(tier_paths["tier1"]),
                "tier2": str(tier_paths["tier2"]),
                "tier3": str(tier_paths["tier3"]),
                "tier4": str(tier_paths["tier4"]),
            },
            "elapsed_seconds": round(elapsed, 1),
            "timestamp": datetime.now().isoformat(),
        }

        # Write summary JSON
        summary_path = self.output_dir / f"icp_summary_{timestamp}.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        self.log.info("=" * 70)
        self.log.info("ICP FILTER COMPLETE")
        self.log.info("  Total rows scanned: %d", total_rows)
        self.log.info("  Files processed: %d", file_count)
        self.log.info("  Qualified leads: %d (%.1f%%)",
                       qualified, qualified / max(total_rows, 1) * 100)
        self.log.info("  Tier 1 (90+): %d", tier_counts["tier1"])
        self.log.info("  Tier 2 (70-89): %d", tier_counts["tier2"])
        self.log.info("  Tier 3 (50-69): %d", tier_counts["tier3"])
        self.log.info("  Tier 4 (30-49): %d", tier_counts["tier4"])
        self.log.info("  Avg score: %.1f | Median: %d", avg_score, median_score)
        self.log.info("  Output: %s", out_path)
        self.log.info("  Summary: %s", summary_path)
        self.log.info("  Elapsed: %.1f seconds", elapsed)
        self.log.info("=" * 70)

        return summary



# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="AirDNA ICP Pre-Filter & Lead Scoring Engine"
    )
    parser.add_argument(
        "inputs", nargs="+",
        help="One or more AirDNA CSV or CSV.GZ files (supports glob)"
    )
    parser.add_argument(
        "-o", "--output-dir", default="./filtered_output",
        help="Output directory (default: ./filtered_output)"
    )
    parser.add_argument(
        "--min-score", type=int, default=30,
        help="Minimum ICP score to qualify (default: 30)"
    )
    parser.add_argument(
        "--top-n", type=int, default=0,
        help="Limit output to top N leads by score (0 = unlimited)"
    )
    parser.add_argument(
        "--tier1-only", action="store_true",
        help="Only output Tier 1 leads (score 90+)"
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging"
    )
    args = parser.parse_args()

    # Setup logging
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)

    # Adjust min_score for tier1-only
    min_score = 90 if args.tier1_only else args.min_score

    pipeline = ICPFilterPipeline(
        input_paths=args.inputs,
        output_dir=Path(args.output_dir),
        min_score=min_score,
        top_n=args.top_n,
    )

    summary = pipeline.run()

    # Print key stats
    print("\n" + "=" * 60)
    print("ICP FILTER RESULTS")
    print("=" * 60)
    print(f"  Total scanned:    {summary['total_rows_scanned']:,}")
    print(f"  Qualified leads:  {summary['qualified_leads']:,} ({summary['qualification_rate']})")
    print(f"  Tier 1 (HOT):     {summary['tiers']['tier1_hot_90plus']:,}")
    print(f"  Tier 2 (HIGH):    {summary['tiers']['tier2_high_70_89']:,}")
    print(f"  Tier 3 (MODERATE):{summary['tiers']['tier3_moderate_50_69']:,}")
    print(f"  Tier 4 (NURTURE): {summary['tiers']['tier4_nurture_30_49']:,}")
    print(f"\n  Enrichment cost estimates:")
    for k, v in summary['enrichment_cost_estimate'].items():
        print(f"    {k}: {v}")
    print(f"\n  Conversion projections (to reach 3,000 clients):")
    for k, v in summary['conversion_projections'].items():
        print(f"    {k}: {v:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
