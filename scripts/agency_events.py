"""所属事務所の公式サイトの「イベント情報」から、所属女優のイベント（発売記念イベント・サイン会・撮影会・来店など）の予定を集めて、
site/src/data/events.json に保存する（毎日）。

運営者の希望（2026-10-05）「女優さんのニュースとかイベント情報とかってどこかから情報入手できないかな？
できるだけ毎日の訪問に価値を見出してほしいから、新鮮な情報がほしい」→「本番に作る」。
下調べ（作業用ブランチの scripts/news_discover.py・events_probe.py）で、イベントの一覧が読める事務所を選んだ。
メーカーの公式サイトは、年齢確認の画面があって読めない・robots.txt で止められているので使わない。

決まり:
- 読むのは、robots.txt で止められていない、事務所の公式サイトのイベントの一覧のページ（RSS）だけ。1日1回・1ページずつ
  （agency_links.fetch_raw。同じサイトへは間をあける）。1件ずつのページは読まない。
- 保存するのは「日付・始まりの時刻・出る人（FANZAの名前）・事務所・種類（撮影会・サイン会など。見出しの言葉から決める）・
  短い見出し・会場の名前・情報を取ったページのURL・見かけた日」だけ。住所・電話・料金・画像・本文は保存しない。
- 出る人は、FANZA の名前と完全に同じ1人に決まる人だけ（agency_links と同じ考え方。人違いを防ぐ）:
  ・事務所が名前を別に書いている所（タグ・カテゴリ・「女優名」）は、その名前の全体が FANZA の名前と同じで、同じ名前が1人だけのとき
  ・見出しの中にしか名前が無い所は、その事務所の所属（agencies.json の、FANZA の名前と結びついた人）の名前が、見出しの中に、
    前後が区切られた形でそのまま出てくるとき（名前の一部・名字だけ・愛称では合わせない）
  だれとも結びつかないイベントは保存しない。
- 未成年を連想させる言葉のある見出しのイベントは保存しない（こちらから知らせる情報のため。claude_comments.py と同じ一覧）。
  行為などの言葉・同意の無い設定の言葉がある見出しは、見出しだけ空にする（種類・日付・会場は出す）。
- 中止のイベント・延期（振替の日が書かれていないもの）のイベントは保存しない。
- きょうから HORIZON_DAYS 日先までのイベントだけ。すぎたイベントは毎日消す。
- 読めない事務所・一覧の形が変わって1件も読めない事務所は、前の情報を残す（すぎたイベントは消す）。
- Python の標準ライブラリだけ。

使い方:
  python scripts/agency_events.py --update                  集め直して保存する（毎日の更新から）
  python scripts/agency_events.py --update --report 報告.json  読んだイベントの全部と、採らなかった理由も書き出す（作業用ブランチでの確認用）
"""
import html as htmllib
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agency_links as A  # noqa: E402
import claude_comments as CC  # noqa: E402  言葉の一覧（未成年を連想させる言葉・行為などの言葉）

EVENTS_PATH = os.environ.get("EVENTS_PATH", os.path.join(A.DATA_DIR, "events.json"))
HORIZON_DAYS = 60  # きょうから、この日数先までのイベントを保存する
TITLE_MAX = 40  # 見出しの長さ（これより長ければ切る）
PLACE_MAX = 30  # 会場の名前の長さ（これより長ければ保存しない）
NAMES_MAX = 6  # 1つのイベントに付ける人数の上限

# 事務所ごとのイベントの一覧（2026-10-05 に下調べ。所属の一覧を読んでいる事務所（agency_links.SITES）のうち、イベントの一覧が新しい所）
SOURCES = [
    {"key": "tpowers", "url": "https://www.t-powers.co.jp/event/", "parser": "tpowers"},  # 日付・場所の欄あり。名前は見出しの中だけ
    {"key": "capsule", "url": "https://capsule.bz/category/event/", "parser": "capsule"},  # 名前はタグ。日付・会場は見出しの中
    {"key": "esflat", "url": "http://www.style-1.jp/feed/", "parser": "rss"},  # お知らせのRSS（イベント情報のカテゴリだけ）。名前はカテゴリと「女優名」
    {"key": "life", "url": "https://life-promotion.com/blog/event/", "parser": "life"},  # 名前は見出しの中だけ。日付は「開催日時」か見出し
]

