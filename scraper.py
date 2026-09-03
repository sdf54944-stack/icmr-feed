import json, urllib.request, sys, re, datetime as dt
from collections import defaultdict

URL = "https://cdn.cboe.com/api/global/delayed_quotes/options/_SPX.json"
BAND = 35

raw = json.load(urllib.request.urlopen(URL, timeout=25))
payload = raw.get("data", raw)
opts = payload.get("options", [])
spot = payload.get("current_price") or payload.get("close")
if not spot:
    print("WARN: no spot key", file=sys.stderr); spot = 0

base = (spot // 5) * 5
lo, hi = base - BAND, base + BAND

SYM = re.compile(r"([A-Z]+)(\d{6})([CP])(\d{8})")
def parse(sym):
    m = SYM.match(sym)
    if not m: return None
    _, ymd, kind, k = m.groups()
    return f"20{ymd[0:2]}-{ymd[2:4]}-{ymd[4:6]}", kind, int(k)/1000

def px(o):
    b, a = o.get("bid",0) or 0, o.get("ask",0) or 0
    return round((b+a)/2,2) if (b or a) else round(o.get("theo",0) or 0,2)

today = dt.date.today().isoformat()
exps = sorted({p[0] for o in opts if (p:=parse(o["option"]))})
near = next((e for e in exps if e >= today), exps[0] if exps else None)  # الأسعار من الأقرب

# OI يتجمّع عبر كل التواريخ | الأسعار من أقرب تاريخ فقط
buck = defaultdict(lambda:{"callOi":0,"putOi":0,"call":0.0,"put":0.0})
for o in opts:
    p = parse(o["option"])
    if not p: continue
    exp, kind, k = p
    if not (lo <= k <= hi): continue
    r = buck[k]
    oi = o.get("open_interest",0) or 0
    if kind == "C":
        r["callOi"] += oi
        if exp == near: r["call"] = px(o)
    else:
        r["putOi"] += oi
        if exp == near: r["put"] = px(o)

rows = [{"strike":k, **v} for k,v in sorted(buck.items(), reverse=True)]
out = {"spot":round(spot or 0,1),"exp":f"{near} (OI مجمّع لكل التواريخ)","rows":rows,"availableExp":exps[:12]}
open("data/spx.json","w").write(json.dumps(out, indent=2))
maxc = max((r["callOi"] for r in rows), default=0)
maxp = max((r["putOi"] for r in rows), default=0)
print(f"wrote {len(rows)} strikes | near={near} | spot={out['spot']} | maxCallOI={maxc} maxPutOI={maxp}")
