"""メーカーの公式サイト（S1・MOODYZ・アイデアポケットなど）のイベント情報を、使ってよいか・読めるかの下調べ（2026-10-05。運営者の質問
「大手の S1・ムーディーズ・アイポケの情報が取れなかったのは痛い。年齢確認を一度クリアしてクッキーを残すとか、手段はないかな？」）。
作業用ブランチにだけ置く。調べるのは:
  1. robots.txt（自動の読み込みを断っていないか）
  2. 年齢確認の仕組み（クッキーだけで通る、ただの確認か。ログインなどではないか）
  3. 利用規約の、自動の収集・転載についての文
  4. イベントのページの有無と形（見出しの見本を数件）
  5. AVイベント情報の総合サイト（av-event.jp。ティーパワーズのイベントのリンク先）も同じように
結果は discovery/maker_probe.json（ページの本文は保存しない。短い見本だけ）。
"""
import html as htmllib
import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

UA = "Mozilla/5.0 (compatible; fanza-ranking-bot/1.0; +https://fanza-ranking.pages.dev/)"
SITES = [
    ("s1", "https://s1s1s1.com/"),
    ("moodyz", "https://moodyz.com/"),
    ("ideapocket", "https://ideapocket.com/"),
    ("premium", "https://premium-beauty.com/"),
    ("attackers", "https://attackers.net/"),
    ("madonna", "https://madonna-av.com/"),
    ("kawaii", "https://kawaiikawaii.jp/"),
    ("ebody", "https://av-e-body.com/"),
    ("fitch", "https://fitch-av.com/"),
    ("sod", "https://www.sod.co.jp/"),
    ("avevent", "https://www.av-event.jp/"),
]
TERM_WORDS = re.compile(r"転載|複製|自動|スクレイピング|クローラ|ロボット|機械的|収集|無断|引用|リンク")


def text_of(fragment):
    return re.sub(r"\s+", " ", htmllib.unescape(re.sub(r"<[^>]+>", " ", fragment or ""))).strip()


def opener():
    jar = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar)), jar


def get(op, url, extra_headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "ja", **(extra_headers or {})})
    try:
        with op.open(req, timeout=30) as res:
            raw = res.read(2_000_000)
            cs = res.headers.get_content_charset() or "utf-8"
            return {"status": res.status, "url": res.geturl(), "set_cookie": res.headers.get_all("Set-Cookie") or [],
                    "text": raw.decode(cs, errors="replace")}
    except urllib.error.HTTPError as e:
        return {"status": e.code, "url": url, "set_cookie": e.headers.get_all("Set-Cookie") or [] if e.headers else [], "text": ""}
    except Exception as e:  # noqa: BLE001
        return {"status": 0, "url": url, "error": f"{type(e).__name__}: {e}"[:200], "set_cookie": [], "text": ""}


def links(page, base):
    out = []
    for m in re.finditer(r"<a\b[^>]*?\bhref\s*=\s*([\"'])(.*?)\1[^>]*>(.*?)</a>", page, re.I | re.S):
        href = htmllib.unescape(m.group(2)).strip()
        if href and not href.startswith(("javascript:", "mailto:", "#")):
            out.append((urllib.parse.urljoin(base, href), text_of(m.group(3))[:60]))
    return out


def page_summary(r):
    t = r.get("text", "")
    title = re.search(r"<title\b[^>]*>(.*?)</title>", t, re.I | re.S)
    gate_words = [w for w in ("18歳", "年齢", "未成年", "age", "ENTER", "はい", "いいえ") if w in t]
    forms = [text_of(f)[:200] for f in re.findall(r"<form\b[\s\S]*?</form>", t, re.I)[:3]]
    gate_bits = []
    for m in re.finditer(r"(?i)(age[_-]?(?:check|verify|verification|auth|gate|confirm)[^\"'<>\s]{0,40}|adult[_-]?(?:check|confirm)[^\"'<>\s]{0,30}|document\.cookie[^;]{0,120})", t):
        if m.group(0) not in gate_bits:
            gate_bits.append(m.group(0)[:160])
        if len(gate_bits) >= 8:
            break
    return {"status": r.get("status"), "url": r.get("url"), "error": r.get("error", ""), "length": len(t),
            "title": text_of(title.group(1))[:100] if title else "", "gate_words": gate_words,
            "set_cookie": [c.split(";")[0][:80] for c in r.get("set_cookie", [])][:6], "forms": forms, "gate_bits": gate_bits}