# 種類（見出しの言葉から。上から順に見る。どれにも当たらなければ「イベント」）。画面に出す文字は lib/events.js の EVENT_KINDS と同じ（テストで突き合わせ）
KINDS = [
    ("サイン・撮影会", r"サイン.{0,6}撮影|撮影.{0,6}サイン"),
    ("撮影会", r"撮影会"),
    ("サイン会", r"サイン"),
    ("握手会", r"握手"),
    ("チェキ会", r"チェキ"),
    ("オフ会", r"オフ会|宴会|飲み会|交流会|ファンミ"),
    ("トークイベント", r"トーク"),
    ("来店イベント", r"来店"),
    ("配信", r"配信|ライブチャット"),
    ("誕生日イベント", r"生誕|誕生日|バースデー|birthday"),
    ("発売記念イベント", r"発売記念|発売イベント|リリースイベント|リリイベ|リリース記念"),
]
KIND_NAMES = [k for k, _ in KINDS] + ["イベント"]

FULL_DATE = re.compile(r"(20\d{2})\s*[年/.\-]\s*(\d{1,2})\s*[月/.\-]\s*(\d{1,2})")
MD_DATE = re.compile(r"(?<![\d/.])(\d{1,2})\s*(?:月\s*(\d{1,2})\s*日|/\s*(\d{1,2})(?=\s*\(\s*[月火水木金土日祝]))")
TIME = re.compile(r"(?<![\d:])([01]?\d|2[0-3])\s*:\s*([0-5]\d)(?!\d)")
KANA_KANJI = re.compile(r"[぀-ヿ㐀-鿿々〆ー]")
# 名前のすぐ後ろに続いてよい言葉（敬称・イベントの言葉・助詞）。これ以外の、かな・漢字が続くときは、ほかの言葉の一部とみて合わせない
AFTER_OK = ("さん", "ちゃん", "くん", "様", "さま", "嬢", "氏", "の", "と", "が", "も", "は", "撮影", "サイン", "握手", "チェキ", "来店", "生誕",
            "誕生", "個人", "イベント", "発売", "単独", "出演", "主演", "トーク", "オフ会", "写真", "卒業", "引退", "初", "新作")
BEFORE_OK = ("女優", "専属", "新人", "主演", "出演", "ゲスト", "さん", "ちゃん", "くん", "様", "さま", "の", "と", "は")
# 【】の中が会場の名前らしいか（カプセルの見出しの最後の【】は、会場のこともメーカーのこともあるので、会場らしい言葉のあるときだけ会場にする）
PLACE_WORDS = re.compile(r"店|館|会場|ホール|スタジオ|劇場|書店|ショップ|SHOP|STUDIO|BOX|HALL", re.I)
# 住所らしい形（会場の欄に住所が書かれていることがある。住所は保存しない）
ADDRESS = re.compile(r"\d+\s*[-－−ー]\s*\d+|(?:都|道|府|県).{0,8}?(?:市|区|町|村).{0,12}\d|丁目|番地")
DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")
# 見出しに出さない言葉（claude_comments.py の一覧に無い、くだけた性的な言い方。種類・日付・会場は出す）
HIDE_WORDS = ["オカズ", "ヌキ", "エッチ", "えっち", "おっぱい", "ちくび", "乳"]
GENERIC_LABELS = {"イベント", "イベント情報", "EVENT", "PICK UP", "女優", "お知らせ", "NEWS", "ニュース", "メディア", "未分類"}


def nfkc(text):
    return unicodedata.normalize("NFKC", str(text or ""))


def iso(y, m, d):
    try:
        return date(int(y), int(m), int(d)).isoformat()
    except (TypeError, ValueError):
        return ""


def valid_day(text):
    """"YYYY-MM-DD" の形で、ありうる日付か"""
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", str(text or ""))
    return bool(m and iso(*m.groups()))


def in_range(day, today):
    """きょうから HORIZON_DAYS 日先までの日付か"""
    left = A.days_between(today, day)
    return left is not None and 0 <= left <= HORIZON_DAYS


