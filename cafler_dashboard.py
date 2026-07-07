#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cafler - Dashboard de insights de redes sociales (Meta: Facebook + Instagram).
Autocontenido: solo librería estándar (urllib). Genera dashboard.html + summary.json.

Token de Meta (larga duración):
  - variable de entorno META_TOKEN, o
  - fichero en META_TOKEN_PATH (por defecto ./meta_token.txt)

Salida: DASHBOARD_OUT (por defecto ./dashboard.html). summary.json se escribe al lado.
"""
import os
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
        # Facebook no expone alcance por página ni por post en la API (deprecado por Meta).
        fb.append({"account": p.get("name"), "id": p.get("id"),
                   "followers": p.get("fan_count"), "week_reach": None, "posts": fbposts})

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
            # Alcance de CUENTA IG (últimos 7 días).
            ig_reach = None
            iins = api_safe("/%s/insights" % iga["id"], {"metric": "reach", "period": "week", "access_token": pt})
            if iins:
                try:
                    ig_reach = iins["data"][0]["values"][-1]["value"]
                except Exception:
                    pass
            ig.append({"account": "@" + iga.get("username", ""), "id": iga.get("id"),
                       "followers": iga.get("followers_count"), "week_reach": ig_reach, "posts": igposts})
    return fb, ig


# ---------- YOUTUBE (API key pública, sin OAuth) ----------
YT_BASE = "https://www.googleapis.com/youtube/v3"
YT_HANDLES = ["CaflerAI", "CaflerES"]  # sin @


def yt_api_safe(path, params):
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        return None
    params = dict(params)
    params["key"] = key
    url = YT_BASE + path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "cafler-dashboard"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception:
        return None


def fetch_youtube():
    if not os.environ.get("YOUTUBE_API_KEY"):
        return []
    channels = []
    for handle in YT_HANDLES:
        ch = yt_api_safe("/channels", {"part": "snippet,statistics,contentDetails", "forHandle": handle})
        if not ch or not ch.get("items"):
            continue
        it = ch["items"][0]
        try:
            uploads = it["contentDetails"]["relatedPlaylists"]["uploads"]
        except Exception:
            uploads = None
        subs = it.get("statistics", {}).get("subscriberCount")
        posts = []
        if uploads:
            pl = yt_api_safe("/playlistItems", {"part": "contentDetails", "playlistId": uploads, "maxResults": N})
            vids = [x["contentDetails"]["videoId"] for x in (pl or {}).get("items", []) if x.get("contentDetails")]
            if vids:
                vd = yt_api_safe("/videos", {"part": "snippet,statistics", "id": ",".join(vids)})
                for v in (vd or {}).get("items", []):
                    st = v.get("statistics", {})
                    def _int(x):
                        try:
                            return int(x)
                        except Exception:
                            return None
                    posts.append({
                        "id": v["id"], "date": v["snippet"].get("publishedAt"),
                        "type": "video", "text": truncate(v["snippet"].get("title")),
                        "permalink": "https://www.youtube.com/watch?v=" + v["id"],
                        "views": _int(st.get("viewCount")) or 0,
                        "likes": _int(st.get("likeCount")),
                        "comments": _int(st.get("commentCount")) or 0,
                    })
        channels.append({"account": "@" + handle, "id": it.get("id"),
                         "followers": _safe_int(subs), "week_reach": None, "posts": posts})
    return channels


def _safe_int(x):
    try:
        return int(x)
    except Exception:
        return None


def now_madrid():
    try:
        from zoneinfo import ZoneInfo
        return datetime.now(ZoneInfo("Europe/Madrid"))
    except Exception:
        return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=2)))


def now_madrid_str():
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    now = now_madrid()
    return "%02d %s %d, %02d:%02d" % (now.day, meses[now.month - 1], now.year, now.hour, now.minute)


def build_model(fb, ig, yt=None):
    platforms = {}
    if fb:
        platforms["facebook"] = {"accounts": fb}
    if ig:
        platforms["instagram"] = {"accounts": ig}
    if yt:
        platforms["youtube"] = {"accounts": yt}
    else:
        platforms["youtube"] = {"status": "pending", "label": "Fase 2",
            "note": "2 canales (@CaflerAI, @CaflerES) - conectar YouTube Data API."}
    platforms["linkedin"] = {"status": "pending", "label": "Fase 3",
        "note": "8 perfiles (Global, ES, LATAM, UK, FR, ASIA, PT, US) - requiere aprobacion de app en LinkedIn Marketing API."}
    platforms["tiktok"] = {"status": "pending", "label": "Fase 4",
        "note": "@cafler.ai - requiere aprobacion de TikTok Business API."}
    return {"generated_at": now_madrid_str(), "platforms": platforms}


def parse_dt(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%S%z")
    except Exception:
        return None


def build_summary(fb, ig, yt=None):
    now = now_madrid()
    cutoff = now - timedelta(days=7)
    rows = []
    for plat, accts in (("facebook", fb), ("instagram", ig), ("youtube", yt or [])):
        for a in accts:
            for p in a.get("posts", []):
                likes = p.get("reactions") if plat == "facebook" else p.get("likes")
                eng = sum(v for v in [likes, p.get("comments"), p.get("shares"), p.get("saved")] if isinstance(v, int))
                rows.append({"plat": plat, "account": a["account"], "dt": parse_dt(p.get("date")),
                             "reach": p.get("reach"), "eng": eng,
                             "permalink": p.get("permalink"), "text": p.get("text", "")})
    week = [r for r in rows if r["dt"] and r["dt"] >= cutoff]
    reach_pool = [r for r in (week or rows) if isinstance(r["reach"], int)]
    top = max(reach_pool, key=lambda r: r["reach"]) if reach_pool else None
    # Alcance general = alcance de cuenta (7 días) sumando FB (página) + IG (cuenta)
    week_reach = 0
    for accts in (fb, ig):
        for a in accts:
            if isinstance(a.get("week_reach"), int):
                week_reach += a["week_reach"]
    return {
        "generated_at": now_madrid_str(),
        "week_posts": len(week),
        "week_interactions": sum(r["eng"] for r in week),
        "week_reach": week_reach,
        "total_posts": len(rows),
        "top_post": ({"account": top["account"], "reach": top["reach"],
                      "permalink": top["permalink"], "text": top["text"][:120]} if top else None),
    }


TEMPLATE = '''<style>
  :root {
    --bg: #f7f9fa; --surface: #ffffff; --surface-2: #eef3f4; --border: #dde5e7;
    --ink: #0e1417; --ink-2: #45585e; --ink-3: #7d9198;
    --road: #1f9bd4; --teal: #2bc0be; --green: #3fd8a6;
    --grad: linear-gradient(90deg, #1f9bd4 0%, #2bc0be 50%, #3fd8a6 100%);
    --warn: #c98a1a;
    --shadow: 0 1px 2px rgba(14,20,23,.04), 0 4px 16px rgba(14,20,23,.05);
    --radius: 14px;
    --fs-sans: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  @media (prefers-color-scheme: dark) {
    :root { --bg: #0b1113; --surface: #121a1d; --surface-2: #18242a; --border: #223138;
      --ink: #eef4f5; --ink-2: #a7bcc2; --ink-3: #6f868d;
      --shadow: 0 1px 2px rgba(0,0,0,.3), 0 6px 22px rgba(0,0,0,.35); }
  }
  :root[data-theme="light"] { --bg: #f7f9fa; --surface: #ffffff; --surface-2: #eef3f4; --border: #dde5e7;
    --ink: #0e1417; --ink-2: #45585e; --ink-3: #7d9198;
    --shadow: 0 1px 2px rgba(14,20,23,.04), 0 4px 16px rgba(14,20,23,.05); }
  :root[data-theme="dark"] { --bg: #0b1113; --surface: #121a1d; --surface-2: #18242a; --border: #223138;
    --ink: #eef4f5; --ink-2: #a7bcc2; --ink-3: #6f868d;
    --shadow: 0 1px 2px rgba(0,0,0,.3), 0 6px 22px rgba(0,0,0,.35); }

  * { box-sizing: border-box; }
  body { margin: 0; }
  .wrap { font-family: var(--fs-sans); background: var(--bg); color: var(--ink); min-height: 100vh; padding: clamp(20px, 4vw, 48px); -webkit-font-smoothing: antialiased; }
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
  .gradline { height: 3px; background: var(--grad); border-radius: 3px; margin: 22px 0 22px; }

  .scope { font-size: 12px; color: var(--ink-3); margin: 0 0 14px; }
  .scope b { color: var(--ink-2); }

  .kpis { display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 26px; }
  @media (max-width: 720px) { .kpis { grid-template-columns: repeat(2, 1fr); } }
  .kpi { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px 16px 14px; box-shadow: var(--shadow); position: relative; overflow: hidden; }
  .kpi .lab { font-size: 11.5px; color: var(--ink-2); text-transform: uppercase; letter-spacing: .07em; font-weight: 600; }
  .kpi .val { font-size: clamp(24px, 3.6vw, 32px); font-weight: 700; letter-spacing: -.02em; margin-top: 6px; font-variant-numeric: tabular-nums; line-height: 1; }
  .kpi .sub { font-size: 11.5px; color: var(--ink-3); margin-top: 6px; }
  .kpi::after { content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--grad); }

  .filters { display: flex; flex-direction: column; gap: 8px; margin-bottom: 22px; }
  .filterrow { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
  .filterrow .flabel { font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .08em; color: var(--ink-3); width: 62px; flex: none; }
  .chip-btn { font-family: inherit; font-size: 13px; font-weight: 600; color: var(--ink-2); background: var(--surface); border: 1px solid var(--border); padding: 7px 13px; border-radius: 999px; cursor: pointer; display: inline-flex; align-items: center; gap: 7px; transition: border-color .15s, color .15s; }
  .chip-btn:hover { color: var(--ink); border-color: var(--ink-3); }
  .chip-btn[aria-selected="true"] { color: #06232b; background: var(--grad); border-color: transparent; }
  .chip-btn .cnt { font-variant-numeric: tabular-nums; opacity: .7; font-weight: 500; }
  .chip-btn .ic { width: 15px; height: 15px; display: block; }
  .chip-btn .fl { font-size: 14px; line-height: 1; }
  .chip-btn:focus-visible { outline: 2px solid var(--road); outline-offset: 2px; }

  .acct { margin-bottom: 26px; }
  .acct-head { display: flex; align-items: center; gap: 9px; margin: 0 0 12px; }
  .acct-head .ic { width: 18px; height: 18px; flex: none; }
  .acct-head h3 { font-size: 15px; font-weight: 700; margin: 0; letter-spacing: -.01em; }
  .acct-head .fl { font-size: 15px; }
  .acct-head .foll { margin-left: auto; font-size: 12px; color: var(--ink-2); font-variant-numeric: tabular-nums; }

  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(268px, 1fr)); gap: 14px; }
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius); padding: 16px; box-shadow: var(--shadow); display: flex; flex-direction: column; gap: 11px; transition: transform .12s ease, border-color .12s; }
  .card:hover { transform: translateY(-2px); border-color: var(--ink-3); }
  .card .crow { display: flex; align-items: center; gap: 8px; }
  .card .ic { width: 18px; height: 18px; flex: none; }
  .card .acc { font-size: 12px; font-weight: 700; color: var(--ink); }
  .card .fl { font-size: 15px; margin-left: 2px; }
  .type-pill { margin-left: auto; font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--ink-3); border: 1px solid var(--border); border-radius: 6px; padding: 2px 7px; }
  .date { font-size: 12px; color: var(--ink-3); font-variant-numeric: tabular-nums; }
  .card .text { font-size: 13.5px; line-height: 1.5; color: var(--ink); margin: 0; min-height: 40px; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .card .text.empty { color: var(--ink-3); font-style: italic; }
  .metrics { display: flex; flex-wrap: wrap; gap: 6px; margin-top: auto; }
  .chip { display: inline-flex; align-items: baseline; gap: 5px; font-size: 12px; background: var(--surface-2); border: 1px solid var(--border); border-radius: 8px; padding: 4px 8px; }
  .chip b { font-weight: 700; font-variant-numeric: tabular-nums; }
  .chip.null, .chip.null b { color: var(--ink-3); }
  .chip .k { color: var(--ink-2); font-size: 11px; }
  .card .foot { display: flex; align-items: center; justify-content: space-between; }
  .card a.view { font-size: 12px; font-weight: 600; color: var(--road); text-decoration: none; }
  .card a.view:hover { text-decoration: underline; }
  .eng { font-size: 12px; color: var(--ink-2); }
  .eng b { color: var(--ink); font-variant-numeric: tabular-nums; }

  .pending { background: var(--surface); border: 1px dashed var(--border); border-radius: var(--radius); padding: 16px; display: flex; align-items: center; gap: 13px; margin-bottom: 12px; }
  .pending .ic { width: 20px; height: 20px; flex: none; }
  .pending .pt { font-weight: 700; font-size: 14px; }
  .pending .pd { font-size: 12.5px; color: var(--ink-2); }
  .pending .status { margin-left: auto; font-size: 11px; font-weight: 600; text-transform: uppercase; letter-spacing: .06em; color: var(--warn); background: color-mix(in srgb, var(--warn) 12%, transparent); padding: 4px 10px; border-radius: 999px; }

  .note { font-size: 12.5px; color: var(--ink-2); background: var(--surface-2); border: 1px solid var(--border); border-left: 3px solid var(--road); border-radius: 8px; padding: 11px 14px; margin-bottom: 24px; line-height: 1.5; }
  footer { margin-top: 34px; padding-top: 18px; border-top: 1px solid var(--border); font-size: 12px; color: var(--ink-3); display: flex; flex-wrap: wrap; gap: 6px 16px; justify-content: space-between; }
  .hidden { display: none !important; }
  @media (prefers-reduced-motion: reduce) { * { transition: none !important; } }
</style>

<div class="wrap">
  <div class="inner">
    <header class="top">
      <div>
        <div class="brandrow"><span class="spark">✦</span><span class="eyebrow">Cafler · Social Insights</span></div>
        <h1>Rendimiento de redes sociales</h1>
        <div class="autobadge">Actualización semanal automática · lunes</div>
      </div>
      <div class="meta-line">Última actualización<br><strong id="genat">—</strong></div>
    </header>
    <div class="gradline"></div>

    <div id="permnote" class="note hidden"></div>
    <p class="scope" id="scope"></p>
    <div class="kpis" id="kpis"></div>
    <div class="filters" id="filters"></div>
    <div id="content"></div>

    <footer>
      <span>Cafler · sistema operativo AI-native del aftermarket</span>
      <span>Fuente: Meta Graph API</span>
    </footer>
  </div>
</div>

<script>
  const DATA = __DATA_JSON__;

  // ---- Iconos de red (SVG inline, reconstruidos) ----
  const ICON = {
    facebook: '<svg class="ic" viewBox="0 0 24 24"><circle cx="12" cy="12" r="11" fill="#1877f2"/><path d="M13.4 8.6h1.8V6.1s-1-.16-2-.16c-2.03 0-3.1 1.24-3.1 3.2v1.36H8v2.45h2.1V20h2.6v-6.05h1.95l.36-2.45h-2.3V9.4c0-.6.3-.8.9-.8Z" fill="#fff"/></svg>',
    instagram: '<svg class="ic" viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="6" fill="#e1306c"/><circle cx="12" cy="12" r="4.1" fill="none" stroke="#fff" stroke-width="1.8"/><circle cx="17.1" cy="6.9" r="1.2" fill="#fff"/></svg>',
    linkedin: '<svg class="ic" viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="4" fill="#0a66c2"/><text x="12" y="16.6" font-size="11" font-weight="700" fill="#fff" text-anchor="middle" font-family="Arial, sans-serif">in</text></svg>',
    youtube: '<svg class="ic" viewBox="0 0 24 24"><rect x="1.5" y="5" width="21" height="14" rx="4.5" fill="#ff0000"/><path d="M10 8.6l6 3.4-6 3.4z" fill="#fff"/></svg>',
    tiktok: '<svg class="ic" viewBox="0 0 24 24"><rect x="2" y="2" width="20" height="20" rx="6" fill="#111"/><text x="12" y="16.4" font-size="12" fill="#25f4ee" text-anchor="middle" font-family="Arial, sans-serif">♪</text></svg>',
  };

  const PLAT = {
    linkedin:  { label: "LinkedIn" },
    facebook:  { label: "Facebook" },
    instagram: { label: "Instagram" },
    youtube:   { label: "YouTube" },
    tiktok:    { label: "TikTok" },
  };
  const ORDER = ["linkedin","facebook","instagram","youtube","tiktok"];

  // ---- Regiones ----
  const REGIONS = {
    es:{label:"España", flag:"🇪🇸"}, latam:{label:"LATAM", flag:"🌎"}, uk:{label:"UK", flag:"🇬🇧"},
    fr:{label:"Francia", flag:"🇫🇷"}, asia:{label:"Asia", flag:"🌏"}, us:{label:"US", flag:"🇺🇸"},
    pt:{label:"Portugal", flag:"🇵🇹"}, global:{label:"Global", flag:"🌐"},
  };
  function regionKey(account){
    const s = (account||"").toLowerCase();
    if (s.includes("latam")) return "latam";
    if (s.includes("france") || s.includes("français")) return "fr";
    if (s.includes("亞洲") || s.includes("asia")) return "asia";
    if (/\buk\b/.test(s) || s.includes("-uk")) return "uk";
    if (s.includes("cafleres") || /\bes\b/.test(s)) return "es";
    if (/\bus\b/.test(s) || s.includes("-us")) return "us";
    if (/\bpt\b/.test(s)) return "pt";
    if (s.includes(".ai") || s.includes("cafler ai") || s.includes("global")) return "global";
    return "global";
  }

  const nf = new Intl.NumberFormat("es-ES");
  function fmtDate(iso){ if(!iso) return ""; const d=new Date(iso); if(isNaN(d)) return ""; return d.toLocaleDateString("es-ES",{day:"2-digit",month:"short",year:"numeric"}); }
  function escapeHtml(s){ return (s||"").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
  const WEEK_MS = 7*24*60*60*1000;
  const NOW = Date.now();

  // ---- Aplanar posts con red + región ----
  function normPosts(platKey, accounts){
    const out = [];
    (accounts||[]).forEach(a => {
      const reg = regionKey(a.account);
      (a.posts||[]).forEach(p => {
        const likes = (platKey === "facebook") ? p.reactions : p.likes;
        const eng = [likes, p.comments, p.shares, p.saved].filter(v => typeof v === "number").reduce((s,v)=>s+v,0);
        const t = new Date(p.date).getTime();
        out.push({ plat: platKey, account: a.account, region: reg, date: p.date,
          isWeek: !isNaN(t) && (NOW - t) <= WEEK_MS, text: p.text||"",
          type: p.type || (platKey==="facebook" ? "post" : ""), permalink: p.permalink,
          likes, comments: p.comments, shares: p.shares, saved: p.saved,
          reach: p.reach, clicks: p.clicks, views: p.views, eng });
      });
    });
    return out;
  }

  const model = {}; // platKey -> {accounts, posts} | {pending}
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

  const dataPlats = ORDER.filter(k => model[k] && model[k].posts);
  const allPosts = dataPlats.flatMap(k => model[k].posts);
  // regiones presentes en los datos
  const regionsPresent = ORDER.reduce((acc,k)=>{
    if(model[k]&&model[k].accounts){ model[k].accounts.forEach(a=>acc.add(regionKey(a.account))); }
    return acc;
  }, new Set());
  const regionList = Object.keys(REGIONS).filter(r => regionsPresent.has(r));

  // ---- Estado de filtros ----
  let activeNet = "all";     // 'all' | plat
  let activeRegion = "all";  // 'all' | region

  function accountsInScope(){
    const accs = [];
    dataPlats.forEach(k => {
      if(activeNet !== "all" && k !== activeNet) return;
      (model[k].accounts||[]).forEach(a => {
        if(activeRegion !== "all" && regionKey(a.account) !== activeRegion) return;
        accs.push({ plat:k, ...a });
      });
    });
    return accs;
  }
  function postsInScope(){
    return allPosts.filter(p =>
      (activeNet==="all" || p.plat===activeNet) &&
      (activeRegion==="all" || p.region===activeRegion));
  }

  // ---- KPIs reactivos ----
  function renderKpis(){
    const posts = postsInScope();
    const accs = accountsInScope();
    const wk = posts.filter(p => p.isWeek);
    const sum = (arr,f)=> arr.reduce((s,p)=> s + (typeof f(p)==="number"? f(p):0), 0);
    const reachAccs = accs.filter(a=>typeof a.week_reach==="number");
    const followers = accs.reduce((s,a)=> s + (typeof a.followers==="number"? a.followers:0), 0);
    const kpiData = [
      { lab:"Publicaciones", big: wk.length, sub: nf.format(posts.length)+" en total" },
      { lab:"Interacciones", big: sum(wk,p=>p.eng), sub: nf.format(sum(posts,p=>p.eng))+" en total" },
      { lab:"Alcance", big: reachAccs.length? reachAccs.reduce((s,a)=>s+a.week_reach,0) : null,
        sub: "personas · Instagram" },
      { lab:"Seguidores", big: followers, sub: accs.length+" perfil"+(accs.length===1?"":"es") },
    ];
    document.getElementById("kpis").innerHTML = kpiData.map(k => `
      <div class="kpi"><div class="lab">${k.lab}</div>
      <div class="val">${k.big===null? "—" : nf.format(k.big)}</div>
      <div class="sub">${k.sub}</div></div>`).join("");
    // scope line
    const netTxt = activeNet==="all" ? "todas las redes" : PLAT[activeNet].label;
    const regTxt = activeRegion==="all" ? "todas las regiones" : REGIONS[activeRegion].label;
    document.getElementById("scope").innerHTML =
      `Números grandes = <b>últimos 7 días</b> · Mostrando <b>${netTxt}</b> · <b>${regTxt}</b>`;
  }

  // ---- Filtros (2 filas) ----
  function renderFilters(){
    const netChips = [{key:"all",label:"Todas"}].concat(
      ORDER.filter(k=>model[k]).map(k => ({key:k, label:PLAT[k].label,
        icon: ICON[k], count: model[k].posts? model[k].posts.length : null})));
    const regChips = [{key:"all",label:"Todas"}].concat(
      regionList.map(r => ({key:r, label:REGIONS[r].label, flag:REGIONS[r].flag})));
    const netHtml = netChips.map(c => `
      <button class="chip-btn" data-kind="net" data-key="${c.key}" aria-selected="${c.key===activeNet}">
        ${c.icon?c.icon:""}${c.label}${(c.count!=null)?` <span class="cnt">${c.count}</span>`:""}
      </button>`).join("");
    const regHtml = regChips.map(c => `
      <button class="chip-btn" data-kind="reg" data-key="${c.key}" aria-selected="${c.key===activeRegion}">
        ${c.flag?`<span class="fl">${c.flag}</span>`:""}${c.label}
      </button>`).join("");
    document.getElementById("filters").innerHTML =
      `<div class="filterrow"><span class="flabel">Red</span>${netHtml}</div>` +
      (regionList.length ? `<div class="filterrow"><span class="flabel">Región</span>${regHtml}</div>` : "");
  }

  // ---- Tarjetas ----
  function chip(label, val){
    const isNull = (val===null || val===undefined);
    return `<span class="chip${isNull?' null':''}"><b>${isNull?'—':nf.format(val)}</b><span class="k">${label}</span></span>`;
  }
  function postCard(p){
    let chips;
    if(p.plat === "instagram") chips = [ chip("likes",p.likes), chip("coment.",p.comments), chip("guard.",p.saved), chip("alcance",p.reach) ];
    else if(p.plat === "facebook") chips = [ chip("reacc.",p.likes), chip("coment.",p.comments), chip("comp.",p.shares), chip("clics",p.clicks) ];
    else if(p.plat === "youtube") chips = [ chip("vistas",p.views), chip("likes",p.likes), chip("coment.",p.comments) ];
    else chips = [ chip("likes",p.likes), chip("coment.",p.comments), chip("alcance",p.reach) ];
    const flag = REGIONS[p.region] ? REGIONS[p.region].flag : "";
    return `
      <div class="card">
        <div class="crow">
          ${ICON[p.plat]||""}<span class="acc">${escapeHtml(p.account)}</span><span class="fl" title="${REGIONS[p.region]?REGIONS[p.region].label:''}">${flag}</span>
          ${p.type ? `<span class="type-pill">${p.type}</span>` : ""}
        </div>
        <div class="date">${fmtDate(p.date)}${p.isWeek?" · esta semana":""}</div>
        <p class="text${p.text?'':' empty'}">${p.text ? escapeHtml(p.text) : "Sin texto · contenido visual"}</p>
        <div class="metrics">${chips.join("")}</div>
        <div class="foot">
          <span class="eng">Interacción <b>${nf.format(p.eng||0)}</b></span>
          ${p.permalink ? `<a class="view" href="${p.permalink}" target="_blank" rel="noopener">Ver →</a>` : ""}
        </div>
      </div>`;
  }
  function accountGroup(a){
    const posts = model[a.plat].posts.filter(p => p.account===a.account);
    if(!posts.length) return "";
    const flag = REGIONS[regionKey(a.account)] ? REGIONS[regionKey(a.account)].flag : "";
    return `
      <div class="acct">
        <div class="acct-head">${ICON[a.plat]||""}<h3>${escapeHtml(a.account)}</h3><span class="fl">${flag}</span>
          ${(a.followers!=null)?`<span class="foll">${nf.format(a.followers)} seguidores</span>`:""}</div>
        <div class="grid">${posts.map(postCard).join("")}</div>
      </div>`;
  }
  function pendingCard(k){
    const p = model[k].pending;
    return `<div class="pending">${ICON[k]||""}
        <div><div class="pt">${PLAT[k].label}</div><div class="pd">${escapeHtml(p.note||"")}</div></div>
        <span class="status">${p.label||"Pendiente"}</span></div>`;
  }

  function renderContent(){
    const c = document.getElementById("content");
    let html = "";
    // pendientes (solo si no filtras por región y la red aplica)
    if(activeRegion === "all"){
      ORDER.filter(k=>model[k]&&model[k].pending).forEach(k => {
        if(activeNet==="all" || activeNet===k) html += pendingCard(k);
      });
    }
    accountsInScope().forEach(a => { html += accountGroup(a); });
    if(!html) html = `<div class="note">Sin publicaciones para este filtro.</div>`;
    c.innerHTML = html;
  }

  function refresh(){ renderKpis(); renderContent(); }

  document.getElementById("filters").addEventListener("click", e => {
    const b = e.target.closest(".chip-btn"); if(!b) return;
    if(b.dataset.kind === "net") activeNet = b.dataset.key; else activeRegion = b.dataset.key;
    renderFilters(); refresh();
  });

  if(anyInsightsMissing){
    const n = document.getElementById("permnote"); n.classList.remove("hidden");
    n.innerHTML = "<strong>Alcance e impresiones pendientes.</strong> Falta que el token de Meta tenga los permisos de insights.";
  }
  document.getElementById("genat").textContent = DATA.generated_at || "—";
  renderFilters(); refresh();
</script>'''


def main():
    token = read_token()
    fb, ig = fetch(token)
    yt = fetch_youtube()
    model = build_model(fb, ig, yt)
    data_json = json.dumps(model, ensure_ascii=False)
    html = TEMPLATE.replace("__DATA_JSON__", data_json)
    out = os.environ.get("DASHBOARD_OUT", "dashboard.html")
    outdir = os.path.dirname(out)
    if outdir and not os.path.exists(outdir):
        os.makedirs(outdir, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    # summary.json al lado (para el aviso de Slack)
    summary = build_summary(fb, ig, yt)
    spath = os.path.join(outdir, "summary.json") if outdir else "summary.json"
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False)
    fbc = sum(len(a["posts"]) for a in fb)
    igc = sum(len(a["posts"]) for a in ig)
    ytc = sum(len(a["posts"]) for a in yt)
    print("OK -> %s (+ summary.json) | FB %d pag (%d posts) | IG %d ctas (%d) | YT %d canales (%d) | semana: %d posts" % (
        out, len(fb), fbc, len(ig), igc, len(yt), ytc, summary["week_posts"]))


if __name__ == "__main__":
    main()
