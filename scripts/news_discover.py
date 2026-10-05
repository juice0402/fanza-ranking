"""女優のニュース・イベント情報を、公式サイトから集められるかを調べる（下調べ用。2026-10-05。
運営者の「女優さんのニュースやイベント情報を、毎日の話題に。新鮮な情報がほしい」）。

対象: 所属事務所の公式サイト（agency_links.SITES）と、主なメーカーの公式サイト（候補。届かなければ、そう書く）。
サイトごとに: robots.txt で止められていないか・トップページ・RSS/Atom（<link rel="alternate">・/feed/）・
ニュース/イベント/スケジュールらしいページ（メニューのリンクの文字・URLから）を探し、ページごとに:
  日付の数・いちばん新しい日付・見出しの見本（日付の近くのリンクの文字。60文字まで・6件）・
  FANZAの名前と完全に同じ名前が入っている見出しの数・イベントの言葉（イベント・撮影会・サイン会・出演…）が入っている見出しの数
を調べる。保存するのは名前・URL・数・短い見出しの見本だけ（本文・画像は保存しない）。

使い方: python scripts/news_discover.py discovery/news.json
"""
import concurrent.futures
import json
import os
import re
import sys
import urllib.error
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agency_links as A  # noqa: E402

MAKERS = [
    ("S1 NO.1 STYLE", "https://s1s1s1.com/"),
    ("MOODYZ", "https://moodyz.com/"),
    ("アイデアポケット", "https://ideapocket.com/"),
    ("PREMIUM", "https://premium-beauty.com/"),
    ("kawaii*", "https://kawaiikawaii.jp/"),
    ("Madonna", "https://madonna-av.com/"),
    ("Attackers", "https://attackers.net/"),
    ("E-BODY", "https://av-e-body.com/"),
    ("MUTEKI", "https://muteki.jp/"),
    ("本中", "https://honnaka.jp/"),
    ("FALENO", "https://faleno.jp/"),
    ("プレステージ", "https://www.prestige-av.com/"),
    ("SODクリエイト", "https://www.sod.co.jp/"),
    ("ムーディーズ（別URL）", "https://www.moodyz.com/"),
    ("エスワン（別URL）", "https://www.s1s1s1.com/"),
]
NAV = re.compile(r"(news|topics|information|info|event|schedule|media|release|blog|ニュース|お知らせ|トピックス|インフォメーション|イベント|スケジュール|メディア|出演情報|最新情報|新着情報)", re.I)
DATE = re.compile(r"(20\d{2})\s*[./年-]\s*(\d{1,2})\s*[./月-]\s*(\d{1,2})")
EVENT = re.compile(r"(イベント|撮影会|サイン会|握手会|チェキ|発売記念|出演|生配信|配信|ライブ|ラジオ|テレビ|TV|雑誌|グラビア|写真集|デビュー|専属|引退|卒業|移籍|所属|誕生日|生誕|ファンミ|オフ会|舞台|映画|コラボ)")
SKIP = ("twitter.com", "x.com", "instagram.com", "youtube.com", "facebook.com", "tiktok.com", "line.me", "dmm.co.jp", "fanza.co.jp", "google.com")


def clean_date(m):
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if 1 <= mo <= 12 and 1 <= d <= 31:
        return f"{y:04d}-{mo:02d}-{d:02d}"
    return ""