def resolve_year(month, day, base):
    """年の書かれていない月日 → base（その記事を出した日・無ければきょう）にいちばん近い日"""
    b = date.fromisoformat(base)
    best = ""
    for y in (b.year - 1, b.year, b.year + 1):
        d = iso(y, month, day)
        if d and (not best or abs((date.fromisoformat(d) - b).days) < abs((date.fromisoformat(best) - b).days)):
            best = d
    return best


def find_date(text, base):
    """文の中のはじめの日付と、そのすぐ後ろの時刻 → ("YYYY-MM-DD", "HH:MM" | "")。無ければ ("", "")"""
    t = nfkc(text)
    m = FULL_DATE.search(t)
    day = iso(*m.groups()) if m else ""
    if not day:
        m = MD_DATE.search(t)
        if m:
            day = resolve_year(int(m.group(1)), int(m.group(2) or m.group(3)), base)
    if not day:
        return "", ""
    tm = TIME.search(t[m.end():m.end() + 24])
    hhmm = f"{int(tm.group(1)):02d}:{tm.group(2)}" if tm else ""
    return day, ("" if hhmm == "00:00" else hhmm)  # 「00:00」は時刻が決まっていない印として使われている


def kind_of(title):
    t = nfkc(title)
    for name, pattern in KINDS:
        if re.search(pattern, t, re.I):
            return name
    return "イベント"


def title_problem(text):
    """見出し（会場の名前）の見方: "minor"（未成年を連想させる。イベントごと保存しない）・"hide"（行為・同意の無い設定などの言葉。文字を出さない）・""（ふつう）"""
    reason = CC.title_block_reason({"title": text})
    if reason == "minor":
        return "minor"
    low = nfkc(text).lower()
    if reason or any(w.lower() in low for w in CC.EXPLICIT_WORDS + HIDE_WORDS):
        return "hide"
    return ""


def base_name(name):
    """「河北彩花（河北彩伽）」→「河北彩花」（かっこの中＝前の名前では合わせない）"""
    return re.split(r"[（(]", str(name or ""))[0].strip()


def names_in_title(title, roster):
    """見出しの中に、前後が区切られた形でそのまま出てくる所属の人（roster: FANZA の名前）。長い名前から先に見て、重なる短い名前は合わせない"""
    t = nfkc(title)
    found, spans = [], []
    for full in sorted(roster, key=lambda n: (-len(A.norm_name(base_name(n))), n)):
        base = base_name(full)
        if not A.name_ok(base):
            continue
        pattern = r"[\s・]?".join(re.escape(c) for c in A.norm_name(base))
        for m in re.finditer(pattern, t):
            s, e = m.span()
            if any(s < e2 and s2 < e for s2, e2 in spans):
                continue
            before, after = t[:s].rstrip(), t[e:].lstrip()
            if before and KANA_KANJI.match(before[-1]) and not before.endswith(BEFORE_OK) and t[s - 1:s].strip():
                continue
            if after and KANA_KANJI.match(after[0]) and not after.startswith(AFTER_OK) and t[e:e + 1].strip():
                continue
            found.append(full)
            spans.append((s, e))
            break
    return [n for _, n in sorted(zip(spans, found))]  # 見出しに出てくる順


def clean_place(place):
    """会場の名前（長すぎる・住所らしいものは保存しない）"""
    p = re.sub(r"[\s\u200b]+", " ", str(place or "")).strip(" 　")
    return p if 2 <= len(p) <= PLACE_MAX and not ADDRESS.search(nfkc(p)) else ""


