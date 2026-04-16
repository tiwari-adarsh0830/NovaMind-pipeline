"""
app.py — Flask dashboard

Run: python app.py
Open: http://localhost:5000

Lets you trigger the pipeline from a browser and see results in real time.
"""

import json
import os
import sys
import threading
from datetime import datetime
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

# make sure imports work regardless of where flask is invoked from
BASE_DIR = Path(__file__).parent
sys.path.insert(0, str(BASE_DIR))
os.chdir(BASE_DIR)  # all relative paths in the modules anchor here

app = Flask(__name__)

# shared state for pipeline progress (simple — single user dashboard)
_state = {"stage": 0, "done": False, "error": None, "running": False}
_state_lock = threading.Lock()


# ── pipeline runner ────────────────────────────────────────────────────────────

def _run_pipeline(topic: str):
    from content_generator import run_content_generation
    from crm_integration import run_distribution
    from performance_tracker import run_performance_tracking

    with _state_lock:
        _state.update({"stage": 1, "done": False, "error": None, "running": True})

    try:
        content_pkg = run_content_generation(topic)

        with _state_lock:
            _state["stage"] = 2

        dist = run_distribution(content_pkg, dry_run=True)

        with _state_lock:
            _state["stage"] = 3

        run_performance_tracking(dist["campaign_log"], dist["by_persona"])

        with _state_lock:
            _state["stage"] = 4
            _state["done"] = True
            _state["running"] = False

    except Exception as e:
        with _state_lock:
            _state["error"] = str(e)
            _state["done"] = True
            _state["running"] = False
        print(f"pipeline error: {e}")


# ── API routes ─────────────────────────────────────────────────────────────────

@app.route("/api/run", methods=["POST"])
def api_run():
    with _state_lock:
        if _state["running"]:
            return jsonify({"error": "pipeline already running"}), 409

    data = request.get_json() or {}
    topic = data.get("topic", "").strip()
    if not topic:
        return jsonify({"error": "topic required"}), 400

    # reset state before starting thread
    with _state_lock:
        _state.update({"stage": 0, "done": False, "error": None, "running": True})

    t = threading.Thread(target=_run_pipeline, args=(topic,), daemon=True)
    t.start()

    return jsonify({"status": "started", "topic": topic})


@app.route("/api/status")
def api_status():
    with _state_lock:
        return jsonify(dict(_state))


@app.route("/api/dashboard")
def api_dashboard():
    """Aggregate all saved data for the dashboard UI."""
    camp_dir = BASE_DIR / "data" / "campaigns"
    perf_dir = BASE_DIR / "data" / "performance"
    cont_dir = BASE_DIR / "data" / "content"

    campaigns = []

    if camp_dir.exists():
        for f in sorted(camp_dir.glob("camp_*.json")):
            try:
                camp = json.loads(f.read_text())
            except Exception:
                continue

            camp_id = camp.get("campaign_id", "")
            perf = {}
            pf = perf_dir / f"perf_{camp_id}_final.json"
            if pf.exists():
                try:
                    perf = json.loads(pf.read_text())
                except Exception:
                    pass

            overall = perf.get("overall", {})
            campaigns.append({
                "campaign_id":      camp_id,
                "blog_title":       camp.get("blog_title", ""),
                "send_date":        camp.get("send_date", ""),
                "total_recipients": overall.get("total_recipients", 0),
                "open_rate":        overall.get("open_rate", 0),
                "click_rate":       overall.get("click_rate", 0),
            })

    # aggregates
    total_r = sum(c["total_recipients"] for c in campaigns)
    avg_open  = sum(c["open_rate"]  for c in campaigns) / len(campaigns) if campaigns else 0
    avg_click = sum(c["click_rate"] for c in campaigns) / len(campaigns) if campaigns else 0

    # latest campaign details
    latest_personas = None
    latest_summary  = None
    latest_newsletters = None

    if campaigns:
        last_id = campaigns[-1]["campaign_id"]

        pf = perf_dir / f"perf_{last_id}_final.json"
        if pf.exists():
            latest_perf = json.loads(pf.read_text())
            latest_personas = latest_perf.get("personas")
            latest_summary  = latest_perf.get("ai_summary")

        # find latest content package
        if cont_dir.exists():
            pkgs = sorted(cont_dir.glob("package_*.json"))
            if pkgs:
                latest_pkg = json.loads(pkgs[-1].read_text())
                latest_newsletters = latest_pkg.get("newsletters")

    return jsonify({
        "total_campaigns":    len(campaigns),
        "total_recipients":   total_r,
        "avg_open_rate":      avg_open,
        "avg_click_rate":     avg_click,
        "campaigns":          campaigns,
        "latest_personas":    latest_personas,
        "latest_ai_summary":  latest_summary,
        "latest_newsletters": latest_newsletters,
    })


