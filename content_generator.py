"""
content_generator.py

Handles all AI content generation for the pipeline:
- blog post outline + draft
- 3 persona-specific newsletters
- bonus: multiple headline/copy variants for A/B testing
"""

import anthropic
import json
import os
import re
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data" / "content"

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# the 3 personas we landed on for NovaMind's audience
PERSONAS = {
    "solo_freelancer": {
        "name": "Solo Freelancer",
        "desc": "independent creative, 1-person shop, watches every dollar",
        "pain_points": "drowning in admin, no budget for more tools, juggling 5 clients at once",
        "tone": "conversational, empathetic, peer-to-peer",
        "cta": "Try NovaMind free — no credit card needed"
    },
    "agency_owner": {
        "name": "Creative Agency Owner",
        "desc": "owns or runs a small-mid agency (5-20 people), wants growth without burnout",
        "pain_points": "can't scale delivery fast enough, margins are tight, good people are expensive",
        "tone": "direct, results-focused, show the ROI clearly",
        "cta": "Book a 15-min demo and see the numbers"
    },
    "project_manager": {
        "name": "Agency Project Manager",
        "desc": "keeps things running at a creative agency, lives in Asana/Notion/Slack",
        "pain_points": "tools don't talk to each other, too many status meetings, deadlines always slip",
        "tone": "practical, tool-aware, give me something I can actually use today",
        "cta": "See how NovaMind fits your existing stack"
    }
}


def _call_claude(prompt: str, max_tokens: int = 1500, retries: int = 2) -> str:
    """calls Claude API with retry logic on transient failures"""
    for attempt in range(retries + 1):
        try:
            resp = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=max_tokens,
                messages=[{"role": "user", "content": prompt}]
            )
            return resp.content[0].text.strip()
        except Exception as e:
            if attempt < retries:
                print(f"  API error ({e}), retrying in 2s...")
                time.sleep(2)
            else:
                raise


def _parse_json(raw: str) -> dict:
    """
    Parse JSON from Claude's output.
    Handles cases where it wraps in ```json fences despite being told not to.
    """
    cleaned = re.sub(r'```(?:json)?\s*\n?', '', raw)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r'\{.*\}', cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        raise ValueError(f"couldn't parse JSON from response. raw output:\n{raw[:400]}")


def generate_blog(topic: str) -> dict:
    """Generate blog outline + 400-600 word draft plus 2 alt headlines."""
    print(f"\ngenerating blog for: '{topic}'")

    prompt = f"""You're the content lead at NovaMind, an early-stage AI startup that helps small creative agencies automate their daily workflows. Think Notion + Zapier + AI combined.

Write a blog post on this topic: "{topic}"

Return ONLY a valid JSON object (no markdown fences, no extra text) with this structure:
{{
    "title": "main blog title",
    "alt_titles": ["alternative headline 1 (different angle)", "alternative headline 2 (different angle)"],
    "meta_description": "SEO meta description, under 160 chars",
    "outline": [
        {{"section": "Introduction", "points": ["point 1", "point 2"]}},
        {{"section": "section 2 title", "points": ["point 1", "point 2"]}},
        {{"section": "section 3 title", "points": ["point 1", "point 2"]}},
        {{"section": "section 4 title", "points": ["point 1", "point 2"]}},
        {{"section": "Conclusion", "points": ["point 1", "point 2"]}}
    ],
    "draft": "Full blog post 400-600 words. Use markdown ## headers for sections. Conversational but authoritative tone. Soft CTA at the end mentioning NovaMind."
}}"""

    raw = _call_claude(prompt, max_tokens=2000)
    blog = _parse_json(raw)
    blog["topic"] = topic
    blog["generated_at"] = datetime.now().isoformat()

    wc = len(blog.get("draft", "").split())
    print(f"  done: '{blog['title']}' ({wc} words)")
    return blog


def generate_newsletters(blog: dict) -> dict:
    """Generate 3 persona-targeted newsletters with A/B subject variants."""
    print("\ngenerating newsletters...")
    newsletters = {}

    for key, persona in PERSONAS.items():
        print(f"  persona: {persona['name']}")

        prompt = f"""You write marketing emails for NovaMind, an AI startup serving creative agencies.

Blog to promote:
Title: {blog['title']}
Content: {blog['draft'][:600]}...

Target persona:
- Who: {persona['desc']}
- Pain points: {persona['pain_points']}
- Tone: {persona['tone']}
- CTA: {persona['cta']}

Return ONLY a valid JSON object (no fences) with this structure:
{{
    "subject_line": "primary subject, under 60 chars",
    "subject_line_b": "B variant subject for A/B test — different framing",
    "preview_text": "preheader text under 90 chars",
    "greeting": "opening line of the email body",
    "body": "150-200 word email. address their pain directly. reference the blog naturally. end with the CTA.",
    "cta_text": "button text, 3-5 words"
}}"""

        raw = _call_claude(prompt, max_tokens=700)
        nl = _parse_json(raw)
        nl["persona_key"] = key
        nl["persona_name"] = persona["name"]
        newsletters[key] = nl
        print(f"    subject: '{nl.get('subject_line', '?')}'")

    return newsletters


def save_content(blog: dict, newsletters: dict) -> dict:
    """Save everything to data/content/ and return the package."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r'[^a-z0-9]+', '_', blog["topic"].lower())[:25].strip('_')
    content_id = f"{slug}_{ts}"

    package = {
        "content_id": content_id,
        "topic": blog["topic"],
        "blog": blog,
        "newsletters": newsletters,
        "created_at": datetime.now().isoformat()
    }

    out = DATA_DIR / f"package_{content_id}.json"
    out.write_text(json.dumps(package, indent=2))
    print(f"\nsaved: {out.name}")
    return package


def run_content_generation(topic: str) -> dict:
    blog = generate_blog(topic)
    newsletters = generate_newsletters(blog)
    return save_content(blog, newsletters)


if __name__ == "__main__":
    pkg = run_content_generation("How AI is changing creative agency workflows in 2025")
    print(f"\ndone — content_id: {pkg['content_id']}")