def clean_title(title, names, place):
    """画面に出す短い見出し（日付・時刻・名前だけの【】・会場だけの【】を外す）"""
    t = re.sub(r"[\s\u200b]+", " ", str(title or "")).translate(DIGITS).strip()
    wd = r"\s*(?:[（(][月火水木金土日祝,、・]{1,7}(?:曜日?)?[）)])?"
    t = re.sub(r"(?:20\d{2}\s*[年/.]\s*)?\d{1,2}\s*[月/]\s*\d{1,2}\s*日?" + wd, " ", t)  # 10月3日（土）・10/3(土)
    t = re.sub(r"[,、・&＆〜～~\-－]\s*\d{1,2}\s*(?:日" + wd + r"|(?=[（(][月火水木金土日祝]))", " ", t)  # 「,18日（土,日）」「〜18(日)」（続きの日）
    t = re.sub(r"[（(][月火水木金土日祝,、・]{1,7}(?:曜日?)?[）)]|20\d{2}\s*年", " ", t)  # 残った曜日「（土,日）」「（土曜日）」・「2026年」
    t = re.sub(r"\d{1,2}\s*(?:[:：]\s*\d{2}|時(?:\s*\d{1,2}\s*分)?)\s*(?:[〜～~\-－]\s*(?:\d{1,2}\s*(?:[:：]\s*\d{2}|時(?:\s*\d{1,2}\s*分)?))?)?", " ", t)  # 18:00〜・12時~・11時30分～
    keys = {A.norm_name(base_name(n)) for n in names} | ({A.norm_name(place)} if place else set())

    def drop(m):
        return " " if A.norm_name(m.group(1)) in keys else m.group(0)

    t = re.sub(r"【([^】]{1,40})】", drop, t)
    if place:  # 「…＠会場」の会場は、会場の欄に出すので外す
        t = re.sub(r"\s*[@＠]\s*" + re.escape(place) + r"\s*$", "", t)
    t = re.sub(r"\s+", " ", t)
    t = re.sub(r"(?<=】) | (?=【)", "", t)
    t = re.sub(r"^[\s,、・&＆|｜\-－:：/／〜～~]+|[\s,、・&＆|｜\-－:：/／〜～~]+$", "", t)
    return t if len(t) <= TITLE_MAX else t[:TITLE_MAX - 1] + "…"


# ------------------------------------------------------------------
# 事務所ごとの読み取り（1件ずつ {title, url, date_text, place, names, base, media} に）
# ------------------------------------------------------------------

def _tag_text(block, pattern):
    m = re.search(pattern, block, re.I | re.S)
    return A.text_of(m.group(1)) if m else ""


def parse_tpowers(page, base_url):
    out = []
    for block in re.findall(r"<article\b[^>]*\bclass\s*=\s*[\"'][^\"']*p-schedule__list-item[^\"']*[\"'][^>]*>(.*?)</article>", page, re.I | re.S):
        a = re.search(r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"']+)", block, re.I)
        meta = {A.text_of(k): A.text_of(v) for k, v in re.findall(
            r"meta-item-heading[^>]*>(.*?)</div>\s*<div\b[^>]*meta-item-description[^>]*>(.*?)</div>", block, re.I | re.S)}
        cat = re.search(r"p-schedule__categpry--([a-z]+)", block)
        out.append({"title": _tag_text(block, r"<h3\b[^>]*>(.*?)</h3>"), "url": urllib.parse.urljoin(base_url, htmllib.unescape(a.group(1))) if a else "",
                    "date_text": meta.get("日付", ""), "place": meta.get("場所", ""), "names": [], "base": "",
                    "media": bool(cat and cat.group(1) != "event")})
    return out


def parse_capsule(page, base_url):
    out, seen = [], set()
    for block in re.findall(r"<li\b[^>]*>(.*?)</li>", page, re.I | re.S):
        if "category/event/" not in block or 'class="title"' not in block:
            continue
        m = re.search(r"<p\b[^>]*class=\"title\"[^>]*>\s*<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", block, re.I | re.S)
        if not m:
            continue
        url = urllib.parse.urljoin(base_url, htmllib.unescape(m.group(1)))
        if url in seen:
            continue
        seen.add(url)
        tags = re.search(r"<div\b[^>]*class=\"tag\"[^>]*>(.*?)</div>", block, re.I | re.S)
        names = [A.text_of(x) for x in re.findall(r"<a\b[^>]*>(.*?)</a>", tags.group(1), re.I | re.S)] if tags else []
        title = A.text_of(m.group(2))
        brackets = re.findall(r"【([^】]{2,40})】", title)
        place = brackets[-1] if brackets and title.rstrip().endswith("】") and PLACE_WORDS.search(brackets[-1]) \
            and A.norm_name(brackets[-1]) not in {A.norm_name(n) for n in names} else ""
        out.append({"title": title, "url": url, "date_text": "", "place": place, "names": names, "base": "", "media": False})
    return out


