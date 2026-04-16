# NovaMind AI Content Pipeline

A take-home project for the Content & Growth Analyst role at Palona AI.

The goal: build an automated marketing pipeline that takes a blog topic all the way through AI content generation, CRM distribution, and performance analysis — with a live dashboard to trigger and monitor it all.

---

## Demo

Run the pipeline in one command:
```bash
python pipeline.py --topic "How AI is changing creative agency workflows in 2025"
```

Then open the dashboard:
```bash
python app.py  # → http://localhost:5000
```

The dashboard lets you trigger new campaigns, view persona performance, read the AI analysis, and preview all 3 newsletter variants side by side.

---

## What it does

1. **AI Content Generation** — Takes a topic, calls the Claude API to generate a full blog post (outline + 400-600 word draft) and 3 persona-specific newsletters. Each newsletter also gets an A/B subject line variant for testing.

2. **CRM Distribution** — Creates/updates contacts in HubSpot segmented by persona, creates a marketing email per segment, and sends each persona the right newsletter. Full dry-run mode for testing without a live HubSpot account.

3. **Performance Tracking + AI Analysis** — Collects engagement metrics (open rate, click rate, CTOR, unsubscribes) per persona, stores historical data for trend comparison, and calls Claude to generate an actionable performance summary with next topic recommendations and A/B test suggestions.

4. **Flask Dashboard** — Web UI to trigger the full pipeline, view campaign history, compare persona performance, read AI insights, and preview newsletter content.

---

## Architecture

```
topic input
    │
    ▼
┌─────────────────────────────────────────┐
│  content_generator.py                   │
│                                         │
│  Claude API (claude-haiku-4-5)          │
│  ├─ blog post: title, outline, draft    │
│  │   └─ + 2 alt headlines for A/B      │
│  └─ 3x newsletters, one per persona    │
│      ├─ Solo Freelancer                 │
│      ├─ Agency Owner                    │
│      └─ Project Manager                 │
│  output: data/content/package_*.json    │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  crm_integration.py                     │
│                                         │
│  HubSpot API                            │
│  ├─ upsert contacts by email            │
│  │   POST /crm/v3/objects/contacts/     │
│  │        batch/upsert                  │
│  ├─ tag each contact with persona       │
│  ├─ create email per persona            │
│  │   POST /marketing/v3/emails          │
│  └─ send to each segment                │
│      POST /marketing/v3/transactional/  │
│           single-email/send             │
│  output: data/campaigns/camp_*.json     │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│  performance_tracker.py                 │
│                                         │
│  fetch/simulate engagement metrics      │
│  (open rate, click rate, unsubs, CTOR)  │
│  ├─ store per-campaign history          │
│  └─ Claude API → AI summary             │
│      · best persona + why               │
│      · optimization suggestions         │
│      · next 3 topic recommendations     │
│      · A/B test to run next time        │
│  output: data/performance/perf_*.json   │
└──────────────────┬──────────────────────┘
                   │
                   ▼ (optional)
┌─────────────────────────────────────────┐
│  app.py — Flask dashboard               │
│  campaign history, persona bars,        │
│  newsletter viewer, pipeline trigger    │
└─────────────────────────────────────────┘
```

---

## The 3 personas

Chosen based on NovaMind's target audience — small creative agencies:

| Persona | Description | Main pain points |
|---|---|---|
| Solo Freelancer | 1-person creative shop, budget-sensitive | too much admin, not enough hours |
| Agency Owner | runs 5-20 person agency | scaling delivery, margin pressure |
| Project Manager | ops/PM at a creative agency | tool fragmentation, missed deadlines |

Each persona gets a tailored newsletter (different subject line, body copy, CTA) plus a B-variant subject line for A/B testing.

---

## File structure

```
novamind-pipeline/
├── pipeline.py             # main entry point — run this
├── content_generator.py    # stage 1: AI blog + newsletter generation
├── crm_integration.py      # stage 2: HubSpot CRM + distribution
├── performance_tracker.py  # stage 3: metrics + AI analysis
├── app.py                  # Flask dashboard (optional)
├── requirements.txt
└── README.md

# generated at runtime (gitignored):
# data/content/      → blog + newsletter JSON
# data/campaigns/    → campaign logs
# data/performance/  → engagement metrics + AI summaries
```

---

## Setup

**1. Install dependencies**
```bash
pip install -r requirements.txt
```

**2. Set environment variables**
```bash
export ANTHROPIC_API_KEY="your-key-here"
export HUBSPOT_API_KEY="your-hubspot-key"   # only needed for --live mode
```

Getting an Anthropic API key: console.anthropic.com → API Keys → Create Key

Getting a HubSpot key (free developer account):
- Go to developers.hubspot.com → create free account
- Settings → Integrations → Private Apps → create app
- Scopes needed: `crm.objects.contacts.write` and `marketing-email`

Note: the pipeline uses a custom HubSpot contact property `novamind_persona`. Create it once:
```
POST /crm/v3/properties/contacts
{"name": "novamind_persona", "label": "NovaMind Persona", "type": "string", "fieldType": "text", "groupName": "contactinformation"}
```

**3. Run the pipeline**
```bash
# dry run (default — no real HubSpot calls needed)
python pipeline.py

# custom topic
python pipeline.py --topic "5 ways AI can cut creative agency overhead"

# live mode (real HubSpot API)
python pipeline.py --topic "your topic" --live
```

**4. Launch the dashboard**
```bash
python app.py
# open http://localhost:5000
```

---

## Assumptions

- **Performance data is simulated by default.** In production you'd poll `GET /marketing/v3/emails/{emailId}/statistics/histogram` 24-48h post-send. Simulated here so the full pipeline is demonstrable immediately.

- **Mock contacts used.** 7 test contacts across 3 personas. In production these come from your real CRM or contact import.

- **Dry run is default.** HubSpot calls are printed but not made unless you pass `--live`. Shows realistic endpoint usage and payload structure without needing a live account.

- **JSON storage is intentionally simple.** Production would use a CMS (Contentful, Sanity) or database. Flat JSON is enough to demonstrate the pipeline and easy to inspect.

- **A/B variants** are generated for every newsletter. The dashboard shows A and B subject lines side by side for each persona.

---

## Example AI performance output

```markdown
## Performance Summary

**Best performer: Agency Owners** — 34.2% open rate, 15.1% click rate.
The outcome-focused subject line ("double your output without hiring")
likely resonated strongly with this segment's primary concern.

**Optimization opportunities:**
1. Solo Freelancer click rate (7.8%) lags despite solid opens (38%).
   Try "save 5 hrs/week" instead of generic "start free trial"
2. Project Manager copy would benefit from naming specific tools
   (Asana, Notion) they already use

**Recommended next topics:**
1. "The real cost of context-switching for creative teams"
2. "5 repetitive tasks agencies should automate this quarter"
3. "How to pitch AI automation to a skeptical client"

**A/B test for next send:**
Agency Owner — "double your output" (outcome) vs.
"how top agencies use AI in 2025" (social proof)
```

---

*Built by Adarsh Tiwari — MS Data Science, NYU. For the Palona AI Content & Growth Analyst take-home.*
