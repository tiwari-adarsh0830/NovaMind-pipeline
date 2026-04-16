"""
pipeline.py — main entry point

Runs the full NovaMind content pipeline:
  generate -> distribute -> analyze

Usage:
  python pipeline.py
  python pipeline.py --topic "your topic here"
  python pipeline.py --topic "your topic" --live     # real HubSpot calls
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

# check env vars before doing anything
def check_env():
    missing = []
    if not os.environ.get("GEMINI_API_KEY"):
        missing.append("GEMINI_API_KEY")
    if missing:
        print(f"error: missing required env vars: {', '.join(missing)}")
        print("set them with: export GEMINI_API_KEY=your_key_here")
        sys.exit(1)

check_env()

from content_generator import run_content_generation
from crm_integration import run_distribution
from performance_tracker import run_performance_tracking

BASE_DIR = Path(__file__).parent


def run_pipeline(topic: str, dry_run: bool = True) -> dict:
    start = datetime.now()
    mode = "dry run" if dry_run else "LIVE"

    print(f"""
╔══════════════════════════════════════════════════════╗
║         NOVAMIND AI CONTENT PIPELINE                 ║
╚══════════════════════════════════════════════════════╝
topic: {topic}
mode:  {mode}
start: {start.strftime('%Y-%m-%d %H:%M:%S')}
""")

    # stage 1
    print("=" * 54)
    print("STAGE 1 — content generation")
    print("=" * 54)
    content_pkg = run_content_generation(topic)
    print(f"\nstage 1 done: blog + 3 newsletters generated")

    # stage 2
    print("\n" + "=" * 54)
    print("STAGE 2 — CRM distribution")
    print("=" * 54)
    dist = run_distribution(content_pkg, dry_run=dry_run)
    print(f"\nstage 2 done: contacts synced, campaigns sent")

    # stage 3
    print("\n" + "=" * 54)
    print("STAGE 3 — performance tracking + AI analysis")
    print("=" * 54)
    perf = run_performance_tracking(
        dist["campaign_log"],
        dist["by_persona"]
    )
    print(f"\nstage 3 done: performance logged, AI analysis complete")

    elapsed = (datetime.now() - start).seconds

    print(f"""
{'=' * 54}
DONE ({elapsed}s)
{'=' * 54}
blog:       {content_pkg['blog']['title']}
campaign:   {dist['campaign_log']['campaign_id']}
recipients: {perf['overall']['total_recipients']}
open rate:  {perf['overall']['open_rate']*100:.1f}%
click rate: {perf['overall']['click_rate']*100:.1f}%

output files:
  data/content/package_{content_pkg['content_id']}.json
  data/campaigns/{dist['campaign_log']['campaign_id']}.json
  data/performance/perf_{dist['campaign_log']['campaign_id']}_final.json

dashboard: python app.py -> http://localhost:5000
""")

    summary = {
        "content_id":   content_pkg["content_id"],
        "topic":        topic,
        "blog_title":   content_pkg["blog"]["title"],
        "campaign_id":  dist["campaign_log"]["campaign_id"],
        "open_rate":    perf["overall"]["open_rate"],
        "click_rate":   perf["overall"]["click_rate"],
        "completed_at": datetime.now().isoformat()
    }
    out = BASE_DIR / "data" / f"run_{content_pkg['content_id']}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2))

    return {"content": content_pkg, "distribution": dist, "performance": perf}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NovaMind AI content pipeline")
    parser.add_argument(
        "--topic",
        default="How AI is changing creative agency workflows in 2025",
        help="blog topic to generate content for"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="use real HubSpot API (requires HUBSPOT_API_KEY). default is dry run."
    )
    args = parser.parse_args()
    run_pipeline(topic=args.topic, dry_run=not args.live)