def _cdata(text):
    return A.text_of(re.sub(r"<!\[CDATA\[(.*?)\]\]>", r"\1", text or "", flags=re.S))


def parse_rss(page, base_url):
    out = []
    for item in re.findall(r"<item\b[^>]*>(.*?)</item>", page, re.I | re.S):
        cats = [_cdata(c) for c in re.findall(r"<category\b[^>]*>(.*?)</category>", item, re.I | re.S)]
        out.append(None)  # 数える（形が変わっていないか）ためだけの印。イベントでなければ None のまま
        if not any(c in ("イベント情報", "イベント") for c in cats):
            continue
        title = _cdata((re.search(r"<title\b[^>]*>(.*?)</title>", item, re.I | re.S) or [None, ""])[1])
        link = _cdata((re.search(r"<link\b[^>]*>(.*?)</link>", item, re.I | re.S) or [None, ""])[1])
        desc = _cdata((re.search(r"<description\b[^>]*>(.*?)</description>", item, re.I | re.S) or [None, ""])[1])
        pub = (re.search(r"<pubDate>\s*\w{3},\s*(\d{1,2})\s+(\w{3})\s+(\d{4})", item) or None)
        months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        base = iso(pub.group(3), months.index(pub.group(2)) + 1, pub.group(1)) if pub and pub.group(2) in months else ""
        names = [c for c in cats if c not in GENERIC_LABELS]
        m = re.search(r"女優名\s*(\S{2,20})", desc)
        if m:
            names.append(m.group(1))
        when = re.search(r"日時\s*(.{6,40}?)(?=\s+(?:女優名|住所|tel|TEL|URL|場所)|$)", desc)
        place = re.search(r"場所\s*(.{2,40}?)(?=\s+(?:日時|女優名|住所|tel|TEL|URL)|$)", desc)
        out[-1] = {"title": title, "url": urllib.parse.urljoin(base_url, link), "date_text": when.group(1) if when else "",
                   "place": place.group(1) if place else "", "names": names, "base": base, "media": False}
    return out


def parse_life(page, base_url):
    out = []
    for block in re.split(r"<div\s+class=\"blog\"\s*>", page)[1:]:
        h2 = re.search(r"<h2\b[^>]*>\s*<a\b[^>]*href\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", block, re.I | re.S)
        if not h2:
            continue
        posted = re.search(r"<p\b[^>]*class=\"date\"[^>]*>\s*(\d{4})\.(\d{1,2})\.(\d{1,2})", block)
        excerpt = _tag_text(block, r"</h2>\s*<p\b[^>]*>(.*?)</p>")
        when = re.search(r"開催日時\s*(20\d{2}\s*/\s*\d{1,2}\s*/\s*\d{1,2}[^\s]*(?:\s*\d{1,2}\s*[:：]\s*\d{2})?)", excerpt)
        place = re.search(r"会場情報\s*(.{2,30}?)\s+(?=住所|開催|参加|料金|内容|チケット|アクセス|タイム)", excerpt)
        out.append({"title": A.text_of(h2.group(2)), "url": urllib.parse.urljoin(base_url, htmllib.unescape(h2.group(1))),
                    "date_text": when.group(1) if when else "", "place": place.group(1) if place else "", "names": [],
                    "base": iso(*posted.groups()) if posted else "", "media": False})
    return out


PARSERS = {"tpowers": parse_tpowers, "capsule": parse_capsule, "rss": parse_rss, "life": parse_life}


# ------------------------------------------------------------------
# 1件ずつ、保存する形に（採らないときは理由）
# ------------------------------------------------------------------

def site_of(key):
    return next((s for s in A.SITES if s["key"] == key), None)


