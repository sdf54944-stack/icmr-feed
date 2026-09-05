import json, urllib.request, sys, re, datetime as dt, os
from collections import defaultdict

CONFIG = {
    "_SPX": 0.006,
    "_RUT": 0.008,
    "QQQ":  0.015,
    "SPY":  0.015,
    "GLD":  0.020,
    "AAPL": 0.040,
    "NVDA": 0.050,
    "TSLA": 0.060,
}
BASE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/{}.json"

SYM = re.compile(r"([A-Z]+)(\d{6})([CP])(\d{8})")
def parse(sym):
    m = SYM.match(sym)
    if not m: return None
    _, ymd, kind, k = m.groups()
    return f"20{ymd[0:2]}-{ymd[2:4]}-{ymd[4:6]}", kind, int(k)/1000

def px(o):
    b, a = o.get("bid",0) or 0, o.get("ask",0) or 0
    return round((b+a)/2,2) if (b or a) else round(o.get("theo",0) or 0,2)

index = {}
today = dt.date.today().isoformat()

for sym, pct in CONFIG.items():
    clean = sym.lstrip("_")
    try:
        raw = json.load(urllib.request.urlopen(BASE_URL.format(sym), timeout=25))
    except Exception as e:
        print(f"skip {sym}: {e}", file=sys.stderr); continue

    payload = raw.get("data", raw)
    opts = payload.get("options", [])
    spot = payload.get("current_price") or payload.get("close")
    if not spot or not opts:
        print(f"skip {sym}: no data", file=sys.stderr); continue

    lo, hi = spot*(1-pct), spot*(1+pct)
    exps = sorted({p[0] for o in opts if (p := parse(o["option"]))})
    near = next((e for e in exps if e >= today), exps[0] if exps else None)

    buck = defaultdict(lambda: {"callOi":0,"putOi":0,"call":0.0,"put":0.0})
    for o in opts:
        p = parse(o["option"])
        if not p: continue
        exp, kind, k = p
        if not (lo <= k <= hi): continue
        r = buck[k]; oi = o.get("open_interest",0) or 0
        if kind == "C":
            r["callOi"] += oi
            if exp == near: r["call"] = px(o)
        else:
            r["putOi"] += oi
            if exp == near: r["put"] = px(o)

    rows = [{"strike":k, **v} for k,v in sorted(buck.items(), reverse=True)]
    out = {"symbol":clean, "spot":round(spot,1), "exp":f"{near} (OI مجمّع)",
           "rows":rows, "availableExp":exps[:12]}
    open(f"data/{clean}.json","w").write(json.dumps(out, indent=2))
    index[clean] = {"spot":round(spot,1), "strikes":len(rows)}
    maxc = max((r["callOi"] for r in rows), default=0)
    print(f"wrote {clean}: {len(rows)} strikes | spot={round(spot,1)} | maxCallOI={maxc}")

open("data/index.json","w").write(json.dumps({"symbols":list(index.keys()),"detail":index}, indent=2))

# ── تنبيهات تيليجرام ──
TG_TOKEN = os.environ.get("TG_TOKEN")
TG_CHAT = os.environ.get("TG_CHAT")
ALERT_PCT = 0.20  # اختبار: 5%. أرجعه لـ 0.15 بعد التأكّد

def send_tg(text):
    if not TG_TOKEN or not TG_CHAT: return
    try:
        u = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        d = json.dumps({"chat_id": TG_CHAT, "text": text}).encode()
        req = urllib.request.Request(u, data=d, headers={"Content-Type":"application/json"})
        urllib.request.urlopen(req, timeout=15)
    except Exception as e:
        print(f"tg fail: {e}", file=sys.stderr)

alerts = []
for clean in index:
    try:
        d = json.load(open(f"data/{clean}.json"))
    except: continue
    sp, rws = d["spot"], d["rows"]
    above = [r for r in rws if r["strike"] > sp]
    below = [r for r in rws if r["strike"] < sp]
    res = max(above, key=lambda r: r.get("callOi",0)) if above else None
    sup = max(below, key=lambda r: r.get("putOi",0)) if below else None
    for wall, kind in [(res,"مقاومة"), (sup,"دعم")]:
        if not wall: continue
        dist = abs(wall["strike"] - sp) / sp * 100
        if dist <= ALERT_PCT:
            alerts.append(f"⚡ {clean}: {sp} قرب {kind} {wall['strike']} (بُعد {dist:.2f}%)")

statefile = "data/.alert_state.json"
prev = {}
try: prev = json.load(open(statefile))
except: pass
new_state = {}
for a in alerts:
    key = a.split(" (")[0]
    new_state[key] = True
    if key not in prev:
        send_tg(a)
open(statefile, "w").write(json.dumps(new_state))
print(f"alerts: {len(alerts)} active | index: {list(index.keys())}")
