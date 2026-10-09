#!/usr/bin/env python3
"""FANZA同人・FANZAゲームの「人気の動き」と「セールの記録」を、毎日足していく（Python標準ライブラリだけ。Gemini は使わない）。

運営者の希望「動画のページと同じレベルの仕組みを同人とゲームにも。SEO対策も徹底的に」→「人気の動き」「セールの充実」（2026-10-09）。
scripts/doujin_game.py の update_floor が、その日のデータ（doujin.json・game.json）を保存したあとに呼ぶ。
毎日の順位・セールは、ほかのファイルに残らないので、記録を始めた日からしかたまらない。

人気の動き（site/src/data/floor_rank_history.json。1作品1行）:
  {"updated": 日付, "doujin": {cid: {"d": 記録の最初の日, "r": [順位, …]}}, "game": {…}}
  ・順位は、サイトの人気ランキングと同じ数え方（発売済みの作品を FANZA の人気順に並べた、このサイトでの順位。1〜）。上位 RANK_TRACK 本だけ記録
  ・1日1つ。0＝圏外（RANK_TRACK 位より下・載っていない）、null＝その日は最後まで読めなかった（分からない）
  ・RANK_DAYS 日分だけ持つ（古い日は前から捨てて、d を進める）。その間ずっと圏外だった作品は消す
セールの記録（site/src/data/floor_sale_history.json）:
  {"updated": 日付, "doujin": {"days": [{"d", "n": セール中の本数, "max": 最大の割引（%）}], "tags": [{"title", "begin", "first", "last", "count", "off"}]}, "game": {…}}
  ・days: 1日1行。tags: セール・キャンペーンの名前ごと（同人は「50%OFF」と始まりの日、ゲームは「最大90%OFFセール【感謝祭オータム2026】」のような札）。
    first・last: 最初と最後に見かけた日・count: その名前の作品がいちばん多かった日の本数・off: 名前から読める最大の割引（無ければ 0）
  ・SALE_KEEP_DAYS 日より前のものは消す
"""
import json
import os
import re
import sys
from datetime import datetime, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT, "site", "src", "data")
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import floor_data as F  # noqa: E402

FLOOR_KEYS = tuple(F.FLOORS)  # 売り場（同人・ゲーム・アニメ・素人・成人映画・コミック・写真集・VR見放題。scripts/floor_data.py）

RANK_TRACK = 300  # 順位を記録する本数（売り場ごと、人気順の上から。ファイルと毎日の差分を小さく）
RANK_DAYS = 30  # 何日分の順位を持つか（作品ページのグラフ）
SALE_KEEP_DAYS = 400  # セールの記録を何日分持つか

DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
CID = re.compile(r"^[A-Za-z0-9_\-]{1,40}$")
OFF_IN_TITLE = re.compile(r"(\d{1,2})\s*[%％]\s*(?:OFF|ＯＦＦ|オフ)")


def rank_history_path():
    return os.environ.get("FLOOR_RANK_HISTORY_PATH", os.path.join(DATA_DIR, "floor_rank_history.json"))


def sale_history_path():
    return os.environ.get("FLOOR_SALE_HISTORY_PATH", os.path.join(DATA_DIR, "floor_sale_history.json"))


def days_between(a, b):
    try:
        return (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days
    except (TypeError, ValueError):
        return None


def add_days(day, n):
    return (datetime.strptime(day, "%Y-%m-%d") + timedelta(days=n)).strftime("%Y-%m-%d")


def _read(path):
    """JSON を読む。無ければ None。壊れていれば ValueError"""
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError) as e:
        raise ValueError(str(e)) from e


def _write(path, text):
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".tmp", path)


def is_sale_tag(tag):
    """値下げのセールの札か（クーポン・ポイント還元は、ほぼ全部の作品に付くので入れない。site/src/lib/floors.js の isSaleTag と同じ）"""
    return "セール" in tag and not re.search(r"クーポン|還元", tag)


def off_of(item):
    """値引きの割合（%）。価格と定価が分かるときだけ（site/src/lib/floors.js の offOf と同じ）"""
    price, base = item.get("price"), item.get("list_price")
    return round((1 - price / base) * 100) if isinstance(price, int) and isinstance(base, int) and 0 < price < base else 0


def off_in_title(title):
    """名前から読める最大の割引（「最大90%OFF」「50%OFF」→ 90・50、「半額」→ 50）。読めなければ 0"""
    nums = [int(m) for m in OFF_IN_TITLE.findall(str(title or ""))]
    if nums:
        return max(nums)
    return 50 if "半額" in str(title or "") else 0


# ---------- 人気の動き ----------