def make_row(entry, key, roster, table, today):
    """読んだ1件 → (保存する行 | None, 理由)"""
    site = site_of(key)
    title = str(entry.get("title") or "").strip()
    if not site or not title:
        return None, "見出しが無い"
    nt = nfkc(title)
    if re.search(r"中止|取りやめ|取り止め", nt) or ("延期" in nt and "振替" not in nt):
        return None, "中止・延期"
    if entry.get("media") and not entry.get("place"):
        return None, "会場の無いメディアの情報"
    problem = title_problem(title)
    if problem == "minor":
        return None, "見出しに未成年を連想させる言葉"
    day, time_ = find_date(entry.get("date_text") or "", entry.get("base") or today)
    if not day:
        day, time_ = find_date(title, entry.get("base") or today)
    if not day:
        return None, "日付が読めない"
    if not in_range(day, today):
        return None, "期間の外"
    names = []
    for n in entry.get("names") or []:
        fanza, _, _ = A.lookup(table, n)
        if fanza and fanza not in names:
            names.append(fanza)
    for n in names_in_title(title, roster):
        if n not in names:
            names.append(n)
    if not names:
        return None, "FANZAの名前と結びつく人がいない"
    place = clean_place(entry.get("place"))
    if place and title_problem(place):
        place = ""
    url = str(entry.get("url") or "")
    if not url.startswith(site["url"]):
        url = next(s["url"] for s in SOURCES if s["key"] == key)  # 事務所のサイトの外（イベントのサイトなど）へのリンクは、事務所の一覧のページにする
    row = {"date": day}
    if time_:
        row["time"] = time_
    row["names"] = names[:NAMES_MAX]
    row["agency"] = key
    row["kind"] = kind_of(title)
    shown = "" if problem else clean_title(title, names, place)
    if shown:
        row["title"] = shown
    if place:
        row["place"] = place
    row["url"] = url
    row["seen"] = today
    return clean_row(row), "採用"


def clean_row(r):
    """保存する1行（決まった項目だけ・形を確かめる）。使えなければ None"""
    if not isinstance(r, dict):
        return None
    key = r.get("agency")
    site = site_of(key)
    src = next((s for s in SOURCES if s["key"] == key), None)
    day = str(r.get("date") or "")
    names = [str(n).strip() for n in (r.get("names") or []) if isinstance(n, str) and n.strip() and len(n) <= 40] if isinstance(r.get("names"), list) else []
    url = str(r.get("url") or "")
    if not site or not src or not valid_day(day) or not names or not url.startswith(site["url"]) \
            or r.get("kind") not in KIND_NAMES or not valid_day(r.get("seen")):
        return None
    row = {"date": day}
    if re.match(r"^(?:[01]\d|2[0-3]):[0-5]\d$", str(r.get("time") or "")):
        row["time"] = r["time"]
    row["names"] = names[:NAMES_MAX]
    row["agency"] = key
    row["kind"] = r["kind"]
    title = str(r.get("title") or "").strip()
    if title and len(title) <= TITLE_MAX and not title_problem(title):
        row["title"] = title
    place = clean_place(r.get("place"))
    if place and not title_problem(place):
        row["place"] = place
    row["url"] = url
    row["seen"] = r["seen"]
    return row


def collect_source(src, roster, table, today):
    """1つの事務所のイベントの一覧を読む → (まとめ, 行, 1件ずつの記録)"""
    report = {"key": src["key"], "ok": False, "blocks": 0, "kept": 0, "error": ""}
    try:
        page = A.fetch_raw(src["url"])
    except Exception as e:  # noqa: BLE001 相手のサイトの不具合では止まらない（前の情報を残す）
        report["error"] = f"{type(e).__name__}: {e}"[:200]
        return report, [], []
    entries = PARSERS[src["parser"]](page, src["url"])
    report["ok"] = True
    report["blocks"] = len(entries)
    rows, log = [], []
    for entry in entries:
        if entry is None:
            continue
        row, why = make_row(entry, src["key"], roster, table, today)
        log.append({"agency": src["key"], "title": str(entry.get("title") or "")[:80], "result": why, **({"row": row} if row else {})})
        if row:
            rows.append(row)
    report["kept"] = len(rows)
    return report, rows, log


# ------------------------------------------------------------------
# 保存するデータ（前の情報を壊さない）
# ------------------------------------------------------------------

def load_previous(path=None):
    """前に保存したデータ。無ければ空。壊れていれば ValueError（上書きしない）"""
    path = path or EVENTS_PATH
    if not os.path.exists(path):
        return {"updated": "", "sites": [], "rows": []}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict) or not isinstance(data.get("rows"), list) or not isinstance(data.get("sites"), list):
        raise ValueError("events.json の形が違う")
    return data