# ── dashboard HTML ─────────────────────────────────────────────────────────────

DASHBOARD = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>NovaMind — Content Pipeline</title>
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;600;700;800&family=DM+Mono:ital,wght@0,300;0,400;0,500;1,300&display=swap" rel="stylesheet">
<style>
:root {
  --bg:      #07070f;
  --surf:    #0f0f1e;
  --surf2:   #161628;
  --border:  #1e1e38;
  --accent:  #7c3aed;
  --acc2:    #a78bfa;
  --green:   #34d399;
  --amber:   #fbbf24;
  --red:     #f87171;
  --text:    #e2e8f0;
  --muted:   #64748b;
  --mono:    'DM Mono', monospace;
  --sans:    'Syne', sans-serif;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: var(--sans); min-height: 100vh; }
body::before {
  content: '';
  position: fixed; inset: 0; pointer-events: none; z-index: 0;
  background-image:
    linear-gradient(rgba(124,58,237,.03) 1px, transparent 1px),
    linear-gradient(90deg, rgba(124,58,237,.03) 1px, transparent 1px);
  background-size: 40px 40px;
}

.wrap { position: relative; z-index: 1; max-width: 1160px; margin: 0 auto; padding: 0 24px; }

header {
  border-bottom: 1px solid var(--border);
  background: rgba(7,7,15,.92);
  position: sticky; top: 0; z-index: 100;
  backdrop-filter: blur(10px);
}
.hdr { display: flex; align-items: center; justify-content: space-between; max-width: 1160px; margin: 0 auto; padding: 18px 24px; }
.logo { font-size: 18px; font-weight: 800; letter-spacing: 3px; background: linear-gradient(135deg, #a78bfa, #34d399); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.logo-sub { font-size: 11px; color: var(--muted); font-family: var(--mono); margin-top: 2px; }
.dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); box-shadow: 0 0 8px var(--green); animation: blink 2s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:.3} }

main { padding: 36px 0 80px; }

.label { font-family: var(--mono); font-size: 11px; color: var(--acc2); letter-spacing: 2px; text-transform: uppercase; margin-bottom: 14px; }

