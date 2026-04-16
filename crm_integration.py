"""
crm_integration.py

HubSpot CRM integration — contacts, email campaigns, distribution, campaign logging.

In dry_run mode (default) it prints what it would do but makes no real API calls.
Set dry_run=False and provide HUBSPOT_API_KEY to go live.
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent
CAMPAIGN_DIR = BASE_DIR / "data" / "campaigns"

HUBSPOT_BASE = "https://api.hubapi.com"
HUBSPOT_KEY = os.environ.get("HUBSPOT_API_KEY", "")

def _headers():
    return {
        "Authorization": f"Bearer {HUBSPOT_KEY}",
        "Content-Type": "application/json"
    }


# mock contacts — realistic test data covering all 3 personas
MOCK_CONTACTS = [
    {"email": "sarah.chen@freelancecreative.io", "firstname": "Sarah",  "lastname": "Chen",    "persona": "solo_freelancer", "company": "Self-Employed"},
    {"email": "mike.torres@pixeldrift.co",       "firstname": "Mike",   "lastname": "Torres",  "persona": "solo_freelancer", "company": "Pixel Drift"},
    {"email": "jessica.park@novocreative.com",   "firstname": "Jessica","lastname": "Park",    "persona": "agency_owner",    "company": "Novo Creative"},
    {"email": "david.kim@brandlabstudio.io",     "firstname": "David",  "lastname": "Kim",     "persona": "agency_owner",    "company": "BrandLab Studio"},
    {"email": "priya.sharma@agencyx.co",         "firstname": "Priya",  "lastname": "Sharma",  "persona": "agency_owner",    "company": "Agency X"},
    {"email": "tom.nguyen@creativeops.com",      "firstname": "Tom",    "lastname": "Nguyen",  "persona": "project_manager", "company": "Creative Ops"},
    {"email": "lisa.patel@designhubnyc.io",      "firstname": "Lisa",   "lastname": "Patel",   "persona": "project_manager", "company": "DesignHub NYC"},
]


def upsert_contact(contact: dict, dry_run: bool = True) -> dict:
    """
    Create or update a contact in HubSpot with persona tagging.
    Uses batch upsert by email (idProperty=email).

    Real endpoint: POST /crm/v3/objects/contacts/batch/upsert
    """
    props = {
        "email":             contact["email"],
        "firstname":         contact["firstname"],
        "lastname":          contact["lastname"],
        "company":           contact.get("company", ""),
        "novamind_persona":  contact["persona"],
        "hs_lead_status":    "NEW"
    }

    if dry_run:
        print(f"  [dry run] upsert contact: {contact['email']} | persona={contact['persona']}")
        return {"id": f"mock_{contact['email']}", "properties": props}

    url = f"{HUBSPOT_BASE}/crm/v3/objects/contacts/batch/upsert"
    payload = {
        "inputs": [{
            "idProperty": "email",
            "id": contact["email"],
            "properties": props
        }]
    }
    r = requests.post(url, headers=_headers(), json=payload)
    if r.status_code in (200, 201):
        result = r.json()["results"][0]
        print(f"  upserted: {contact['email']} (id={result['id']})")
        return result
    else:
        # don't crash the pipeline on CRM errors
        print(f"  warn: hubspot error {r.status_code} for {contact['email']}: {r.text[:150]}")
        return {"id": f"fallback_{contact['email']}", "error": r.status_code}


def sync_contacts(dry_run: bool = True) -> dict:
    """Upsert all mock contacts, return persona -> list of contacts mapping."""
    print("\nsyncing contacts to HubSpot...")
    by_persona = {}

    for c in MOCK_CONTACTS:
        result = upsert_contact(c, dry_run=dry_run)
        p = c["persona"]
        by_persona.setdefault(p, []).append({
            "email":  c["email"],
            "name":   f"{c['firstname']} {c['lastname']}",
            "crm_id": result.get("id", "unknown")
        })

    total = sum(len(v) for v in by_persona.values())
    print(f"  {total} contacts synced across {len(by_persona)} segments")
    return by_persona


def create_email(newsletter: dict, blog_title: str, dry_run: bool = True) -> dict:
    """
    Create a HubSpot marketing email for one persona's newsletter.

    Real endpoint: POST /marketing/v3/emails
    Returns the created email object (or mock).
    """
    name = f"NovaMind Weekly | {newsletter['persona_name']} | {datetime.now().strftime('%b %d %Y')}"

    payload = {
        "name":          name,
        "subject":       newsletter["subject_line"],
        "previewText":   newsletter.get("preview_text", ""),
        "fromName":      "NovaMind Team",
        "replyTo":       "hello@novamind.ai",
        "sendingDomain": "novamind.ai",
        "content": {
            "body": _build_html(newsletter, blog_title)
        }
    }

    if dry_run:
        mock_id = f"mock_email_{newsletter['persona_key']}_{datetime.now().strftime('%H%M%S')}"
        print(f"  [dry run] create email: '{name}'")
        return {"id": mock_id, "name": name, "subject": newsletter["subject_line"]}

    url = f"{HUBSPOT_BASE}/marketing/v3/emails"
    r = requests.post(url, headers=_headers(), json=payload)
    if r.status_code in (200, 201):
        result = r.json()
        print(f"  created email: '{name}' (id={result['id']})")
        return result
    else:
        print(f"  warn: email creation failed {r.status_code}: {r.text[:150]}")
        return {"id": f"mock_email_{newsletter['persona_key']}", "name": name,
                "subject": newsletter["subject_line"], "error": r.status_code}


def send_emails(email_id: str, persona_key: str, contacts: list, dry_run: bool = True) -> dict:
    """
    Send a HubSpot email to all contacts in a persona segment.

    Real endpoint: POST /marketing/v3/transactional/single-email/send
    (single-send API — one call per recipient)
    """
    results = []

    for contact in contacts:
        if dry_run:
            print(f"  [dry run] send {email_id} -> {contact['email']}")
            results.append({"email": contact["email"], "status": "simulated", "sent_at": datetime.now().isoformat()})
            continue

        url = f"{HUBSPOT_BASE}/marketing/v3/transactional/single-email/send"
        payload = {
            "emailId": email_id,
            "message": {"to": contact["email"]},
            "contactProperties": {"email": contact["email"]}
        }
        r = requests.post(url, headers=_headers(), json=payload)
        status = "sent" if r.status_code in (200, 201, 204) else f"error_{r.status_code}"
        results.append({"email": contact["email"], "status": status, "sent_at": datetime.now().isoformat()})

    sent = sum(1 for r in results if r["status"] in ("sent", "simulated"))
    print(f"  {persona_key}: {sent}/{len(results)} sent")
    return {"persona": persona_key, "recipients": results}


def _build_html(newsletter: dict, blog_title: str) -> str:
    """Build inline-styled HTML email body (compatible with email clients)."""
    body_html = newsletter.get("body", "").replace("\n", "<br>")
    return f"""<html>
