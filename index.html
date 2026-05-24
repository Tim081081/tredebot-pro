<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta name="theme-color" content="#0d0d0d">
<meta name="apple-mobile-web-app-capable" content="yes">
<title>TradeBot Pro</title>
<style>
*{box-sizing:border-box;margin:0;padding:0;-webkit-tap-highlight-color:transparent}
:root{--bg:#0a0a0a;--s1:#141414;--s2:#1c1c1c;--b:#2a2a2a;--gold:#f0b429;--green:#22c55e;--red:#ef4444;--text:#e8e8e8;--muted:#666;--r:12px}
body{font-family:'Segoe UI',sans-serif;background:var(--bg);color:var(--text);min-height:100vh}
header{position:sticky;top:0;z-index:100;background:rgba(10,10,10,.95);backdrop-filter:blur(16px);border-bottom:1px solid var(--b);padding:12px 16px;display:flex;align-items:center;justify-content:space-between}
.logo{display:flex;align-items:center;gap:10px}
.logo-mark{width:32px;height:32px;background:var(--gold);border-radius:8px;display:flex;align-items:center;justify-content:center;font-weight:700;font-size:12px;color:#000}
.logo-text{font-size:18px;font-weight:800}
.logo-text span{color:var(--gold)}
.header-right{display:flex;gap:8px;align-items:center}
.badge-time{font-size:11px;color:var(--muted);background:var(--s2);padding:4px 10px;border-radius:20px;border:1px solid var(--b)}
#refresh-btn{width:32px;height:32px;border-radius:8px;background:var(--s2);border:1px solid var(--b);color:var(--gold);cursor:pointer;font-size:16px;display:flex;align-items:center;justify-content:center}
#refresh-btn.spin{animation:spin .8s linear infinite}
nav{display:flex;background:var(--s1);border-bottom:1px solid var(--b)}
.tab{flex:1;padding:12px 4px;text-align:center;font-size:11px;font-weight:600;color:var(--muted);cursor:pointer;border-bottom:2px solid transparent;transition:all .2s}
.tab.active{color:var(--gold);border-bottom-color:var(--gold)}
.tab-icon{font-size:18px;display:block;margin-bottom:2px}
main{padding:14px;max-width:800px;margin:0 auto}
.page{display:none}.page.active{display:block}
.stats-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:14px}
.stat-card{background:var(--s1);border:1px solid var(--b);border-radius:var(--r);padding:12px;text-align:center}
.stat-value{font-size:18px;font-weight:700;font-family:monospace}
.stat-label{font-size:9px;color:var(--muted);margin-top:3px;text-transform:uppercase;letter-spacing:.5px}
.gold{color:var(--gold)}.pos{color:var(--green)}.neg{color:var(--red)}
.section-title{font-size:12px;font-weight:700;color:var(--gold);letter-spacing:.5px;margin:16px 0 8px;display:flex;align-items:center;gap:6px}
.signal-card{background:var(--s2);border:1px solid var(--b);border-radius:var(--r);padding:14px;margin-bottom:10px;border-left:3px solid var(--b)}
.signal-card.buy-card{border-left-color:var(--green)}
.signal-card.sell-card{border-left-color:var(--red)}
.signal-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:10px}
.signal-name{font-size:16px;font-weight:700}
.signal-ticker{font-size:11px;color:var(--muted);margin-top:2px;font-family:monospace}
.badge{padding:4px 10px;border-radius:20px;font-size:11px;font-weight:700;letter-spacing:.5px}
.badge-buy{background:rgba(34,197,94,.15);color:var(--green);border:1px solid rgba(34,197,94,.3)}
.badge-sell{background:rgba(239,68,68,.15);color:var(--red);border:1px solid rgba(239,68,68,.3)}
.prices{display:grid;grid-template-columns:repeat(3,1fr);gap:6px;margin-bottom:10px}
.price-item{text-align:center}
.price-label{font-size:9px;color:var(--muted);text-transform:uppercase}
.price-value{font-size:13px;font-weight:700;font-family:monospace;margin-top:2px}
.strength-bar{height:4px;background:var(--b);border-radius:2px;overflow:hidden;margin-bottom:8px}
.strength-fill{height:100%;border-radius:2px;transition:width .8s}
.signal-tags{font-size:11px;color:var(--muted);margin-bottom:10px}
.signal-tags span{display:inline-block;background:var(--b);padding:2px 8px;border-radius:8px;margin:2px 2px 0 0}
.signal-actions{display:flex;flex-direction:column;gap:8px}
.amount-row{display:flex;gap:8px;align-items:center}
.amount-input{flex:1;padding:8px 10px;border-radius:8px;background:var(--b);border:1px solid #444;color:var(--text);font-size:13px;font-family:monospace}
.btn{padding:10px;border-radius:8px;font-size:13px;font-weight:600;border:none;cursor:pointer;width:100%;transition:opacity .2s}
.btn:active{opacity:.8}
.btn-buy{background:var(--green);color:#000}
.btn-sell{background:var(--red);color:#fff}
.btn-secondary{background:var(--b);color:var(--text)}
.pos-card{background:var(--s2);border:1px solid var(--b);border-radius:var(--r);padding:14px;margin-bottom:10px}
.pos-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.pos-name{font-size:14px;font-weight:700}
.pos-details{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;font-size:11px;margin-top:8px}
.pd-label{color:var(--muted)}
.pd-value{font-family:monospace;font-weight:600;font-size:12px}
.trade-row{display:flex;justify-content:space-between;align-items:center;padding:10px 0;border-bottom:1px solid var(--b)}
.trade-row:last-child{border:none}
.empty{text-align:center;padding:32px 16px;color:var(--muted);font-size:14px}
.empty-icon{font-size:40px;margin-bottom:10px}
.card{background:var(--s1);border:1px solid var(--b);border-radius:var(--r);padding:16px;margin-bottom:12px}
.setting-row{display:flex;justify-content:space-between;align-items:center;padding:12px 0;border-bottom:1px solid var(--b)}
.setting-row:last-child{border:none}
.setting-label{font-size:14px;font-weight:600}
.setting-sub{font-size:11px;color:var(--muted);margin-top:2px}
.toggle{width:44px;height:24px;border-radius:12px;background:var(--b);border:none;cursor:pointer;position:relative;transition:background .2s}
.toggle.on{background:var(--gold)}
.toggle::after{content:'';position:absolute;top:3px;left:3px;width:18px;height:18px;border-radius:50%;background:white;transition:transform .2s}
.toggle.on::after{transform:translateX(20px)}
.progress-container{background:var(--s1);border:1px solid var(--b);border-radius:var(--r);padding:20px;margin-bottom:12px;text-align:center}
.progress-bar-bg{background:var(--b);border-radius:4px;height:8px;margin:12px 0}
.progress-bar-fill{background:var(--gold);height:8px;border-radius:4px;transition:width .5s}
.exit-card{border-radius:var(--r);padding:14px;margin-bottom:10px}
.exit-card.urgent{background:rgba(239,68,68,.1);border:1px solid rgba(239,68,68,.4)}
.exit-card.warn{background:rgba(240,180,41,.1);border:1px solid rgba(240,180,41,.4)}
@keyframes spin{to{transform:rotate(360deg)}}
</style>
</head>
<body>
<header>
  <div class="logo">
    <div class="logo-mark">TB</div>
    <div class="logo-text">Trade<span>Bot</span></div>
  </div>
  <div class="header-right">
    <div class="badge-time" id="clock">--:--</div>
    <button id="refresh-btn" onclick="doRefresh()">⟳</button>
  </div>
</header>

<nav>
  <div class="tab active" onclick="showTab('signals')"><span class="tab-icon">📡</span>Signale</div>
  <div class="tab" onclick="showTab('portfolio')"><span class="tab-icon">💼</span>Portfolio</div>
  <div class="tab" onclick="showTab('history')"><span class="tab-icon">📋</span>Historie</div>
  <div class="tab" onclick="showTab('settings')"><span class="tab-icon">⚙️</span>Einstellungen</div>
</nav>

<main>
  <!-- SIGNALE -->
  <div class="page active" id="page-signals">
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-value gold" id="s-analyzed">—</div><div class="stat-label">Analysiert</div></div>
      <div class="stat-card"><div class="stat-value" id="s-found">—</div><div class="stat-label">Signale</div></div>
      <div class="stat-card"><div class="stat-value gold" id="s-top">—</div><div class="stat-label">Top Signal</div></div>
    </div>
    <div id="progress-area"></div>
    <div class="section-title">📡 Handelssignale</div>
    <div id="signals-list"></div>
  </div>

  <!-- PORTFOLIO -->
  <div class="page" id="page-portfolio">
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-value" id="p-value">—</div><div class="stat-label">Gesamtwert</div></div>
      <div class="stat-card"><div class="stat-value" id="p-pnl">—</div><div class="stat-label">P&L</div></div>
      <div class="stat-card"><div class="stat-value" id="p-cash">—</div><div class="stat-label">Cash</div></div>
    </div>
    <div class="stats-grid">
      <div class="stat-card"><div class="stat-value" id="p-trades">—</div><div class="stat-label">Trades</div></div>
      <div class="stat-card"><div class="stat-value pos" id="p-wr">—</div><div class="stat-label">Win Rate</div></div>
      <div class="stat-card"><div class="stat-value" id="p-open">—</div><div class="stat-label">Offen</div></div>
    </div>
    <div class="section-title">🚨 Exit-Signale</div>
    <div id="exit-list"></div>
    <div class="section-title">📊 Offene Positionen</div>
    <div id="positions-list"></div>
  </div>

  <!-- HISTORIE -->
  <div class="page" id="page-history">
    <div class="section-title">📋 Abgeschlossene Trades</div>
    <div class="card"><div id="history-list"></div></div>
  </div>

  <!-- EINSTELLUNGEN -->
  <div class="page" id="page-settings">
    <div class="section-title">⚙️ Einstellungen</div>
    <div class="card">
      <div class="setting-row">
        <div><div class="setting-label">E-Mail-Benachrichtigungen</div><div class="setting-sub">dieter_kammer@gmx.de</div></div>
        <button class="toggle on" id="tog-email" onclick="this.classList.toggle('on')"></button>
      </div>
      <div class="setting-row">
        <div><div class="setting-label">Paper Trading</div><div class="setting-sub">Virtuelles Kapital: 10.000€</div></div>
        <button class="toggle on" id="tog-paper" onclick="this.classList.toggle('on')"></button>
      </div>
    </div>
    <div class="section-title">📈 Analyseparameter</div>
    <div class="card">
      <div class="setting-row" style="flex-direction:column;align-items:flex-start;gap:10px;">
        <div style="display:flex;justify-content:space-between;width:100%">
          <div><div class="setting-label">Min. Signalstärke</div><div class="setting-sub">Filtert schwache Signale heraus</div></div>
          <span class="gold" style="font-family:monospace;font-weight:700" id="str-display">60</span>
        </div>
        <input type="range" id="str-slider" min="20" max="80" value="60" step="5"
          style="width:100%;accent-color:#f0b429"
          oninput="document.getElementById('str-display').textContent=this.value"
          onchange="saveStrength(this.value)">
        <div style="display:flex;justify-content:space-between;width:100%;font-size:10px;color:var(--muted)">
          <span>20 Viele</span><span>50 Mittel</span><span>80 Wenige</span>
        </div>
      </div>
      <div class="setting-row">
        <div><div class="setting-label">Analysierte Werte</div><div class="setting-sub">DAX (42) + Euro Stoxx 50 (50)</div></div>
        <span class="gold" style="font-family:monospace">~80</span>
      </div>
    </div>
    <div class="section-title">ℹ️ Info</div>
    <div class="card" style="font-size:12px;color:var(--muted);line-height:1.7">
      Indikatoren: RSI (14), MACD (12/26/9), Bollinger Bands (20), Stochastik (14/3), EMA 20/50, ATR (14)<br><br>
      Datenquelle: Yahoo Finance (kostenlos)<br><br>
      ⚠️ Keine Anlageberatung. Handeln Sie auf eigenes Risiko.
    </div>
  </div>
</main>

<script>
const API = '';
let pollTimer = null;

// ── Tabs ──────────────────────────────────────────────────────────────────────
function showTab(name) {
  document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  const tabs = ['signals','portfolio','history','settings'];
  document.querySelectorAll('.tab')[tabs.indexOf(name)].classList.add('active');
  document.getElementById('page-'+name).classList.add('active');
  if (name === 'portfolio' || name === 'history') loadPortfolio();
}

// ── Clock ─────────────────────────────────────────────────────────────────────
function tick() {
  const n = new Date();
  document.getElementById('clock').textContent =
    n.toLocaleTimeString('de-DE',{hour:'2-digit',minute:'2-digit'});
}
setInterval(tick, 10000); tick();

// ── Toast ─────────────────────────────────────────────────────────────────────
function toast(msg, type='') {
  let t = document.getElementById('toast');
  if (!t) { t = document.createElement('div'); t.id='toast'; document.body.appendChild(t);
    t.style.cssText='position:fixed;bottom:20px;left:50%;transform:translateX(-50%) translateY(80px);background:#1c1c1c;border:1px solid #2a2a2a;border-radius:24px;padding:10px 20px;font-size:13px;z-index:999;transition:transform .3s;max-width:90vw;text-align:center'; }
  t.textContent = msg;
  t.style.borderColor = type==='ok' ? '#22c55e' : type==='err' ? '#ef4444' : '#2a2a2a';
  t.style.color = type==='ok' ? '#22c55e' : type==='err' ? '#ef4444' : '#e8e8e8';
  t.style.transform = 'translateX(-50%) translateY(0)';
  setTimeout(() => t.style.transform='translateX(-50%) translateY(80px)', 3000);
}

// ── Signals ───────────────────────────────────────────────────────────────────
function fmt2(n) { return n==null?'—':n.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/,'.'); }

async function loadSignals() {
  try {
    const res = await fetch(`${API}/api/signals`);
    const d = await res.json();
    const status = d.status || 'done';
    const prog = d.progress || 0;

    document.getElementById('s-analyzed').textContent = d.total_analyzed || '…';
    document.getElementById('s-found').textContent = d.signals_found || (status==='done'?'0':'…');
    document.getElementById('s-top').textContent = d.top_signals?.length > 0 ? d.top_signals[0].strength+'/100' : '—';

    // Progress bar
    const pa = document.getElementById('progress-area');
    if (status === 'loading' || status === 'running') {
      pa.innerHTML = `<div class="progress-container">
        <div style="font-size:13px;margin-bottom:4px;">⏳ Märkte werden analysiert…</div>
        <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:${prog}%"></div></div>
        <div style="font-size:12px;color:var(--muted)">${prog}% abgeschlossen – automatische Aktualisierung</div>
      </div>`;
      if (!pollTimer) pollTimer = setInterval(loadSignals, 12000);
    } else {
      pa.innerHTML = '';
      if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    }

    renderSignals(d.top_signals || []);
  } catch(e) {
    document.getElementById('signals-list').innerHTML = '<div class="empty"><div class="empty-icon">⚠️</div>Backend nicht erreichbar</div>';
  }
}

function renderSignals(signals) {
  const c = document.getElementById('signals-list');
  if (!signals.length) {
    c.innerHTML = '<div class="empty"><div class="empty-icon">🔍</div>Keine starken Signale aktuell</div>';
    return;
  }
  c.innerHTML = signals.map((s,i) => `
    <div class="signal-card ${s.direction==='BUY'?'buy-card':'sell-card'}">
      <div class="signal-header">
        <div><div class="signal-name">${s.name}</div><div class="signal-ticker">${s.ticker}</div></div>
        <span class="badge ${s.direction==='BUY'?'badge-buy':'badge-sell'}">${s.direction==='BUY'?'▲ LONG':'▼ SHORT'}</span>
      </div>
      <div class="prices">
        <div class="price-item"><div class="price-label">Kurs</div><div class="price-value">${fmt2(s.price)}</div></div>
        <div class="price-item"><div class="price-label">Take Profit</div><div class="price-value pos">${fmt2(s.take_profit)}</div></div>
        <div class="price-item"><div class="price-label">Stop Loss</div><div class="price-value neg">${fmt2(s.stop_loss)}</div></div>
      </div>
      <div class="strength-bar"><div class="strength-fill" style="width:${s.strength}%;background:${s.direction==='BUY'?'var(--green)':'var(--red)'}"></div></div>
      <div style="font-size:11px;color:var(--muted);margin-bottom:8px">Stärke: <b>${s.strength}/100</b> · RSI: ${s.rsi}</div>
      <div class="signal-tags">${(s.signals||[]).map(r=>`<span>${r}</span>`).join('')}</div>
      <div class="signal-actions">
        <div class="amount-row">
          <span style="font-size:12px;color:var(--muted)">Betrag:</span>
          <input type="number" id="amt${i}" class="amount-input" value="500" min="10" max="10000" step="50">
          <span style="font-size:12px;color:var(--muted)">€</span>
        </div>
        <button class="btn ${s.direction==='BUY'?'btn-buy':'btn-sell'}"
          onclick='openTrade(${JSON.stringify(s).replace(/'/g,"&#39;")}, document.getElementById("amt${i}").value)'>
          ${s.direction==='BUY'?'▲ Long eröffnen':'▼ Short eröffnen'}
        </button>
      </div>
    </div>`).join('');
}

async function doRefresh() {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('spin');
  try {
    await fetch(`${API}/api/signals/refresh`, {method:'POST'});
    document.getElementById('progress-area').innerHTML = `<div class="progress-container">
      <div style="font-size:13px">⏳ Neue Analyse gestartet…</div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" style="width:0%"></div></div>
    </div>`;
    document.getElementById('signals-list').innerHTML = '';
    if (!pollTimer) pollTimer = setInterval(loadSignals, 12000);
    toast('Analyse gestartet', 'ok');
  } catch(e) { toast('Fehler', 'err'); }
  btn.classList.remove('spin');
}

// ── Trade ─────────────────────────────────────────────────────────────────────
async function openTrade(signal, amount) {
  try {
    const res = await fetch(`${API}/api/trade/open`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({...signal, invest_amount: parseFloat(amount)||0})
    });
    const d = await res.json();
    if (res.ok) toast(`✅ Trade eröffnet: ${signal.name}`, 'ok');
    else toast(`❌ ${d.detail}`, 'err');
  } catch(e) { toast('Fehler', 'err'); }
}

// ── Portfolio ─────────────────────────────────────────────────────────────────
async function loadPortfolio() {
  try {
    const [pr, er] = await Promise.all([
      fetch(`${API}/api/portfolio`),
      fetch(`${API}/api/exit-signals`)
    ]);
    const pd = await pr.json();
    const ed = await er.json();
    const s = pd.stats || {};
    const pnl = s.total_pnl || 0;

    document.getElementById('p-value').textContent = fmt2(s.total_value)+'€';
    const pnlEl = document.getElementById('p-pnl');
    pnlEl.textContent = (pnl>=0?'+':'')+fmt2(pnl)+'€';
    pnlEl.className = 'stat-value '+(pnl>=0?'pos':'neg');
    document.getElementById('p-cash').textContent = fmt2(s.cash)+'€';
    document.getElementById('p-trades').textContent = s.total_trades||0;
    document.getElementById('p-wr').textContent = (s.win_rate||0)+'%';
    document.getElementById('p-open').textContent = s.open_positions||0;

    renderExitSignals(ed.exit_signals||[]);
    renderPositions(pd.portfolio?.positions||[]);
    renderHistory(pd.portfolio?.closed_trades||[]);
  } catch(e) {}
}

function renderExitSignals(signals) {
  const c = document.getElementById('exit-list');
  if (!signals.length) { c.innerHTML = '<div style="font-size:12px;color:var(--muted);padding:4px 0 12px">Keine Exit-Signale für offene Positionen.</div>'; return; }
  c.innerHTML = signals.map(s => {
    const col = s.urgency==='urgent'?'var(--red)':'var(--gold)';
    return `<div class="exit-card ${s.urgency}">
      <div style="display:flex;justify-content:space-between;margin-bottom:8px">
        <div><b>${s.name}</b> · ${s.direction}</div>
        <span style="color:${s.pnl_pct>=0?'var(--green)':'var(--red)'};font-family:monospace">${s.pnl_pct>=0?'+':''}${s.pnl_pct}%</span>
      </div>
      ${s.exit_reasons.map(r=>`<div style="font-size:12px;color:${col};margin-bottom:3px">${r}</div>`).join('')}
      <button class="btn btn-secondary" style="margin-top:10px" onclick="closeTrade('${s.trade_id}',${s.current_price})">
        ${s.recommendation}: Schließen zu ${s.current_price}€
      </button>
    </div>`;
  }).join('');
}

function renderPositions(positions) {
  const c = document.getElementById('positions-list');
  if (!positions.length) { c.innerHTML = '<div class="empty"><div class="empty-icon">📭</div>Keine offenen Positionen</div>'; return; }
  c.innerHTML = positions.map(p => {
    const pnl = p.unrealized_pnl||0;
    return `<div class="pos-card">
      <div class="pos-header">
        <div>
          <div class="pos-name">${p.name}</div>
          <span class="badge ${p.direction==='BUY'?'badge-buy':'badge-sell'}" style="font-size:10px;padding:2px 8px">${p.direction==='BUY'?'▲ LONG':'▼ SHORT'}</span>
        </div>
        <div style="text-align:right">
          <div style="font-family:monospace;font-weight:700;color:${pnl>=0?'var(--green)':'var(--red)'}">${pnl>=0?'+':''}${fmt2(pnl)}€</div>
          <div style="font-size:11px;color:var(--muted)">${p.unrealized_pnl_pct>=0?'+':''}${p.unrealized_pnl_pct||0}%</div>
        </div>
      </div>
      <div class="pos-details">
        <div><div class="pd-label">Einstieg</div><div class="pd-value">${fmt2(p.entry_price)}</div></div>
        <div><div class="pd-label">Aktuell</div><div class="pd-value">${fmt2(p.current_price)}</div></div>
        <div><div class="pd-label">Stop Loss</div><div class="pd-value neg">${fmt2(p.stop_loss)}</div></div>
        <div><div class="pd-label">Take Profit</div><div class="pd-value pos">${fmt2(p.take_profit)}</div></div>
      </div>
      <button class="btn btn-secondary" style="margin-top:10px;font-size:12px" onclick="closeTrade('${p.id}',${p.current_price})">
        Position schließen (${fmt2(p.current_price)}€)
      </button>
    </div>`;
  }).join('');
}

function renderHistory(trades) {
  const c = document.getElementById('history-list');
  if (!trades.length) { c.innerHTML = '<div class="empty" style="padding:20px"><div class="empty-icon">📋</div>Noch keine Trades</div>'; return; }
  c.innerHTML = [...trades].reverse().map(t => {
    const pnl = t.pnl||0;
    const date = new Date(t.closed).toLocaleDateString('de-DE',{day:'2-digit',month:'2-digit',year:'2-digit'});
    return `<div class="trade-row">
      <div><div style="font-weight:600">${t.name}</div><div style="font-size:11px;color:var(--muted)">${t.direction} · ${date} · ${t.id}</div></div>
      <div style="text-align:right"><div style="font-family:monospace;font-weight:700;color:${pnl>=0?'var(--green)':'var(--red)'}">${pnl>=0?'+':''}${fmt2(pnl)}€</div><div style="font-size:11px;color:var(--muted)">${t.status}</div></div>
    </div>`;
  }).join('');
}

async function closeTrade(id, price) {
  if (!confirm(`Position ${id} zu ${price}€ schließen?`)) return;
  try {
    const res = await fetch(`${API}/api/trade/close`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({trade_id:id, close_price:price})
    });
    const d = await res.json();
    if (res.ok) { toast(`Geschlossen: ${d.trade?.pnl>=0?'+':''}${fmt2(d.trade?.pnl)}€`, d.trade?.pnl>=0?'ok':'err'); loadPortfolio(); }
    else toast(d.detail, 'err');
  } catch(e) { toast('Fehler', 'err'); }
}

// ── Settings ──────────────────────────────────────────────────────────────────
async function saveStrength(val) {
  try {
    await fetch(`${API}/api/settings`, {
      method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({min_strength: parseInt(val)})
    });
    toast(`Signalstärke: ${val} – Analyse wird neu gestartet`, 'ok');
    setTimeout(() => { loadSignals(); if (!pollTimer) pollTimer = setInterval(loadSignals, 12000); }, 1000);
  } catch(e) { toast('Fehler beim Speichern', 'err'); }
}

async function loadStrength() {
  try {
    const res = await fetch(`${API}/api/settings`);
    const d = await res.json();
    const v = d.min_strength||60;
    document.getElementById('str-slider').value = v;
    document.getElementById('str-display').textContent = v;
  } catch(e) {}
}

// ── Init ──────────────────────────────────────────────────────────────────────
loadSignals();
loadStrength();
setInterval(() => { if (document.getElementById('page-signals').classList.contains('active')) loadSignals(); }, 300000);
</script>
</body>
</html>
