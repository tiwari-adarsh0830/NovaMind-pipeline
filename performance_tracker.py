"""
performance_tracker.py

Performance tracking + AI analysis for sent campaigns.
Simulates engagement data (in prod would poll HubSpot stats API),
stores history, and generates an AI summary with optimization recommendations.
"""

import anthropic
import json
import os
import random
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
PERF_DIR = BASE_DIR / "data" / "performance"

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# baseline engagement ranges by persona (based on industry benchmarks for SaaS/B2B)
BASELINES = {
    "solo_freelancer": {
        "open":        (0.28, 0.44),
        "click":       (0.06, 0.15),
        "unsubscribe": (0.001, 0.008),
    },
    "agency_owner": {
        "open":        (0.22, 0.36),
        "click":       (0.08, 0.18),
        "unsubscribe": (0.002, 0.010),
    },
    "project_manager": {
        "open":        (0.25, 0.39),
        "click":       (0.07, 0.16),
        "unsubscribe": (0.001, 0.007),
    }
}


def collect_performance(campaign_log: dict, by_persona: dict) -> dict:
    """
    Simulate engagement metrics per persona segment.
    In production: GET /marketing/v3/emails/{emailId}/statistics/histogram
    """
    PERF_DIR.mkdir(parents=True, exist_ok=True)
    print("\ncollecting performance data...")

    perf = {
        "campaign_id": campaign_log["campaign_id"],
        "blog_title":  campaign_log["blog_title"],
        "measured_at": datetime.now().isoformat(),
        "personas":    {}
    }

    for persona_key, baseline in BASELINES.items():
        contacts = by_persona.get(persona_key, [])
        n = len(contacts)
        if n == 0:
            continue

        open_rate  = round(random.uniform(*baseline["open"]),        4)
        click_rate = round(random.uniform(*baseline["click"]),       4)
        unsub_rate = round(random.uniform(*baseline["unsubscribe"]), 4)

        opens  = int(n * open_rate)
        clicks = int(n * click_rate)
        unsubs = max(0, int(n * unsub_rate))
        ctor   = round(clicks / opens, 4) if opens > 0 else 0.0

        perf["personas"][persona_key] = {
            "persona_name":         persona_key.replace("_", " ").title(),
            "recipients":           n,
            "opens":                opens,
            "clicks":               clicks,
            "unsubscribes":         unsubs,
            "open_rate":            open_rate,
            "click_rate":           click_rate,
            "click_to_open_rate":   ctor,
            "unsubscribe_rate":     unsub_rate,
            "avg_time_to_open_hrs": round(random.uniform(0.5, 7.0), 1),
            "source":               "simulated"
        }
        print(f"  {persona_key}: open={open_rate*100:.1f}% click={click_rate*100:.1f}% unsub={unsubs}")

    all_r = sum(p["recipients"] for p in perf["personas"].values())
    all_o = sum(p["opens"]      for p in perf["personas"].values())
    all_c = sum(p["clicks"]     for p in perf["personas"].values())

    perf["overall"] = {
        "total_recipients": all_r,
        "total_opens":      all_o,
        "total_clicks":     all_c,
        "open_rate":        round(all_o / all_r, 4) if all_r > 0 else 0.0,
        "click_rate":       round(all_c / all_r, 4) if all_r > 0 else 0.0,
    }

    return perf


def save_performance(perf: dict) -> Path:
    PERF_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    p = PERF_DIR / f"perf_{perf['campaign_id']}_{ts}.json"
    p.write_text(json.dumps(perf, indent=2))
    print(f"  saved: {p.name}")
    return p


def load_history() -> list:
    if not PERF_DIR.exists():
        return []
    records = []
    for f in sorted(PERF_DIR.glob("perf_*.json")):
        try:
            records.append(json.loads(f.read_text()))
        except Exception:
            pass
    return records


def generate_ai_summary(perf: dict, history: list) -> str:
    """Call Claude to produce a performance summary with recommendations."""
    print("\ngenerating AI summary...")

    hist_ctx = ""
    prior = [r for r in history if r.get("campaign_id") != perf["campaign_id"]]
    if prior:
        prev = prior[-1]
        prev_overall = prev.get("overall", {})
        hist_ctx = f"""
Previous campaign: "{prev.get('blog_title', 'N/A')}"
- Open rate:  {prev_overall.get('open_rate', 0)*100:.1f}%
- Click rate: {prev_overall.get('click_rate', 0)*100:.1f}%
"""

    overall = perf["overall"]
    prompt = f"""You are the growth analytics system for NovaMind, an AI startup.

Analyze this email campaign and give actionable recommendations.

Campaign: "{perf['blog_title']}"
Date: {perf['measured_at'][:10]}

Overall:
- Recipients:  {overall['total_recipients']}
- Open rate:   {overall['open_rate']*100:.1f}%
- Click rate:  {overall['click_rate']*100:.1f}%

By persona:
{json.dumps(perf['personas'], indent=2)}

{f"Historical context:{hist_ctx}" if hist_ctx else "First campaign - no prior data."}

Write a 150-200 word summary covering:
1. Which persona performed best and a likely reason why
2. 1-2 concrete optimization suggestions
3. 3 recommended next blog topics based on what's working
4. One A/B test to run on the next campaign

Be specific and data-driven. Use markdown for formatting."""

    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        summary = resp.content[0].text.strip()
        print("  AI summary done")
        return summary
    except Exception as e:
        print(f"  warn: AI summary failed ({e}), using placeholder")
        return f"[AI summary unavailable: {e}]"


def run_performance_tracking(campaign_log: dict, by_persona: dict) -> dict:
    perf = collect_performance(campaign_log, by_persona)
    save_performance(perf)
    history = load_history()
    perf["ai_summary"] = generate_ai_summary(perf, history)

    final_path = PERF_DIR / f"perf_{perf['campaign_id']}_final.json"
    final_path.write_text(json.dumps(perf, indent=2))

    overall = perf["overall"]
    print(f"\n--- performance ---")
    print(f"recipients: {overall['total_recipients']}")
    print(f"open rate:  {overall['open_rate']*100:.1f}%")
    print(f"click rate: {overall['click_rate']*100:.1f}%")
    print(f"\nAI analysis:\n{perf['ai_summary']}")

    return perf