def positions(data, track=RANK_TRACK):
    """その日のデータ → {cid: このサイトの人気ランキングでの順位}（上位 track 本だけ）"""
    ranks = data.get("ranks") or {}
    ordered = sorted((r, cid) for cid, r in ranks.items() if isinstance(r, int) and r > 0)
    return {cid: i + 1 for i, (_, cid) in enumerate(ordered[:track])}


def _rank_list(values):
    out = []
    for v in (values if isinstance(values, list) else [])[:RANK_DAYS]:
        out.append(v if v is None or (isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 100000) else None)
    return out


def load_rank_history():
    """無い・壊れているときは空から始める（ほかに元のデータが無いので、壊れていたら記録し直すしかない）"""
    try:
        raw = _read(rank_history_path())
    except ValueError as e:
        print(f"⚠️ 同人・ゲームの人気の動き（floor_rank_history.json）を読めませんでした（{e}）。空から記録し直します")
        raw = None
    hist = {"updated": "", **{k: {} for k in FLOOR_KEYS}}
    if not isinstance(raw, dict):
        return hist
    hist["updated"] = raw.get("updated") if isinstance(raw.get("updated"), str) and DAY.match(raw["updated"]) else ""
    for key in FLOOR_KEYS:
        rows = raw.get(key) if isinstance(raw.get(key), dict) else {}
        for cid, row in rows.items():
            if CID.match(str(cid)) and isinstance(row, dict) and isinstance(row.get("d"), str) and DAY.match(row["d"]):
                hist[key][str(cid)] = {"d": row["d"], "r": _rank_list(row.get("r"))}
    return hist


def merge_rank_history(hist, key, today_str, pos):
    """きょうの順位（pos: {cid: 順位}。最後まで読めなかった日は None）を足す。消した作品の数を返す"""
    rows = hist.setdefault(key, {})
    for cid in pos or {}:
        rows.setdefault(cid, {"d": today_str, "r": []})
    for cid, row in rows.items():
        i = days_between(row["d"], today_str)
        if i is None or i < 0:
            continue
        r = row["r"]
        while len(r) <= i:
            r.append(None)
        value = None if pos is None else pos.get(cid, 0)
        if not (value is None and r[i] is not None):  # 同じ日に2回動いたとき、分かっている順位を「分からない」で上書きしない
            r[i] = value
        if len(r) > RANK_DAYS:  # 古い日は前から捨てて、最初の日を進める
            cut = len(r) - RANK_DAYS
            row["r"] = r[cut:]
            row["d"] = add_days(row["d"], cut)
    gone = [cid for cid, row in rows.items() if not any(v for v in row["r"])]
    for cid in gone:
        del rows[cid]
    hist["updated"] = today_str
    return len(gone)


def save_rank_history(hist):
    parts = []
    for key in FLOOR_KEYS:
        rows = sorted(hist.get(key, {}).items(), key=lambda kv: kv[0])
        lines = [f'{json.dumps(cid)}:{{"d":{json.dumps(row["d"])},"r":{json.dumps(row["r"], separators=(",", ":"))}}}' for cid, row in rows]
        parts.append(f'{json.dumps(key)}:{{\n' + ",\n".join(lines) + ("\n" if lines else "") + "}")
    _write(rank_history_path(), f'{{"updated":{json.dumps(hist.get("updated", ""))},\n' + ",\n".join(parts) + "}\n")


# ---------- セールの記録 ----------

def sale_today(data, today_str):
    """その日のデータ → ({"d", "n", "max"}, [{"title", "begin", "count", "off"}])"""
    items = [i for i in (data.get("items") or {}).values() if str(i.get("date", ""))[:10] <= today_str]
    on_sale = [i for i in items if off_of(i) > 0 or any(is_sale_tag(t) for t in i.get("sales") or [])]
    best = max([off_of(i) for i in on_sale] + [off_in_title(t) for i in on_sale for t in i.get("sales") or [] if is_sale_tag(t)] + [0])
    counts = {}
    for i in items:
        names = [(t, "") for t in i.get("sales") or []]
        camp = i.get("campaign")
        if isinstance(camp, dict) and camp.get("title"):
            names.append((str(camp["title"]), str(camp.get("begin") or "")))
        for name in dict.fromkeys(names):
            counts[name] = counts.get(name, 0) + 1
    tags = [{"title": t, "begin": b, "count": n, "off": off_in_title(t)} for (t, b), n in sorted(counts.items())]
    return {"d": today_str, "n": len(on_sale), "max": best}, tags


