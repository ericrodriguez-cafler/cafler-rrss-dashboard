#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cafler - Dashboard de insights de redes sociales (Meta: Facebook + Instagram).
Autocontenido: solo librería estándar (urllib). Genera dashboard.html.

Token de Meta (larga duración):
  - variable de entorno META_TOKEN, o
  - fichero en META_TOKEN_PATH (por defecto ./meta_token.txt)

Salida: DASHBOARD_OUT (por defecto ./dashboard.html)
"""
import os
import sys
import json
import urllib.request
import urllib.parse
from datetime import datetime, timezone, timedelta

BASE = "https://graph.facebook.com/v21.0"
N = 12  # publicaciones recientes por cuenta


def read_token():
    t = os.environ.get("META_TOKEN")
    if t:
        return t.strip()
    path = os.environ.get("META_TOKEN_PATH", "meta_token.txt")
    with open(path, encoding="utf-8") as f:
        return f.read().strip()


def api(path, params):
    url = BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "cafler-dashboard"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def api_safe(path, params):
    try:
        return api(path, params)
    except Exception:
        return None


def truncate(s, n=180):
    if not s:
        return ""
    s = s.strip()
    return s if len(s) <= n else s[:n] + "..."


def fetch(token):
    fb, ig = [], []
    accs = api("/me/accounts", {
        "fields": "name,id,fan_count,access_token,instagram_business_account{id,username,followers_count}",
        "limit": 100, "access_token": token,
    })
    for p in accs.get("data", []):
        pt = p.get("access_token")

        # ---------- FACEBOOK ----------
        fbposts = []
        posts = api_safe("/%s/published_posts" % p["id"], {
            "fields": "id,created_time,message,permalink_url,shares", "limit": N, "access_token": pt,
        })
        for post in (posts or {}).get("data", []):
            reactions = comments = clicks = None
            eng = api_safe("/%s" % post["id"], {
                "fields": "reactions.summary(true),comments.summary(true)", "access_token": pt,
            })
            if eng:
                try:
                    reactions = int(eng["reactions"]["summary"]["total_count"])
                except Exception:
                    pass
                try:
                    comments = int(eng["comments"]["summary"]["total_count"])
                except Exception:
                    pass
            ins = api_safe("/%s/insights" % post["id"], {"metric": "post_clicks", "access_token": pt})
            if ins:
                for m in ins.get("data", []):
                    if m.get("name") == "post_clicks":
                        clicks = m["values"][0]["value"]
            shares = post.get("shares", {}).get("count", 0) if post.get("shares") else 0
            fbposts.append({
                "id": post["id"], "date": post.get("created_time"),
                "text": truncate(post.get("message")), "permalink": post.get("permalink_url"),
                "reactions": reactions, "comments": comments, "shares": shares,
                "reach": None, "impressions": None, "clicks": clicks,
            })
        fb.append({"account": p.get("name"), "id": p.get("id"),
                   "followers": p.get("fan_count"), "posts": fbposts})

        # ---------- INSTAGRAM ----------
        iga = p.get("instagram_business_account")
        if iga:
            igposts = []
            media = api_safe("/%s/media" % iga["id"], {
                "fields": "id,timestamp,media_type,caption,permalink,like_count,comments_count",
                "limit": N, "access_token": pt,
            })
            for m in (media or {}).get("data", []):
                reach = saved = inter = None
                ins = api_safe("/%s/insights" % m["id"], {
                    "metric": "reach,saved,total_interactions", "access_token": pt,
                })
                if ins:
                    for x in ins.get("data", []):
                        nm = x.get("name")
                        if nm == "reach":
                            reach = x["values"][0]["value"]
                        elif nm == "saved":
                            saved = x["values"][0]["value"]
                        elif nm == "total_interactions":
                            inter = x["values"][0]["value"]
                igposts.append({
                    "id": m["id"], "date": m.get("timestamp"), "type": m.get("media_type"),
                    "text": truncate(m.get("caption")), "permalink": m.get("permalink"),
                    "likes": m.get("like_count"), "comments": m.get("comments_count"),
                    "reach": reach, "saved": saved, "interactions": inter,
                })
            ig.append({"account": "@" + iga.get("username", ""), "id": iga.get("id"),
                       "followers": iga.get("followers_count"), "posts": igposts})
    return fb, ig


def now_madrid_str():
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("Europe/Madrid"))
    except Exception:
        # Fallback aproximado (CEST, +2) si no hay tz database
        now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=2)))
    return "%02d %s %d, %02d:%02d" % (now.day, meses[now.month - 1], now.year, now.hour, now.minute)


def build_model(fb, ig):
    platforms = {}
    if fb:
        platforms["facebook"] = {"accounts": fb}
    if ig:
        platforms["instagram"] = {"accounts": ig}
    platforms["youtube"] = {"status": "pending", "label": "Fase 2",
        "note": "2 canales (@CaflerAI, @CaflerES) — conectar YouTube Data + Analytics API."}
    platforms["linkedin"] = {"status": "pending", "label": "Fase 3",
        "note": "8 perfiles (Global, ES, LATAM, UK, FR, ASIA, PT, US) — requiere aprobación de app en LinkedIn Marketing API."}
    platforms["tiktok"] = {"status": "pending", "label": "Fase 4",
        "note": "@cafler.ai — requiere aprobación de TikTok Business API."}
    return {"generated_at": now_madrid_str(), "platforms": platforms}


TEMPLATE = '''<style>
  :root {
    --bg: #f7f9fa;
    --surface: #ffffff;
    --surface-2: #eef3f4;
    --border: #dde5e7;
    --ink: #0e1417;
    --ink-2: #45585e;
    --ink-3: #7d9198;
    --road: #1f9bd4;
    --teal: #2bc0be;
    --green: #3fd8a6;
    --grad: linear-gradient(90deg, #1f9bd4 0%, #2bc0be 50%, #3fd8a6 100%);
    --good: #1aa87d;
    --warn: #c98a1a;
    --shadow: 0 1px 2px rgba(14,20,23,.04), 0 4px 16px rgba(14,20,23,.05);
    --radius: 14px;
    --fs-mono: ui-monospace, "SF Mono", "Cascadia Code", Menlo, Consolas, monospace;
    --fs-sans: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0b1113; --surface: #121a1d; --surface-2: #18242a; --border: #223138;
      --ink: #eef4f5; --ink-2: #a7bcc2; --ink-3: #6f868d;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 6px 22px rgba(0,0,0,.35);
    }
  }
  :root[data-theme="light"] {
    --bg: #f7f9fa; --surface: #ffffff; --surface-2: #eef3f4; --border: #dde5e7;
    --ink: #0e1417; --ink-2: #45585e; --ink-3: #7d9198;
    --shadow: 0 1px 2px rgba(14,20,23,.04), 0 4px 16px rgba(14,20,23,.05);
  }
  :root[data-theme="dark"] {
    --bg: #0b1113; --surface: #121a1d; --surface-2: #18242a; --border: #223138;
    --ink: #eef4f5; --ink-2: #a7bcc2; --ink-3: #6f868d;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 6px 22px rgba(0,0,0,.35);
  }

  * { box-sizing: border-box; }
  body { margin: 0; }
  .wrap {
    font-family: var(--fs-sans);
    background: var(--bg);
    color: var(--ink);
    min-height: 100vh;
    padding: clamp(20px, 4vw, 48px);
    -webkit-font-smoothing: antialiased;
  }
  .inner { max-width: 1180px; margin: 0 auto; }

  header.top { display: flex; flex-wrap: wrap; align-items: flex-end; justify-content: space-between; gap: 20px; margin-bottom: 8px; }
  .brandrow { display: flex; align-items: center; gap: 12px; }
  .spark { font-size: 22px; background: var(--grad); -webkit-background-clip: text; background-clip: text; color: transparent; }
  h1 { font-size: clamp(22px, 3vw, 30px); font-weight: 700; letter-spacing: -.02em; margin: 0; line-height: 1.1; }
  .eyebrow { text-transform: uppercase; letter-spacing: .14em; font-size: 11px; font-weight: 600; color: var(--ink-3); }
  .meta-line { font-size: 13px; color: var(--ink-2); text-align: right; }
  .meta-line strong { color: var(--ink); font-variant-numeric: tabular-nums; }
  .autobadge { display: inline-flex; align-items: center; gap: 6px; margin-top: 6px; font-size: 12px; color: var(--ink-2); background: var(--surface-2); border: 1px solid var(--border); padding: 4px 10px; border-radius: 999px; }
  .autobadge::before { content: ""; width: 7px; height: 7px; border-radius: 50%; background: var(--green); box-shadow: 0 0 0 3px color-mix(in srgb, var(--green) 25%, transparent); }
  .gradline { height: 3px; background: var(--grad); border-radius: 3px; margin: 22px 0 26px; }

  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 30px; }
  @media (max-width: 720px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 18px 18px 16px; box-shadow: var(--shadow); position: relative; overflow: hidden; }
  .kpi .lab { font-size: 12px; color: var(--ink-2); text-transform: uppercase; letter-spacing: .08em; font-weight: 600; }
  .kpi .val { font-size: clamp(26px, 4vw, 34px); font-weight: 700; letter-spacing: -.02em; margin-top: 8px; font-variant-numeric: tabular-nums; line-height: 1; }
  .kpi .sub { font-size: 12px; color: var(--ink-3); margin-top: 7px; }
  .kpi::after { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--grad); }

  .tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 22px; }
  .tab { font-family: inherit; font-size: 13px; font-weight: 600; color: var(--ink-2); background: var(--surface); border: 1px solid var(--border); padding: 8px 14px; border-radius: 999px; cursor: pointer; display: inline-flex; align-items: center; gap: 8px; transition: border-color .15s, color .15s; }
  .tab:hover { color: var(--ink); border-color: var(--ink-3); }
  .tab[aria-selected="true"] { color: #06232b; background: var(--grad); border-color: transparent; }
  .tab .dot { width: 9px; height: 9px; border-radius: 50%; }
  .tab .cnt { font-variant-numeric: tabular-nums; opacity: .7; font-weight: 500; }
  .tab:focus-visible { outline: 2px solid var(--road); outline-offset: 2px; }

  .acct { margin-bottom: 30px; }
  .acct-head { display: flex; align-items: center; gap: 10px; margin: 0 0 14px; }
  .acct-head .dot { width: 11px; height: 11px; border-radius: 50%; flex: none; }
  .acct-head h3 { font-size: 15px; font-weight: 700; margin: 0; letter-spacing: -.01em; }
  .acct-head .plat { font-size: 12px; color: var(--ink-3); }
  .acct-head .foll { margin-left: auto; font-size: 12px; color: var(--ink-2); font-variant-numeric: tabular-nums; }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(268px, 1fr)); gap: 14px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 12px; transition: transform .12s ease, border-color .12s; }
  .card:hover { transform: translateY(-2px); border-color: var(--ink-3); }
  .card .crow { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .badge { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; font-weight: 600; color: var(--ink-2); }
  .badge .dot { width: 8px; height: 8px; border-radius: 50%; }
  .type-pill { font-size: 10px; text-transform: uppercase; letter-spacing: .07em; color: var(--ink-3); border: 1px solid var(--border); border-radius: 6px; padding: 2px 7px; }
  .date { font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
  .card .text { font-size: 13.5px; line-height: 1.5; color: var(--ink); margin: 0; min-height: 40px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .card .text.empty { color: var(--ink-3); font-style: italic; }
  .metrics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
  .chip { display: inline-flex; align-items: baseline; gap: 5px; font-size: 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 4px 8px; }
  .chip b { font-weight: 700; font-variant-numeric: tabular-nums; }
  .chip.null { color: var(--ink-3); }
  .chip.null b { color: var(--ink-3); }
  .chip .k { color: var(--ink-2); font-size: 11px; }
  .card .foot { display: flex; align-items: center; justify-content: space-between; }
  .card a.view { font-size: 12px; font-weight: 600; color: var(--road); text-decoration: none; }
  .card a.view:hover { text-decoration: underline; }
  .eng { font-size: 12px; color: var(--ink-2); }
  .eng b { color: var(--ink); font-variant-numeric: tabular-nums; }

  .pending { background: var(--surface); border: 1px dashed var(--border); border-radius: var(--radius); padding: 18px; display: flex; align-items: center; gap: 14px; margin-bottom: 14px; }
  .pending .dot { width: 12px; height: 12px; border-radius: 50%; flex: none; }
  .pending .pt { font-weight: 700; font-size: 14px; }
  .pending .pd { font-size: 13px; color: var(--ink-2); }
  .pending .status { margin-left: auto; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, transparent); padding: 4px 10px; border-radius: 999px; }

  .note { font-size: 12.5px; color: var(--ink-2); background: var(--surface-2); border: 1px solid var(--border); border-left: 3px solid var(--road); border-radius: 8px; padding: 11px 14px; margin-bottom: 24px; line-height: 1.5; }
  footer { margin-top: 36px; padding-top: 18px; border-top: 1px solid var(--border); font-size: 12px; color: var(--ink-3); display: flex; flex-wrap: wrap; gap: 6px 16px; justify-content: space-between; }
  .hidden { display: none !important; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
  <div class="inner">
    <header class="top">
      <div>
        <div class="brandrow"><span class="spark">✦</span><span class="eyebrow">Cafler · Social Insights</span></div>
        <h1>Rendimiento de redes sociales</h1>
        <div class="autobadge" id="autobadge">Actualización semanal automática · lunes</div>
      </div>
      <div class="meta-line">
        Última actualización<br><strong id="genat">—</strong>
      </div>
    </header>
    <div class="gradline"></div>

    <div id="permnote" class="note hidden"></div>

    <div class="kpis" id="kpis"></div>

    <div class="tabs" id="tabs"></div>

    <div id="content"></div>

    <footer>
      <span>Cafler · sistema operativo AI-native del aftermarket</span>
      <span id="src">Fuente: Meta Graph API</span>
    </footer>
  </div>
</div>

<script>
  const DATA = __DATA_JSON__;

  const PLAT = {
    linkedin:  { label: "LinkedIn",  color: "#0a66c2" },
    facebook:  { label: "Facebook",  color: "#1877f2" },
    instagram: { label: "Instagram", color: "#e1306c" },
    youtube:   { label: "YouTube",   color: "#ff0000" },
    tiktok:    { label: "TikTok",    color: "#25f4ee" },
  };
  const ORDER = ["linkedin","facebook","instagram","youtube","tiktok"];

  const nf = new Intl.NumberFormat("es-ES");
  function fmtDate(iso){
    if(!iso) return "";
    const d = new Date(iso);
    if(isNaN(d)) return "";
    return d.toLocaleDateString("es-ES", { day:"2-digit", month:"short", year:"numeric" });
  }

  function normPosts(platKey, accounts){
    const out = [];
    (accounts||[]).forEach(a => {
      (a.posts||[]).forEach(p => {
        const likes = (platKey === "instagram") ? p.likes : p.reactions;
        const reach = p.reach;
        const eng = [likes, p.comments, p.shares, p.saved]
          .filter(v => typeof v === "number").reduce((s,v)=>s+v,0);
        out.push({
          plat: platKey, account: a.account, date: p.date, text: p.text||"",
          type: p.type || (platKey==="facebook" ? "post" : ""),
          permalink: p.permalink,
          likes, comments: p.comments, shares: p.shares, saved: p.saved,
          reach, impressions: p.impressions, clicks: p.clicks, eng,
        });
      });
    });
    return out;
  }

  const model = {};
  let anyInsightsMissing = false;
  ORDER.forEach(k => {
    const node = DATA.platforms[k];
    if(!node) return;
    if(node.status === "pending"){ model[k] = { pending: node }; return; }
    const posts = normPosts(k, node.accounts);
    posts.sort((a,b)=> new Date(b.date) - new Date(a.date));
    if(k === "instagram" && posts.length && posts.every(p => p.reach == null)) anyInsightsMissing = true;
    model[k] = { accounts: node.accounts, posts };
  });

  const allPosts = ORDER.flatMap(k => (model[k] && model[k].posts) ? model[k].posts : []);
  const connectedProfiles = ORDER.reduce((s,k)=> s + ((model[k]&&model[k].accounts)? model[k].accounts.length : 0), 0);
  const totalInteractions = allPosts.reduce((s,p)=> s + (p.eng||0), 0);
  const reachVals = allPosts.map(p=>p.reach).filter(v=>typeof v==="number");
  const totalReach = reachVals.length ? reachVals.reduce((s,v)=>s+v,0) : null;

  const kpiEl = document.getElementById("kpis");
  const kpiData = [
    { lab:"Perfiles conectados", val: connectedProfiles, sub: ORDER.filter(k=>model[k]&&model[k].accounts).map(k=>PLAT[k].label).join(" · ") },
    { lab:"Publicaciones", val: allPosts.length, sub:"últimas por canal" },
    { lab:"Interacciones", val: totalInteractions, sub:"likes + coment. + comp. + guardados" },
    { lab:"Alcance total", val: totalReach, sub: totalReach===null ? "pendiente de permisos" : "personas alcanzadas · Instagram" },
  ];
  kpiEl.innerHTML = kpiData.map(k => `
    <div class="kpi">
      <div class="lab">${k.lab}</div>
      <div class="val">${k.val===null ? "—" : nf.format(k.val)}</div>
      <div class="sub">${k.sub}</div>
    </div>`).join("");

  if(anyInsightsMissing){
    const n = document.getElementById("permnote");
    n.classList.remove("hidden");
    n.innerHTML = "<strong>Alcance e impresiones pendientes.</strong> El token de Meta aún no tiene los permisos <code>read_insights</code>, <code>pages_read_user_content</code> e <code>instagram_manage_insights</code>.";
  }

  const tabsEl = document.getElementById("tabs");
  const tabDefs = [{ key:"all", label:"Todas" }].concat(
    ORDER.filter(k=>model[k]).map(k => ({ key:k, label: PLAT[k].label,
      count: model[k].posts ? model[k].posts.length : null,
      color: PLAT[k].color, pending: !!model[k].pending }))
  );
  let active = "all";
  tabsEl.innerHTML = tabDefs.map(t => `
    <button class="tab" role="tab" data-key="${t.key}" aria-selected="${t.key==='all'}">
      ${t.color ? `<span class="dot" style="background:${t.color}"></span>` : ""}
      ${t.label}${(t.count!=null)?` <span class="cnt">${t.count}</span>`:""}
    </button>`).join("");

  function chip(label, val){
    const isNull = (val === null || val === undefined);
    return `<span class="chip${isNull?' null':''}"><b>${isNull?'—':nf.format(val)}</b><span class="k">${label}</span></span>`;
  }
  function postCard(p){
    let chips;
    if(p.plat === "instagram"){
      chips = [ chip("likes", p.likes), chip("coment.", p.comments), chip("guard.", p.saved), chip("alcance", p.reach) ];
    } else if(p.plat === "facebook"){
      chips = [ chip("reacc.", p.likes), chip("coment.", p.comments), chip("comp.", p.shares), chip("clics", p.clicks) ];
    } else {
      chips = [ chip("likes", p.likes), chip("coment.", p.comments), chip("alcance", p.reach) ];
    }
    return `
      <div class="card">
        <div class="crow">
          <span class="badge"><span class="dot" style="background:${PLAT[p.plat].color}"></span>${p.account}</span>
          ${p.type ? `<span class="type-pill">${p.type}</span>` : ""}
        </div>
        <div class="date">${fmtDate(p.date)}</div>
        <p class="text${p.text?'':' empty'}">${p.text ? escapeHtml(p.text) : "Sin texto · contenido visual"}</p>
        <div class="metrics">${chips.join("")}</div>
        <div class="foot">
          <span class="eng">Interacción <b>${nf.format(p.eng||0)}</b></span>
          ${p.permalink ? `<a class="view" href="${p.permalink}" target="_blank" rel="noopener">Ver publicación →</a>` : ""}
        </div>
      </div>`;
  }
  function escapeHtml(s){ return s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  function accountGroup(platKey){
    const m = model[platKey];
    return (m.accounts||[]).map(a => {
      const posts = m.posts.filter(p => p.account === a.account);
      if(!posts.length) return "";
      return `
        <div class="acct">
          <div class="acct-head">
            <span class="dot" style="background:${PLAT[platKey].color}"></span>
            <h3>${a.account}</h3><span class="plat">${PLAT[platKey].label}</span>
            ${(a.followers!=null)?`<span class="foll">${nf.format(a.followers)} seguidores</span>`:""}
          </div>
          <div class="grid">${posts.map(postCard).join("")}</div>
        </div>`;
    }).join("");
  }

  function pendingCard(platKey){
    const p = model[platKey].pending;
    return `<div class="pending">
        <span class="dot" style="background:${PLAT[platKey].color}"></span>
        <div><div class="pt">${PLAT[platKey].label}</div><div class="pd">${p.note||""}</div></div>
        <span class="status">${p.label||"Pendiente"}</span>
      </div>`;
  }

  function render(){
    const c = document.getElementById("content");
    const keys = active === "all" ? ORDER.filter(k=>model[k]) : [active];
    let html = "";
    keys.forEach(k => { if(model[k].pending){ html += pendingCard(k); } });
    keys.forEach(k => { if(model[k].posts && model[k].posts.length){ html += accountGroup(k); } });
    if(!html) html = `<div class="note">Sin publicaciones para este canal todavía.</div>`;
    c.innerHTML = html;
  }

  tabsEl.addEventListener("click", e => {
    const b = e.target.closest(".tab"); if(!b) return;
    active = b.dataset.key;
    [...tabsEl.children].forEach(t => t.setAttribute("aria-selected", t.dataset.key===active));
    render();
  });

  document.getElementById("genat").textContent = DATA.generated_at || "—";
  render();
</script>'''


def main():
    token = read_token()
    fb, ig = fetch(token)
    model = build_model(fb, ig)
    data_json = json.dumps(model, ensure_ascii=False)
    html = TEMPLATE.replace("__DATA_JSON__", data_json)
    out = os.environ.get("DASHBOARD_OUT", "dashboard.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    fbc = sum(len(a["posts"]) for a in fb)
    igc = sum(len(a["posts"]) for a in ig)
    print("OK -> %s | FB %d paginas (%d posts) | IG %d cuentas (%d posts)" % (out, len(fb), fbc, len(ig), igc))


if __name__ == "__main__":
    main()
