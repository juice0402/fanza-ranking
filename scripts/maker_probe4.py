"""下調べ4回目（2026-10-05）: イベルト（av-event.jp）のリンクについての決まり（/link/・/guide/）と、イベント主催者の一覧（どのメーカー・事務所が載せているか）。
本文は保存しない（リンク・転載についての文と、主催者の名前・件数だけ）。"""
import json
import re
import sys

sys.path.insert(0, "scripts")
import maker_probe as P  # noqa: E402
import maker_probe2 as Q  # noqa: E402

LINKY = re.compile(r"リンク|バナー|転載|引用|掲載|許可|許諾|連絡|自由|商用|営利|アフィリエイト|禁止")


def main(argv):
    out = argv[1]
    op, _ = P.opener()
    res = {}
    for path in ("link/", "guide/", "help/"):
        r = P.get(op, "https://www.av-event.jp/" + path)
        sents = [s.strip() for s in re.split(r"[。\n]", P.text_of(r.get("text", ""))) if LINKY.search(s) and 6 < len(s.strip()) < 240]
        res[path] = {"status": r.get("status"), "sentences": sents[:25]}
    r = P.get(op, "https://www.av-event.jp/organizer/")
    orgs = []
    for u, l in P.links(r.get("text", ""), "https://www.av-event.jp/organizer/"):
        m = re.search(r"/organizer/event_list/(\d+)/", u)
        if m and l and (m.group(1), l) not in orgs:
            orgs.append((m.group(1), l[:40]))
    res["organizers"] = {"status": r.get("status"), "count": len(orgs), "list": orgs[:200]}
    for oid in ("4", "23"):
        r = P.get(op, f"https://www.av-event.jp/organizer/event_list/{oid}/")
        s, n = Q.dated_samples(r.get("text", ""), 3)
        res[f"org_{oid}"] = {"status": r.get("status"), "title": P.page_summary(r)["title"][:80], "dated_count": n,
                             "event_links": len(set(re.findall(r"/event/(\d+)/", r.get("text", ""))))}
    json.dump(res, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv)