def robots(base):
    op, _ = opener()
    r = get(op, base + "robots.txt")
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(r.get("text", "").splitlines() if r.get("status") == 200 else [])
    return r.get("status"), r.get("text", "")[:1500], rp


def main(argv):
    out_path = argv[1] if len(argv) > 1 else "discovery/maker_probe.json"
    res = {}
    for key, base in SITES:
        entry = {"base": base}
        status, robots_text, rp = robots(base)
        entry["robots_status"] = status
        entry["robots"] = robots_text
        entry["robots_top_allowed"] = rp.can_fetch(UA, base) if status == 200 else None
        op, jar = opener()
        top = get(op, base)
        entry["top"] = page_summary(top)
        lk = links(top.get("text", ""), top.get("url") or base)
        entry["gate_links"] = [l for l in lk if re.search(r"(?i)age|enter|yes|はい|18歳|入る|entrance|top\?|index", l[0] + " " + l[1])][:12]
        entry["event_links"] = [l for l in lk if re.search(r"(?i)event|イベント|schedule", l[0] + " " + l[1])][:15]
        entry["terms_links"] = [l for l in lk if re.search(r"(?i)terms|kiyaku|rule|policy|規約|ご利用|利用条件|注意", l[0] + " " + l[1])][:6]
        entry["cookies_after_top"] = [c.name for c in jar]
        # 年齢確認のリンク・フォームを1つ押したのと同じことをして、中身が変わるか（ただの確認か）を見る
        tried = []
        for url, label in entry["gate_links"][:3]:
            if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(base).netloc:
                continue
            if status == 200 and not rp.can_fetch(UA, url):
                tried.append({"url": url, "skipped": "robots"})
                continue
            r = get(op, url)
            tried.append({"url": url, "label": label, **page_summary(r), "cookies": [c.name for c in jar]})
            again = get(op, base)
            tried[-1]["top_again"] = page_summary(again)
            entry["event_links"] = entry["event_links"] or [l for l in links(again.get("text", ""), base) if re.search(r"(?i)event|イベント", l[0] + " " + l[1])][:15]
            break
        entry["gate_try"] = tried
        # イベントのページ（あれば1つ）の見出しの見本
        for url, label in entry["event_links"][:2]:
            if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(base).netloc:
                continue
            if status == 200 and not rp.can_fetch(UA, url):
                entry.setdefault("event_page", []).append({"url": url, "skipped": "robots"})
                continue
            r = get(op, url)
            heads = []
            for tag in ("h2", "h3", "h4", "p", "dt", "li"):
                for x in re.findall(r"<%s\b[^>]*>(.*?)</%s>" % (tag, tag), r.get("text", ""), re.I | re.S):
                    s = text_of(x)
                    if re.search(r"\d{1,2}[/月]\d{1,2}", s) and 6 < len(s) < 120 and s not in heads:
                        heads.append(s)
            entry.setdefault("event_page", []).append({"url": url, **page_summary(r), "dated_samples": heads[:8], "dated_count": len(heads)})
        # 利用規約（あれば1つ）の、自動の収集・転載についての文
        for url, label in entry["terms_links"][:2]:
            if urllib.parse.urlsplit(url).netloc != urllib.parse.urlsplit(base).netloc:
                continue
            r = get(op, url)
            sentences = [s.strip() for s in re.split(r"[。\n]", text_of(r.get("text", ""))) if TERM_WORDS.search(s) and 6 < len(s.strip()) < 220]
            entry.setdefault("terms", []).append({"url": url, "label": label, "status": r.get("status"), "sentences": sentences[:12]})
        res[key] = entry
        print(key, entry["robots_status"], entry["top"]["status"], entry["top"]["title"][:40], len(entry["event_links"]))
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main(sys.argv)
