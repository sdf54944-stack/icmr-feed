import json, urllib.request, sys, re, datetime as dt
from collections import defaultdict

SYMBOLS = ["_SPX", "_NDX", "_RUT"]  # أضف/احذف رموزًا هنا. الفاشل يُتخطّى تلقائيًا.
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

def detect_step(strikes):
    ss = sorted(set(strikes))
    if len(ss) < 2: return 5
    diffs = sorted({round(ss[i+1]-ss[i], 2) for i in range(len(ss)-1) if ss[i+1] != ss[i]})
    return diffs[0] if diffs else 5

index = {}   # فهرس بكل الرموز الناجحة، للتطبيق
today = dt.date.today().isoformat()

for sym in SYMBOLS:
    clean = sym.lstrip("_")
    try:
        raw = json.load(urllib.request.urlopen(BASE_URL.format(sym), timeout=25))
    except Exception as e:
        print(f"skip {sym}: {e}", file=sys.stderr)
        continue

    payload = raw.get("data", raw)
    opts = payload.get("options", [])
    spot = payload.get("current_price") or payload.get("close")
    if not spot or not opts:
        print(f"skip {sym}: no data", file=sys.stderr)
        continue

    strikes = [p[2] for o in opts if (p := parse(o["option"]))]
    step = detect_step(strikes)
    band = step * 7                       # ±7 سترايكات (نسبي للخطوة)
    base = round(spot/step)*step
    lo, hi = base - band, base + band

    exps = sorted({p[0] for o in opts if (p := parse(o["option"]))})
    near = next((e for e in exps if e >= today), exps[0] if exps else None)

    # OI مجمّع عبر كل التواريخ | الأسعار من الأقرب
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
           "step":step, "rows":rows, "availableExp":exps[:12]}
    open(f"data/{clean}.json","w").write(json.dumps(out, indent=2))
    index[clean] = {"spot":round(spot,1), "strikes":len(rows)}
    maxc = max((r["callOi"] for r in rows), default=0)
    print(f"wrote {clean}: {len(rows)} strikes | spot={round(spot,1)} | step={step} | maxCallOI={maxc}")

# فهرس الرموز المتاحة (يقرؤه التطبيق ليبني مبدّل المؤشرات)
open("data/index.json","w").write(json.dumps({"symbols":list(index.keys()),"detail":index}, indent=2))
print(f"index: {list(index.keys())}")