<body style="margin:0;padding:0;background:#f4f4f5;font-family:Georgia,serif;">
  <table width="100%" cellpadding="0" cellspacing="0">
    <tr>
      <td align="center" style="padding:32px 16px;">
        <table width="600" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:8px;overflow:hidden;">

          <!-- header -->
          <tr>
            <td style="background:#0f0f1a;padding:24px;text-align:center;">
              <h1 style="margin:0;color:#a78bfa;font-size:22px;letter-spacing:3px;font-family:Arial,sans-serif;">NOVAMIND</h1>
              <p style="margin:4px 0 0;color:#6b7280;font-size:12px;font-family:Arial,sans-serif;">AI-Powered Workflow Automation</p>
            </td>
          </tr>

          <!-- persona label -->
          <tr>
            <td style="background:#1e1b4b;padding:8px 24px;">
              <p style="margin:0;color:#c4b5fd;font-size:11px;font-family:Arial,sans-serif;letter-spacing:2px;text-transform:uppercase;">
                {newsletter.get('persona_name','').upper()} EDITION
              </p>
            </td>
          </tr>

          <!-- body -->
          <tr>
            <td style="padding:32px 24px;">
              <h2 style="margin:0 0 16px;font-size:20px;color:#111827;">{newsletter.get('subject_line','')}</h2>
              <p style="margin:0 0 16px;color:#6b7280;font-style:italic;">{newsletter.get('greeting','')}</p>
              <div style="line-height:1.75;color:#374151;font-size:15px;">{body_html}</div>
              <div style="margin:32px 0;text-align:center;">
                <a href="https://novamind.ai/blog"
                   style="background:#7c3aed;color:#ffffff;padding:14px 32px;border-radius:6px;
                          text-decoration:none;font-weight:bold;font-size:14px;font-family:Arial,sans-serif;
                          display:inline-block;">
                  {newsletter.get('cta_text', 'Learn More')}
                </a>
              </div>
            </td>
          </tr>

          <!-- footer -->
          <tr>
            <td style="padding:16px 24px;border-top:1px solid #e5e7eb;text-align:center;">
              <p style="margin:0;font-size:11px;color:#9ca3af;font-family:Arial,sans-serif;">
                NovaMind &bull; hello@novamind.ai &bull;
                <a href="#" style="color:#9ca3af;">Unsubscribe</a>
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def log_campaign(content_id: str, blog_title: str, emails: dict, sends: dict) -> dict:
    """Write campaign log to data/campaigns/."""
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)

    log = {
        "campaign_id":      f"camp_{content_id}",
        "content_id":       content_id,
        "blog_title":       blog_title,
        "send_date":        datetime.now().isoformat(),
        "total_recipients": 0,
        "emails":           {}
    }

    for persona_key, email_data in emails.items():
        recipients = sends.get(persona_key, {}).get("recipients", [])
        log["emails"][persona_key] = {
            "email_id":        email_data.get("id", ""),
            "email_name":      email_data.get("name", ""),
            "subject":         email_data.get("subject", ""),
            "recipient_count": len(recipients),
            "sent_at":         datetime.now().isoformat()
        }
        log["total_recipients"] += len(recipients)

    out = CAMPAIGN_DIR / f"{log['campaign_id']}.json"
    out.write_text(json.dumps(log, indent=2))
    print(f"\ncampaign logged: {log['campaign_id']} | {log['total_recipients']} recipients")
    return log


