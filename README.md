# NovaMind AI Content Pipeline

A take-home project for the Content & Growth Analyst role at Palona AI.

The goal was to build an automated marketing pipeline that goes from a blog topic all the way through to newsletter distribution and performance analysis. I built it as a Python CLI + optional Flask dashboard.

---

## What it does

You give it a topic. It:
1. Uses the Claude API to generate a blog post (outline + ~500 word draft) and 3 persona-targeted newsletter variants
2. Creates contacts in HubSpot, segments them by persona, and sends the right newsletter to each segment
3. Collects engagement data (open rate, click rate, unsubscribes) and runs it through Claude to generate a performance summary + recommendations

The whole thing is mostly hands-off once you run it. There's also a simple Flask dashboard if you prefer a UI over the command line.

---

## Architecture

```
topic input
    │
    ▼
┌─────────────────────────────────────────┐
│  content_generator.py                   │
│                                         │
│  Claude API (claude-opus-4-5)           │
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

I picked these based on NovaMind's stated audience (small creative agencies):

| Persona | Description | Main pain points |
|---|---|---|
| Solo Freelancer | 1-person creative shop, budget-sensitive | too much admin, not enough hours |
| Agency Owner | runs 5-20 person agency | scaling delivery, margin pressure |
| Project Manager | ops/PM at a creative agency | tool fragmentation, missed deadlines |

Each persona gets a different newsletter version with a tailored subject line, body, and CTA. There's also a B-variant subject line per persona for A/B testing (bonus feature).

---

## File structure

```
novamind-pipeline/
├── pipeline.py             # run this — orchestrates all 3 stages
├── content_generator.py    # stage 1: blog + newsletters via Claude
├── crm_integration.py      # stage 2: HubSpot contacts + sending
├── performance_tracker.py  # stage 3: engagement data + AI summary
├── app.py                  # optional Flask dashboard
├── requirements.txt
└── data/
    ├── content/            # generated blog + newsletter JSON
    ├── campaigns/          # campaign logs
    └── performance/        # engagement metrics + AI summaries
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

Getting a HubSpot API key (free):
- Go to developers.hubspot.com and create a free developer account
- Under Settings → Integrations → Private Apps, create a new app
- Grant scopes: `crm.objects.contacts.write` and `marketing-email`
- Copy the access token

Note: the pipeline assumes a custom contact property `novamind_persona` exists in HubSpot. You'd create it once via:
```
POST /crm/v3/properties/contacts
{"name": "novamind_persona", "label": "NovaMind Persona", "type": "string", "fieldType": "text", "groupName": "contactinformation"}
```

**3. Run the pipeline**
```bash
# default (dry run — simulates HubSpot calls, no real API needed)
python pipeline.py

# custom topic
python pipeline.py --topic "5 ways AI can cut creative agency overhead"

# live mode (real HubSpot API calls)
python pipeline.py --topic "your topic" --live
```

**4. Launch the dashboard (optional)**
```bash
python app.py
# open http://localhost:5000
```

---

## Assumptions and notes

- **Performance data is simulated by default.** In production, you'd poll `GET /marketing/v3/emails/{emailId}/statistics/histogram` 24-48 hours after sending. I simulate plausible numbers immediately so the full pipeline is demonstrable without waiting.

- **Mock contacts are used.** The 7 test contacts cover all 3 personas. In production these would come from your actual contact list or a CRM import.

- **Dry run is the default.** All HubSpot calls are printed but not executed unless you pass `--live`. This lets you see exactly what the API payloads look like without needing a real account for the demo.

- **JSON storage is intentionally simple.** A real version would probably use a CMS (Contentful, Sanity) or a database. For this project, flat JSON files are enough to demonstrate the pipeline and keep things easy to inspect.

- **The A/B subject line variants** (bonus feature) are generated alongside the primary newsletter for each persona. The dashboard shows both the A and B versions side by side.

---

## Example output

After running, `data/performance/perf_camp_*_final.json` contains something like:

```
## Performance Summary

**Best performer: Agency Owners** — 34.2% open rate, 15.1% click rate.
The outcome-focused subject line ("double your output without hiring") 
likely hit the right nerve for this segment.

**Optimization opportunities:**
1. Solo Freelancer click rate (7.8%) lags despite solid opens (38%). 
   Try a more specific CTA — "save 5 hrs/week" vs. generic "start free trial"
2. Project Manager segment would benefit from calling out specific tools 
   (Asana, Notion) in the body copy

**Recommended next topics:**
1. "The real cost of context-switching for creative teams"
2. "5 repetitive tasks agencies should automate this quarter"
3. "How to pitch AI automation to a skeptical client"

**A/B test to run next send:**
Agency Owner segment — test "double your output" (outcome) vs. 
"how top agencies use AI in 2025" (social proof)
```

---

*Built by Adarsh Tiwari for the Palona AI take-home assignment.*