def roster_of(agency_rows, key):
    return sorted({r["name"] for r in agency_rows if isinstance(r, dict) and r.get("agency") == key and r.get("name")})


def build_dataset(results, previous, today):
    """事務所ごとの今回の結果 {key: (まとめ, 行)} と前のデータ → 保存するデータ。
    読めた事務所は今回の行に入れ替え、読めなかった事務所（一覧の形が変わって1件も読めないときも）は前の行を残す。どちらも、すぎたイベントは消す"""
    prev_sites = {s.get("key"): s for s in previous.get("sites", []) if isinstance(s, dict)}
    prev_rows = [r for r in (clean_row(r) for r in previous.get("rows", [])) if r and in_range(r["date"], today)]
    sites, rows, fresh = [], [], False
    for src in SOURCES:
        key = src["key"]
        report, new_rows = results.get(key, ({"ok": False, "blocks": 0}, []))
        if report.get("ok") and report.get("blocks", 0) > 0:
            fresh = True
            sites.append({"key": key, "checked": today, "found": report["blocks"]})
            rows += [r for r in (clean_row(r) for r in new_rows) if r and in_range(r["date"], today)]
        else:
            old = prev_sites.get(key) or {}
            sites.append({"key": key, "checked": str(old.get("checked") or ""), "found": int(old.get("found") or 0)})
            rows += [r for r in prev_rows if r["agency"] == key]
    out, seen = [], set()
    for r in sorted(rows, key=lambda r: (r["date"], r.get("time", "99:99"), r["names"][0], r["agency"], r["url"])):
        k = (r["date"], r.get("time", ""), tuple(r["names"]), r.get("place", ""))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return {"updated": today if fresh else str(previous.get("updated") or ""), "sites": sites, "rows": out}


def dump_dataset(data):
    """1行に1件（毎日の差分が小さくなるように）"""
    rows = ",\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in data["rows"])
    sites = ",\n".join(json.dumps(s, ensure_ascii=False, separators=(",", ":")) for s in data["sites"])
    return f'{{"updated":{json.dumps(data["updated"])},\n"sites":[\n{sites}\n],\n"rows":[\n{rows}\n]}}\n'


def save_dataset(data, path=None):
    path = path or EVENTS_PATH
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(dump_dataset(data))
    os.replace(path + ".tmp", path)


def main(argv):
    if "--update" not in argv:
        print(__doc__)
        return 2
    today = A.jst_today()
    try:
        previous = load_previous()
        agencies = A.load_previous()
    except (OSError, ValueError) as e:
        print(f"events.json / agencies.json が読めないので、上書きしません: {e}")
        return 1
    table = A.fanza_names()
    results, logs = {}, []
    for src in SOURCES:
        try:
            report, rows, log = collect_source(src, roster_of(agencies.get("rows", []), src["key"]), table, today)
        except Exception as e:  # noqa: BLE001 1つの事務所の思わぬ失敗で、ほかの事務所の結果を捨てない
            report, rows, log = {"key": src["key"], "ok": False, "blocks": 0, "kept": 0, "error": f"{type(e).__name__}: {e}"[:200]}, [], []
        results[src["key"]] = (report, rows)
        logs += log
        name = site_of(src["key"])["name"]
        print(f"{name}: 一覧{'○' if report['ok'] else '×'} 読めた{report['blocks']}件 保存{report['kept']}件 {report.get('error', '')}")
    data = build_dataset(results, previous, today)
    save_dataset(data)
    if "--report" in argv and argv.index("--report") + 1 < len(argv):
        with open(argv[argv.index("--report") + 1], "w", encoding="utf-8") as f:
            json.dump({"today": today, "sites": [r for r, _ in results.values()], "entries": logs}, f, ensure_ascii=False, indent=1)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n### イベント情報（毎日）\n\n| 事務所 | 一覧 | 読めた | 保存 |\n|---|---|---|---|\n")
            for src in SOURCES:
                report, _ = results[src["key"]]
                f.write(f"| {site_of(src['key'])['name']} | {'○' if report['ok'] else '×'} | {report['blocks']} | {report['kept']} |\n")
            f.write(f"\n保存したイベント: {len(data['rows'])}件\n")
    print(f"イベント情報: {len(data['rows'])}件を保存しました")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