def _sale_floor(raw):
    days, tags = [], []
    for d in (raw.get("days") if isinstance(raw, dict) and isinstance(raw.get("days"), list) else []):
        if isinstance(d, dict) and isinstance(d.get("d"), str) and DAY.match(d["d"]) and isinstance(d.get("n"), int) and isinstance(d.get("max"), int):
            days.append({"d": d["d"], "n": d["n"], "max": d["max"]})
    for t in (raw.get("tags") if isinstance(raw, dict) and isinstance(raw.get("tags"), list) else []):
        if isinstance(t, dict) and isinstance(t.get("title"), str) and t["title"] and all(isinstance(t.get(k), str) and DAY.match(t[k]) for k in ("first", "last")):
            tags.append({"title": t["title"], "begin": str(t.get("begin") or ""), "first": t["first"], "last": t["last"],
                         "count": t["count"] if isinstance(t.get("count"), int) else 0, "off": t["off"] if isinstance(t.get("off"), int) else 0})
    return {"days": days, "tags": tags}


def load_sale_history():
    """無いときは空から。壊れているときは ValueError（記録を上書きして消さないように、呼ぶ側はその日の記録をやめる）"""
    raw = _read(sale_history_path())
    hist = {"updated": "", **{k: {"days": [], "tags": []} for k in FLOOR_KEYS}}
    if raw is None:
        return hist
    if not isinstance(raw, dict):
        raise ValueError("形が違います")
    hist["updated"] = raw.get("updated") if isinstance(raw.get("updated"), str) and DAY.match(raw["updated"]) else ""
    for key in FLOOR_KEYS:
        hist[key] = _sale_floor(raw.get(key))
    return hist


def merge_sale_history(hist, key, today_str, day, tags):
    floor = hist.setdefault(key, {"days": [], "tags": []})
    floor["days"] = [d for d in floor["days"] if d["d"] != today_str and (days_between(d["d"], today_str) or 0) < SALE_KEEP_DAYS] + [day]
    floor["days"].sort(key=lambda d: d["d"])
    known = {(t["title"], t["begin"]): t for t in floor["tags"]}
    for t in tags:
        row = known.get((t["title"], t["begin"]))
        if row:
            row["last"] = max(row["last"], today_str)
            row["count"] = max(row["count"], t["count"])
            row["off"] = max(row["off"], t["off"])
        else:
            known[(t["title"], t["begin"])] = {"title": t["title"], "begin": t["begin"], "first": today_str, "last": today_str, "count": t["count"], "off": t["off"]}
    floor["tags"] = sorted((t for t in known.values() if (days_between(t["last"], today_str) or 0) < SALE_KEEP_DAYS),
                           key=lambda t: (t["last"], t["first"], t["title"]), reverse=True)
    hist["updated"] = today_str


def save_sale_history(hist):
    parts = []
    for key in FLOOR_KEYS:
        floor = hist.get(key) or {"days": [], "tags": []}
        days = ",\n".join(json.dumps(d, ensure_ascii=False, separators=(",", ":")) for d in floor["days"])
        tags = ",\n".join(json.dumps(t, ensure_ascii=False, separators=(",", ":")) for t in floor["tags"])
        parts.append(f'{json.dumps(key)}:{{"days":[\n{days}\n],"tags":[\n{tags}\n]}}')
    _write(sale_history_path(), f'{{"updated":{json.dumps(hist.get("updated", ""))},\n' + ",\n".join(parts) + "}\n")


def record(key, data, today_str, trusted):
    """doujin_game.py から: その日のデータを、人気の動きとセールの記録に足して保存する。結果の要約の文を返す。
    最後まで読めなかった日（trusted でない）は、順位を「分からない」にし、セールは記録しない（前の日のデータが混ざっているため）"""
    hist = load_rank_history()
    pos = positions(data) if trusted else None
    removed = merge_rank_history(hist, key, today_str, pos)
    save_rank_history(hist)
    note = f"人気の動き {len(hist[key])}本を記録中（外した{removed}本）"
    if not trusted:
        return note + "・きょうの順位とセールは記録しない（最後まで読めなかったため）"
    try:
        sales = load_sale_history()
    except ValueError as e:
        print(f"::warning title=セールの記録を読めませんでした::{e}。上書きを防ぐため、きょうは記録しません")
        return note + "・セールの記録は読めなかったので、きょうは記録しない"
    day, tags = sale_today(data, today_str)
    merge_sale_history(sales, key, today_str, day, tags)
    save_sale_history(sales)
    return note + f"・セール中 {day['n']}本（最大{day['max']}%OFF）・セールの名前 {len(sales[key]['tags'])}件を記録"


if __name__ == "__main__":
    sys.exit("scripts/doujin_game.py --update から使います")
