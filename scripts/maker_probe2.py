"""メーカーの公式サイトとイベルト（av-event.jp）の下調べ・2回目（2026-10-05）。
1回目で、WILLグループのメーカー（S1・MOODYZ・アイデアポケットなど）は robots.txt で止めておらず、年齢確認の「はい（入室する）」は
/top へのふつうのリンク（クッキーも要らない）と分かった。2回目は /top の中の「イベント」「ニュース」「利用規約」のリンクと、
その中身の形（見出しの見本）、利用規約の「禁止」などの文を見る。イベルトは、イベントの一覧・1件のページの形と、利用規約の禁止事項。
ページの本文は保存しない（見本と、規約の該当する文だけ）。
"""
import json
import re
import sys
import traceback
import urllib.parse

sys.path.insert(0, "scripts")
import maker_probe as P  # noqa: E402

CLAUSE = re.compile(r"禁止|してはならない|できません|行わない|複製|転載|転用|営利|商用|自動|クローラ|スクレイピング|ロボット|収集|二次利用|無断|引用|リンク|著作権")
LINK_WORDS = re.compile(r"(?i)event|イベント|news|ニュース|お知らせ|info|topics|terms|kiyaku|規約|ご利用|policy|ポリシー|company|会社|actress|女優|feed|rss")


def dated_samples(text, limit=10):
    heads = []
    for tag in ("h2", "h3", "h4", "p", "dt", "dd", "li", "a", "span", "div"):
        for x in re.findall(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), text, re.I | re.S):
            s = P.text_of(x)
            if re.search(r"\d{1,2}\s*[/月]\s*\d{1,2}", s) and 6 < len(s) < 140 and s not in heads:
                heads.append(s)
    return heads[:limit], len(heads)


def clauses(text, limit=25):
    out = []
    for s in re.split(r"[。\n]|(?<=\d\.)|(?=（\d+）)|(?=\(\d+\))", P.text_of(text)):
        s = s.strip()
        if CLAUSE.search(s) and 6 < len(s) < 260 and s not in out:
            out.append(s)
    return out[:limit]


def block_around(text, pattern, width=1500, count=2):
    out = []
    for m in re.finditer(pattern, text):
        out.append(re.sub(r"\s+", " ", text[max(0, m.start() - 200):m.start() + width]))
        if len(out) >= count:
            break
    return out


def probe_maker(base):
    op, jar = P.opener()
    top = P.get(op, base + "top")
    links = P.links(top.get("text", ""), base + "top")
    found = []
    for u, l in links:
        if urllib.parse.urlsplit(u).netloc == urllib.parse.urlsplit(base).netloc and LINK_WORDS.search(u + " " + l) and (u, l) not in found:
            found.append((u, l))
    entry = {"top_status": top.get("status"), "top_len": len(top.get("text", "")), "links": found[:40]}
    pages = {}
    for u, l in found:
        key = urllib.parse.urlsplit(u).path.rstrip("/").split("/")[1] if urllib.parse.urlsplit(u).path.strip("/") else ""
        if key in pages or not re.search(r"(?i)event|news|イベント|ニュース|terms|規約|policy|ご利用|company|会社", u + " " + l):
            continue
        r = P.get(op, u)
        t = r.get("text", "")
        samples, n = dated_samples(t)
        item = {"url": u, "label": l, "status": r.get("status"), "len": len(t), "title": P.page_summary(r)["title"][:80], "dated_count": n, "dated_samples": samples}
        if re.search(r"(?i)terms|規約|policy|ご利用|company|会社", u + " " + l):
            item["clauses"] = clauses(t)
        if re.search(r"(?i)event|イベント|news|ニュース", u + " " + l):
            sub = [(x, y) for x, y in P.links(t, u) if re.search(r"(?i)/(event|news)s?/[^/?#]+", urllib.parse.urlsplit(x).path)]
            item["detail_links"] = sub[:8]
            if sub:
                d = P.get(op, sub[0][0])
                dt = d.get("text", "")
                ds, dn = dated_samples(dt, 6)
                item["detail"] = {"url": sub[0][0], "status": d.get("status"), "title": P.page_summary(d)["title"][:100], "dated": ds,
                                  "actress_links": [(x, y) for x, y in P.links(dt, sub[0][0]) if re.search(r"(?i)actress|女優", x)][:6]}
        pages[key] = item
        if len(pages) >= 6:
            break
    entry["pages"] = list(pages.values())
    return entry


def probe_evelt():
    base = "https://www.av-event.jp/"
    op, jar = P.opener()
    top = P.get(op, base + "top/")
    t = top.get("text", "")
    links = P.links(t, base + "top/")
    paths = {}
    for u, l in links:
        if urllib.parse.urlsplit(u).netloc != "www.av-event.jp":
            continue
        p = urllib.parse.urlsplit(u).path
        shape = re.sub(r"\d+", "N", p)
        paths.setdefault(shape, []).append((u, l[:50]))
    entry = {"top_status": top.get("status"), "path_shapes": {k: (len(v), v[:2]) for k, v in sorted(paths.items(), key=lambda kv: -len(kv[1]))[:40]}}
    ev = [u for u, l in links if re.search(r"/event/\d+/?$", urllib.parse.urlsplit(u).path)]
    entry["event_link_count"] = len(set(ev))
    if ev:
        d = P.get(op, ev[0])
        dt = d.get("text", "")
        entry["detail"] = {"url": ev[0], "status": d.get("status"), "title": P.page_summary(d)["title"][:120],
                           "dl_rows": [(P.text_of(a)[:30], P.text_of(b)[:80]) for a, b in re.findall(r"<(?:dt|th)\b[^>]*>(.*?)</(?:dt|th)>\s*<(?:dd|td)\b[^>]*>(.*?)</(?:dd|td)>", dt, re.I | re.S)][:15],
                           "links": [(u, l) for u, l in P.links(dt, ev[0]) if re.search(r"(?i)actress|maker|label|shop|tag|category|女優|メーカー", u)][:12]}
    for path in ("event/", "feed/", "rss/", "event/?page=2"):
        r = P.get(op, base + path)
        s, n = dated_samples(r.get("text", ""), 5)
        entry.setdefault("lists", []).append({"path": path, "status": r.get("status"), "len": len(r.get("text", "")), "dated_count": n, "samples": s,
                                             "is_feed": "<rss" in r.get("text", "")[:500] or "<feed" in r.get("text", "")[:500]})
    terms = P.get(op, base + "terms/")
    entry["terms_clauses"] = clauses(terms.get("text", ""), 40)
    entry["operator"] = [s for s in re.split(r"[。\n]", P.text_of(terms.get("text", ""))) if re.search(r"運営|株式会社|合同会社|有限会社", s)][:6]
    return entry


def main(argv):
    out = argv[1] if len(argv) > 1 else "discovery/maker_probe2.json"
    res = {}
    for key, base in (("s1", "https://s1s1s1.com/"), ("moodyz", "https://moodyz.com/"), ("ideapocket", "https://ideapocket.com/"), ("madonna", "https://madonna-av.com/")):
        try:
            res[key] = probe_maker(base)
        except Exception:  # noqa: BLE001
            res[key] = {"crash": traceback.format_exc()[-1500:]}
        print(key, "ok" if "crash" not in res[key] else "crash")
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    try:
        res["evelt"] = probe_evelt()
    except Exception:  # noqa: BLE001
        res["evelt"] = {"crash": traceback.format_exc()[-1500:]}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv)
