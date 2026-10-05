"""下調べ3回目（2026-10-05）: WILLグループのメーカーの /top の、作品・女優以外のリンク（メニュー・フッター）を全部と、
「イベント」「ニュース」「お知らせ」「規約」「ポリシー」らしいページの中身の形・規約の文。ページの本文は保存しない。"""
import json
import re
import sys
import traceback
import urllib.parse

sys.path.insert(0, "scripts")
import maker_probe as P  # noqa: E402
import maker_probe2 as Q  # noqa: E402


def probe(base):
    op, _ = P.opener()
    top = P.get(op, base + "top")
    t = top.get("text", "")
    host = urllib.parse.urlsplit(base).netloc
    menu, seen = [], set()
    for u, l in P.links(t, base + "top"):
        sp = urllib.parse.urlsplit(u)
        if re.match(r"^/(actress|works)/(detail|list)", sp.path) or re.match(r"^/actress/[a-z]+$", sp.path):
            continue
        key = (sp.netloc, sp.path)
        if key in seen:
            continue
        seen.add(key)
        menu.append((u, l))
    entry = {"menu": menu[:80]}
    pages = []
    for u, l in menu:
        if urllib.parse.urlsplit(u).netloc != host or not re.search(r"(?i)event|news|topics|info|schedule|イベント|ニュース|お知らせ|policy|terms|kiyaku|規約|ポリシー|ご利用|注意", u + " " + l):
            continue
        r = P.get(op, u)
        tx = r.get("text", "")
        samples, n = Q.dated_samples(tx, 10)
        item = {"url": u, "label": l, "status": r.get("status"), "len": len(tx), "title": P.page_summary(r)["title"][:80], "dated_count": n, "dated_samples": samples}
        if re.search(r"(?i)policy|terms|kiyaku|規約|ポリシー|ご利用|注意", u + " " + l):
            item["clauses"] = Q.clauses(tx, 30)
        else:
            subs = [(x, y) for x, y in P.links(tx, u) if urllib.parse.urlsplit(x).netloc == host and re.search(r"(?i)/(event|news|topics|info)[^?#]*/[^/?#]+", urllib.parse.urlsplit(x).path)]
            item["detail_links"] = subs[:8]
            if subs:
                d = P.get(op, subs[0][0])
                dt = d.get("text", "")
                ds, _ = Q.dated_samples(dt, 6)
                body = re.search(r"<(?:article|main)\b[\s\S]*?</(?:article|main)>", dt, re.I)
                item["detail"] = {"url": subs[0][0], "status": d.get("status"), "title": P.page_summary(d)["title"][:120], "dated": ds,
                                  "actress_links": [(x, y) for x, y in P.links(dt, subs[0][0]) if "/actress/detail/" in x][:6],
                                  "body_head": P.text_of(body.group(0))[:300] if body else ""}
        pages.append(item)
        if len(pages) >= 8:
            break
    entry["pages"] = pages
    return entry


def main(argv):
    out = argv[1]
    res = {}
    for key, base in (("s1", "https://s1s1s1.com/"), ("moodyz", "https://moodyz.com/"), ("ideapocket", "https://ideapocket.com/")):
        try:
            res[key] = probe(base)
        except Exception:  # noqa: BLE001
            res[key] = {"crash": traceback.format_exc()[-1500:]}
        json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv)
