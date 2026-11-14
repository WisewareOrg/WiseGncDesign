import re, sys, numpy as np
for f in sys.argv[1:]:
    rows = [re.match(r"case (\d+) ([\d.]+)s rss ([\d.]+)MB", l).groups() for l in open(f) if l.startswith("case")]
    k = np.array([int(r[0]) for r in rows]); t = np.array([float(r[1]) for r in rows]); r = np.array([float(r[2]) for r in rows])
    print(f"{f}: n={len(k)} time mean {t.mean():.3f} median {np.median(t):.3f} (case0 {t[0]:.3f}) | rss start {r[0]:.0f} end {r[-1]:.0f} MB, slope {np.polyfit(k,r,1)[0]*1000:.0f} kB/case (cases 20-99: {np.polyfit(k[20:],r[20:],1)[0]*1000:.0f})")