def run_distribution(content_package: dict, dry_run: bool = True) -> dict:
    """
    Full distribution pipeline:
    1. Sync contacts to HubSpot (upsert + persona tagging)
    2. Create email per persona segment
    3. Send to each segment
    4. Log the campaign
    """
    blog_title  = content_package["blog"]["title"]
    newsletters = content_package["newsletters"]
    content_id  = content_package["content_id"]

    mode = "DRY RUN" if dry_run else "LIVE"
    print(f"\n--- distribution ({mode}): {blog_title} ---")

    # step 1: contacts
    by_persona = sync_contacts(dry_run=dry_run)

    # step 2: create emails
    print("\ncreating email campaigns...")
    emails = {}
    for key, nl in newsletters.items():
        emails[key] = create_email(nl, blog_title, dry_run=dry_run)

    # step 3: send
    print("\nsending...")
    sends = {}
    for key, email_data in emails.items():
        contacts = by_persona.get(key, [])
        if not contacts:
            print(f"  no contacts for persona '{key}', skipping")
            continue
        sends[key] = send_emails(email_data["id"], key, contacts, dry_run=dry_run)

    # step 4: log
    campaign_log = log_campaign(content_id, blog_title, emails, sends)

    return {
        "campaign_log":  campaign_log,
        "by_persona":    by_persona,
        "emails":        emails,
        "sends":         sends
    }