def headlines(page_html, base_url):
    """日付の近く（すぐ前160文字・中・すぐ後120文字）にあるリンクの文字 → [(日付, 見出し, URL)]（新しい順）"""
    out, seen = [], set()
    for m in re.finditer(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", page_html, re.I | re.S):
        label = A.text_of(m.group(3))
        before = list(DATE.finditer(A.text_of(page_html[max(0, m.start() - 160):m.start()])))
        dm = DATE.search(label) or (before[-1] if before else None) or DATE.search(A.text_of(page_html[m.end():m.end() + 120]))
        if not dm:
            continue
        date = clean_date(dm)
        label = DATE.sub("", label).strip(" 　|｜-–—:：/")
        if not date or not (4 <= len(label) <= 120) or label in seen:
            continue
        seen.add(label)
        out.append((date, label[:60], urllib.parse.urljoin(base_url, A.htmllib.unescape(m.group(2)))))
    out.sort(key=lambda r: r[0], reverse=True)
    return out


def feed_items(text):
    items = []
    for block in re.findall(r"<(?:item|entry)\b[\s\S]*?</(?:item|entry)>", text, re.I):
        t = re.search(r"<title[^>]*>([\s\S]*?)</title>", block, re.I)
        d = re.search(r"<(?:pubDate|updated|published|dc:date)[^>]*>([\s\S]*?)</", block, re.I)
        title = A.text_of(re.sub(r"<!\[CDATA\[|\]\]>", "", t.group(1))) if t else ""
        date = ""
        if d:
            dm = DATE.search(d.group(1))
            if dm:
                date = clean_date(dm)
            else:
                mm = re.search(r"(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (20\d{2})", d.group(1))
                if mm:
                    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
                    date = f"{mm.group(3)}-{months.index(mm.group(2)) + 1:02d}-{int(mm.group(1)):02d}"
        if title:
            items.append((date, title[:60]))
    items.sort(key=lambda r: r[0], reverse=True)
    return items


def names_in(text, table):
    key = A.norm_name(text)
    found = set()
    for i in range(len(key)):
        for L in range(3, 11):
            part = key[i:i + L]
            if len(part) == L and part in table and len(table[part]) == 1:
                found.add(next(iter(table[part])))
    return sorted(found)


def summarize(rows, table):
    with_names = [r for r in rows if names_in(r[1], table)]
    with_event = [r for r in rows if EVENT.search(r[1])]
    return {
        "count": len(rows),
        "newest": rows[0][0] if rows else "",
        "recent_30d": sum(1 for r in rows if r[0] >= A.jst_today()[:8] + "01" or r[0] >= _days_ago(30)),
        "with_fanza_name": len(with_names),
        "with_event_word": len(with_event),
        "samples": [{"date": r[0], "title": r[1], "names": names_in(r[1], table)[:3]} for r in rows[:6]],
    }


def _days_ago(n):
    import datetime
    return (datetime.date.fromisoformat(A.jst_today()) - datetime.timedelta(days=n)).isoformat()


def survey(name, url, table):
    res = {"name": name, "url": url, "robots_ok": None, "top": "", "feeds": [], "pages": [], "error": ""}
    try:
        res["robots_ok"] = A.allowed(url)
        if not res["robots_ok"]:
            return res
        top = A.fetch_raw(url)
        res["top"] = "ok"
    except PermissionError:
        res["robots_ok"] = False
        return res
    except (urllib.error.URLError, OSError, ValueError) as e:
        res["error"] = f"{type(e).__name__}: {str(e)[:80]}"
        return res
    host = urllib.parse.urlsplit(url).netloc
    # RSS / Atom
    feeds = [urllib.parse.urljoin(url, A.htmllib.unescape(h)) for h in re.findall(r"<link\b[^>]*type\s*=\s*[\"']application/(?:rss|atom)\+xml[\"'][^>]*href\s*=\s*[\"']([^\"']+)", top, re.I)]
    feeds += [urllib.parse.urljoin(url, A.htmllib.unescape(h)) for h in re.findall(r"<link\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*type\s*=\s*[\"']application/(?:rss|atom)\+xml", top, re.I)]
    feeds.append(urllib.parse.urljoin(url, "/feed/"))
    for f in list(dict.fromkeys(feeds))[:3]:
        if urllib.parse.urlsplit(f).netloc != host:
            continue
        try:
            text = A.fetch_raw(f)
            items = feed_items(text)
            if items:
                res["feeds"].append({"url": f, **summarize(items, table)})
        except (PermissionError, urllib.error.URLError, OSError, ValueError):
            pass
    # ニュース・イベントらしいページ
    cands = []
    for href, label in A.links(top, url):
        p = urllib.parse.urlsplit(href)
        if p.netloc != host or any(s in p.netloc for s in SKIP):
            continue
        if NAV.search(label or "") or NAV.search(p.path):
            cands.append(href.split("#")[0])
    pages = [url] + list(dict.fromkeys(cands))[:5]
    for pg in pages:
        try:
            html_ = top if pg == url else A.fetch_raw(pg)
        except (PermissionError, urllib.error.URLError, OSError, ValueError) as e:
            res["pages"].append({"url": pg, "error": f"{type(e).__name__}"})
            continue
        rows = headlines(html_, pg)
        if rows:
            res["pages"].append({"url": pg, **summarize(rows, table)})
    return res


def safe_survey(name, url, table):
    """思わぬ失敗（読み込みの途中で切れた など）でも止めずに、そのサイトだけ「失敗」と書く"""
    try:
        return survey(name, url, table)
    except Exception as e:  # noqa: BLE001
        import traceback
        return {"name": name, "url": url, "robots_ok": None, "top": "", "feeds": [], "pages": [], "error": f"{type(e).__name__}: {str(e)[:80]}", "trace": traceback.format_exc()[-600:]}


def main(argv):
    out = argv[1] if len(argv) > 1 else "discovery/news.json"
    table = A.fanza_names()
    targets = [(s["name"], s["url"]) for s in A.SITES] + MAKERS
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda t: safe_survey(t[0], t[1], table), targets))
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"checked": A.jst_today(), "sites": results}, f, ensure_ascii=False, indent=1)
    for r in results:
        best = max([p for p in r["pages"] if "count" in p] + r["feeds"], key=lambda p: (p.get("recent_30d", 0), p.get("count", 0)), default=None)
        print(f"{r['name']}: robots={r['robots_ok']} {r['error']} feeds={len(r['feeds'])} pages={len(r['pages'])}"
              + (f" best={best['url']} n={best['count']} newest={best['newest']} 30d={best['recent_30d']} names={best['with_fanza_name']} event={best['with_event_word']}" if best else ""))


if __name__ == "__main__":
    try:
        main(sys.argv)
    except Exception:  # noqa: BLE001
        import traceback
        os.makedirs("discovery", exist_ok=True)
        with open("discovery/error.txt", "w", encoding="utf-8") as f:
            f.write(traceback.format_exc())
        raise
