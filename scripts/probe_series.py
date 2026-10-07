#!/usr/bin/env python3
"""作業用: 商品情報APIの iteminfo に、シリーズ・レーベル・監督があるか・どのくらい付いているかを調べる（読むだけ。保存しない）。main には入れない。
API_ID を含むURLは出さない。出すのは件数と、シリーズ・レーベルの名前の例（作品のタイトルは出さない）だけ。"""
import json, os, sys, time, urllib.parse, urllib.request
from collections import Counter
API_ID = os.environ.get("API_ID", ""); AFF = os.environ.get("AFFILIATE_ID", "juice0402-990")
def note(t, s):
    s = str(s).replace("\n", " | ").replace("%", "%25").replace(API_ID or "\0", "***"); print(f"::notice title={t}::{s[:3500]}", flush=True)
def call(params):
    q = {"api_id": API_ID, "affiliate_id": AFF, "output": "json", "site": "FANZA", "service": "digital", "floor": "videoa"}
    q.update(params)
    with urllib.request.urlopen(urllib.request.Request("https://api.dmm.com/affiliate/v3/ItemList?" + urllib.parse.urlencode(q), headers={"User-Agent": "Mozilla/5.0"}), timeout=30) as r:
        return (json.loads(r.read().decode("utf-8")).get("result") or {}).get("items") or []
items = []
for sort, off in (("rank", 1), ("rank", 101), ("date", 1), ("rank", 5001)):
    try:
        items += call({"sort": sort, "hits": 100, "offset": off}); time.sleep(1)
    except Exception as e:
        note("err", type(e).__name__)
note("n", len(items))
keys = Counter(k for it in items for k in (it.get("iteminfo") or {}))
note("iteminfo-keys", keys.most_common())
ex = next((it.get("iteminfo") for it in items if (it.get("iteminfo") or {}).get("series")), {})
note("shape", {k: (v[:1] if isinstance(v, list) else v) for k, v in (ex or {}).items() if k in ("series", "label", "maker", "director")})
ser = Counter((s.get("id"), s.get("name")) for it in items for s in ((it.get("iteminfo") or {}).get("series") or [])[:1])
lab = Counter((s.get("id"), s.get("name")) for it in items for s in ((it.get("iteminfo") or {}).get("label") or [])[:1])
multi_s = sum(1 for it in items if len((it.get("iteminfo") or {}).get("series") or []) > 1)
multi_l = sum(1 for it in items if len((it.get("iteminfo") or {}).get("label") or []) > 1)
note("series", f"with={sum(1 for it in items if (it.get('iteminfo') or {}).get('series'))} distinct={len(ser)} multi={multi_s} top={ser.most_common(12)}")
note("label", f"with={sum(1 for it in items if (it.get('iteminfo') or {}).get('label'))} distinct={len(lab)} multi={multi_l} top={lab.most_common(12)}")
same = sum(1 for it in items for l in ((it.get("iteminfo") or {}).get("label") or [])[:1] for m in ((it.get("iteminfo") or {}).get("maker") or [])[:1] if l.get("name") == m.get("name"))
note("label-eq-maker", same)
dirs = Counter(d.get("name") for it in items for d in ((it.get("iteminfo") or {}).get("director") or [])[:1])
note("director", f"with={sum(dirs.values())} distinct={len(dirs)}")