.gen-panel {
  background: var(--surf); border: 1px solid var(--border); border-radius: 14px;
  padding: 28px; margin-bottom: 36px; position: relative; overflow: hidden;
}
.gen-panel::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 2px; background: linear-gradient(90deg, var(--accent), var(--green)); }
.gen-title { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
.gen-sub { color: var(--muted); font-size: 13px; margin-bottom: 20px; }
.row { display: flex; gap: 10px; }
.tinput {
  flex: 1; background: var(--bg); border: 1px solid var(--border); border-radius: 8px;
  padding: 12px 16px; color: var(--text); font-family: var(--mono); font-size: 13px; outline: none;
  transition: border-color .2s;
}
.tinput:focus { border-color: var(--acc2); }
.tinput::placeholder { color: var(--muted); }
.btn { padding: 12px 24px; border-radius: 8px; border: none; cursor: pointer; font-family: var(--sans); font-weight: 700; font-size: 13px; transition: all .15s; white-space: nowrap; }
.btn-run { background: linear-gradient(135deg, var(--accent), #5b21b6); color: #fff; box-shadow: 0 4px 16px rgba(124,58,237,.3); }
.btn-run:hover { transform: translateY(-1px); box-shadow: 0 6px 20px rgba(124,58,237,.4); }
.btn-run:disabled { opacity: .5; cursor: not-allowed; transform: none; }

.progress { display: none; margin-top: 18px; background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 18px; }
.steps { display: flex; flex-direction: column; gap: 10px; }
.step { display: flex; align-items: center; gap: 10px; font-family: var(--mono); font-size: 12px; color: var(--muted); transition: color .3s; }
.step.active { color: var(--acc2); }
.step.done { color: var(--green); }
.si { width: 18px; text-align: center; }
@keyframes spin { to { transform: rotate(360deg); } }
.spin { display: inline-block; animation: spin 1s linear infinite; }

.stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 14px; margin-bottom: 32px; }
.sc { background: var(--surf); border: 1px solid var(--border); border-radius: 10px; padding: 18px 20px; transition: border-color .2s, transform .2s; }
.sc:hover { border-color: var(--accent); transform: translateY(-2px); }
.sc-label { font-family: var(--mono); font-size: 10px; color: var(--muted); letter-spacing: 1px; margin-bottom: 8px; }
.sc-val { font-size: 28px; font-weight: 800; }
.purple { color: var(--acc2); }
.green  { color: var(--green); }
.amber  { color: var(--amber); }

.two { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 28px; }
@media (max-width: 720px) { .two { grid-template-columns: 1fr; } }

.card { background: var(--surf); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; }
.ch { padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.ch-title { font-size: 14px; font-weight: 700; }
.ch-meta { font-family: var(--mono); font-size: 11px; color: var(--muted); }
.cb { padding: 18px; }

.clist { display: flex; flex-direction: column; gap: 10px; }
.ci { background: var(--surf2); border: 1px solid var(--border); border-radius: 8px; padding: 14px; transition: border-color .2s; }
.ci:hover { border-color: var(--accent); }
.ci-title { font-size: 13px; font-weight: 600; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ci-meta { font-family: var(--mono); font-size: 10px; color: var(--muted); margin-bottom: 8px; }
.ci-stats { display: flex; gap: 14px; }
.cs { font-family: var(--mono); font-size: 11px; }
.cs span { color: var(--acc2); }

.pr { margin-bottom: 18px; }
.pr-name { font-size: 12px; font-weight: 600; margin-bottom: 6px; }
.bars { display: flex; flex-direction: column; gap: 5px; }
.br { display: flex; align-items: center; gap: 8px; }
.bl { font-family: var(--mono); font-size: 10px; color: var(--muted); width: 44px; }
.bt { flex: 1; height: 5px; background: var(--border); border-radius: 3px; overflow: hidden; }
.bf { height: 100%; border-radius: 3px; transition: width .7s ease; }
.bf.o { background: var(--acc2); }
.bf.c { background: var(--green); }
.bv { font-family: var(--mono); font-size: 10px; color: var(--muted); width: 38px; text-align: right; }

.ai-box {
  background: var(--bg); border: 1px solid var(--border); border-left: 3px solid var(--accent);
  border-radius: 0 6px 6px 0; padding: 14px 16px; font-family: var(--mono); font-size: 12px;
  line-height: 1.75; color: #94a3b8; white-space: pre-wrap;
  max-height: 280px; overflow-y: auto;
}

.tabs { display: flex; gap: 6px; margin-bottom: 14px; flex-wrap: wrap; }
.tab { padding: 6px 14px; border-radius: 6px; border: 1px solid var(--border); background: transparent; color: var(--muted); font-family: var(--sans); font-size: 11px; font-weight: 600; cursor: pointer; transition: all .15s; }
.tab.on { border-color: var(--acc2); color: var(--acc2); background: rgba(167,139,250,.08); }
.nlc { display: none; }
.nlc.on { display: block; }
.nf { margin-bottom: 10px; }
.nfl { font-family: var(--mono); font-size: 10px; color: var(--muted); letter-spacing: 1px; margin-bottom: 3px; }
.nfv { font-size: 12px; line-height: 1.6; background: var(--bg); padding: 8px 10px; border-radius: 5px; }
.nfv.subj { font-weight: 700; }
.nfv.muted { color: var(--muted); }
.nfv.cta  { color: var(--acc2); font-weight: 700; }

.empty { text-align: center; padding: 36px; color: var(--muted); font-family: var(--mono); font-size: 12px; }

#toast {
  position: fixed; bottom: 20px; right: 20px;
  background: var(--surf2); border: 1px solid var(--accent); border-radius: 8px;
  padding: 12px 18px; font-family: var(--mono); font-size: 12px; color: var(--acc2);
  opacity: 0; transition: opacity .3s; z-index: 999; pointer-events: none;
}
#toast.show { opacity: 1; }
</style>
</head>
<body>

<header>
  <div class="hdr">
    <div>
      <div class="logo">NOVAMIND</div>
      <div class="logo-sub">content pipeline dashboard</div>
    </div>
    <div style="display:flex;align-items:center;gap:8px;">
      <div class="dot"></div>
      <span style="font-family:var(--mono);font-size:11px;color:var(--muted)">online</span>
    </div>
  </div>
</header>

<main>
<div class="wrap">

  <div class="gen-panel">
    <div class="label">pipeline control</div>
    <div class="gen-title">Run a new campaign</div>
    <div class="gen-sub">Enter a topic to generate a blog post, 3 persona newsletters, distribute via CRM, and get AI performance insights.</div>
    <div class="row">
      <input class="tinput" id="topicInput" type="text"
        placeholder="e.g. 5 AI tools every creative agency needs in 2025"
        value="How AI is changing creative agency workflows in 2025">
      <button class="btn btn-run" id="runBtn" onclick="runPipeline()">▶ Run Pipeline</button>
    </div>
    <div class="progress" id="prog">
      <div class="steps">
        <div class="step" id="s1"><span class="si">○</span> Stage 1 — generating blog post + 3 newsletter variants</div>
        <div class="step" id="s2"><span class="si">○</span> Stage 2 — syncing contacts + distributing via CRM</div>
        <div class="step" id="s3"><span class="si">○</span> Stage 3 — collecting engagement data + AI analysis</div>
        <div class="step" id="s4"><span class="si">○</span> Saving results</div>
      </div>
    </div>
  </div>

  <div class="label">overview</div>
  <div class="stats">
    <div class="sc"><div class="sc-label">CAMPAIGNS</div><div class="sc-val purple" id="stC">—</div></div>
    <div class="sc"><div class="sc-label">TOTAL RECIPIENTS</div><div class="sc-val" id="stR">—</div></div>
    <div class="sc"><div class="sc-label">AVG OPEN RATE</div><div class="sc-val green" id="stO">—</div></div>
    <div class="sc"><div class="sc-label">AVG CLICK RATE</div><div class="sc-val amber" id="stCl">—</div></div>
  </div>

  <div class="two">
    <div class="card">
      <div class="ch"><div class="ch-title">Campaign History</div><div class="ch-meta" id="campCount">0 campaigns</div></div>
      <div class="cb"><div class="clist" id="campList"><div class="empty">no campaigns yet</div></div></div>
    </div>
    <div class="card">
      <div class="ch"><div class="ch-title">Persona Performance</div><div class="ch-meta">latest campaign</div></div>
      <div class="cb" id="personaPanel"><div class="empty">run a campaign first</div></div>
    </div>
  </div>

  <div class="two">
    <div class="card">
      <div class="ch"><div class="ch-title">AI Performance Analysis</div></div>
      <div class="cb"><div class="ai-box" id="aiBox">run a campaign to see AI-generated insights.</div></div>
    </div>
    <div class="card">
      <div class="ch"><div class="ch-title">Newsletter Viewer</div></div>
      <div class="cb">
        <div class="tabs" id="nlTabs"></div>
        <div id="nlContent"><div class="empty">run a campaign to preview newsletters</div></div>
      </div>
    </div>
  </div>

</div>
</main>

<div id="toast"></div>

<script>
async function loadDash() {
  try {
    const d = await fetch('/api/dashboard').then(r => r.json());
    render(d);
  } catch(e) { /* first load before any data */ }
}

function render(d) {
  document.getElementById('stC').textContent  = d.total_campaigns;
  document.getElementById('stR').textContent  = d.total_recipients.toLocaleString();
  document.getElementById('stO').textContent  = d.avg_open_rate  ? pct(d.avg_open_rate)  : '—';
  document.getElementById('stCl').textContent = d.avg_click_rate ? pct(d.avg_click_rate) : '—';
  document.getElementById('campCount').textContent = `${d.total_campaigns} campaign${d.total_campaigns !== 1 ? 's' : ''}`;

  const list = document.getElementById('campList');
  if (!d.campaigns.length) {
    list.innerHTML = '<div class="empty">no campaigns yet</div>';
  } else {
    list.innerHTML = d.campaigns.map(c => `
      <div class="ci">
        <div class="ci-title">${c.blog_title}</div>
        <div class="ci-meta">${c.campaign_id} · ${fmt(c.send_date)}</div>
        <div class="ci-stats">
          <div class="cs">Recipients: <span>${c.total_recipients}</span></div>
          <div class="cs">Open: <span>${pct(c.open_rate)}</span></div>
          <div class="cs">Click: <span>${pct(c.click_rate)}</span></div>
        </div>
      </div>`).join('');
  }

  if (d.latest_personas) {
    document.getElementById('personaPanel').innerHTML =
      Object.entries(d.latest_personas).map(([k,p]) => `
        <div class="pr">
          <div class="pr-name">${p.persona_name}</div>
          <div class="bars">
            <div class="br">
              <div class="bl">Open</div>
              <div class="bt"><div class="bf o" style="width:${p.open_rate*100}%"></div></div>
              <div class="bv">${pct(p.open_rate)}</div>
            </div>
            <div class="br">
              <div class="bl">Click</div>
              <div class="bt"><div class="bf c" style="width:${Math.min(p.click_rate*300,100)}%"></div></div>
              <div class="bv">${pct(p.click_rate)}</div>
            </div>
          </div>
        </div>`).join('');
  }

  if (d.latest_ai_summary) {
    document.getElementById('aiBox').textContent = d.latest_ai_summary;
  }

  if (d.latest_newsletters) {
    const personas = Object.keys(d.latest_newsletters);
    document.getElementById('nlTabs').innerHTML = personas.map((k,i) => `
      <button class="tab ${i===0?'on':''}" onclick="showNL('${k}',this)">
        ${d.latest_newsletters[k].persona_name}
      </button>`).join('');
    document.getElementById('nlContent').innerHTML = personas.map((k,i) => {
      const nl = d.latest_newsletters[k];
      return `<div class="nlc ${i===0?'on':''}" id="nl_${k}">
        <div class="nf"><div class="nfl">SUBJECT (A)</div><div class="nfv subj">${nl.subject_line||''}</div></div>
        <div class="nf"><div class="nfl">SUBJECT (B variant)</div><div class="nfv subj" style="color:var(--amber)">${nl.subject_line_b||'—'}</div></div>
        <div class="nf"><div class="nfl">PREVIEW TEXT</div><div class="nfv muted">${nl.preview_text||''}</div></div>
        <div class="nf"><div class="nfl">BODY</div><div class="nfv">${nl.body||''}</div></div>
        <div class="nf"><div class="nfl">CTA</div><div class="nfv cta">${nl.cta_text||''}</div></div>
      </div>`;
    }).join('');
  }
}

function showNL(k, btn) {
  document.querySelectorAll('.nlc').forEach(el => el.classList.remove('on'));
  document.querySelectorAll('.tab').forEach(el => el.classList.remove('on'));
  document.getElementById('nl_'+k)?.classList.add('on');
  btn.classList.add('on');
}

async function runPipeline() {
  const topic = document.getElementById('topicInput').value.trim();
  if (!topic) { toast('enter a topic first'); return; }

  const btn = document.getElementById('runBtn');
  btn.disabled = true;
  btn.textContent = '⏳ running...';
  document.getElementById('prog').style.display = 'block';
  setStep('s1', 'active');

  try {
    await fetch('/api/run', {
      method: 'POST',
      headers: {'Content-Type':'application/json'},
      body: JSON.stringify({topic})
    });
  } catch(e) {
    toast('error starting pipeline'); btn.disabled=false; btn.textContent='▶ Run Pipeline'; return;
  }

  // poll status
  const poll = setInterval(async () => {
    let st;
    try { st = await fetch('/api/status').then(r => r.json()); } catch(e) { return; }

    if (st.stage >= 1) setStep('s1', st.stage > 1 ? 'done' : 'active');
    if (st.stage >= 2) setStep('s2', st.stage > 2 ? 'done' : 'active');
    if (st.stage >= 3) setStep('s3', st.stage > 3 ? 'done' : 'active');
    if (st.stage >= 4) setStep('s4', 'done');

    if (st.done) {
      clearInterval(poll);
      btn.disabled = false;
      btn.textContent = '▶ Run Pipeline';
      if (st.error) {
        toast('pipeline error: ' + st.error);
      } else {
        await loadDash();
        toast('✓ campaign complete');
      }
    }
  }, 1500);
}

function setStep(id, state) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = 'step ' + state;
  const icons = { active: '<span class="spin">◌</span>', done: '✓' };
  el.querySelector('.si').innerHTML = icons[state] || '○';
}

function pct(v) { return v ? (v*100).toFixed(1)+'%' : '—'; }
function fmt(s) { try { return new Date(s).toLocaleDateString(); } catch(e) { return s; } }
function toast(msg) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.classList.add('show');
  setTimeout(() => t.classList.remove('show'), 3000);
}

loadDash();
setInterval(loadDash, 20000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(DASHBOARD)


if __name__ == "__main__":
    # check API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("error: ANTHROPIC_API_KEY not set")
        print("run: export ANTHROPIC_API_KEY=your_key_here")
        sys.exit(1)

    print("\nNovaMind dashboard starting...")
    print("open http://localhost:5000\n")
    app.run(debug=False, port=5000)
