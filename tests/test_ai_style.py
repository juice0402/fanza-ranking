"""AIっぽさゼロの点検（運営者の「サイト作りの原則」。2026-10-18）。
実行: python3 tests/test_ai_style.py
サイトの作り（site/src のページ・部品・部品の文言、site/public のスクリプト、site.css）に、AIの文章・デザインによく出るものが
入っていないかを調べる。コメント（// … や /* … */）の中は調べない。
作品のタイトル・ジャンル名などの FANZA のデータは、サイトの言葉ではないので調べない（ビルドしたページではなく、作りを調べる）。
Claude が書くコメント・週/月のまとめは、書く道具（scripts/claude_comments.py の text_problems）が同じ言葉を断る。"""
import glob
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
from claude_comments import AI_STYLE_RE  # noqa: E402

passed = failed = 0


def check(name, cond, detail=""):
    global passed, failed
    if cond:
        passed += 1
        print("  ✅ " + name)
    else:
        failed += 1
        print("  ❌ " + name + (f"  → {detail}" if detail else ""))


SITE = os.path.join(ROOT, "site")
FILES = sorted(
    glob.glob(os.path.join(SITE, "src", "pages", "**", "*.astro"), recursive=True)
    + glob.glob(os.path.join(SITE, "src", "pages", "**", "*.js"), recursive=True)
    + glob.glob(os.path.join(SITE, "src", "components", "*.astro"))
    + glob.glob(os.path.join(SITE, "src", "layouts", "*.astro"))
    + [p for p in glob.glob(os.path.join(SITE, "src", "lib", "*.js")) if not p.endswith("budoux-ja.js")]  # budoux-ja.js は文節の辞書（データ）
    + glob.glob(os.path.join(SITE, "public", "*.js"))
)
CSS = os.path.join(SITE, "src", "styles", "site.css")


def code_only(text):
    """コメントを除いた中身（行の数は変えない）"""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    text = re.sub(r"/\*.*?\*/", blank, text, flags=re.S)
    text = re.sub(r"<!--.*?-->", blank, text, flags=re.S)
    return re.sub(r"(?<![:\\'\"\w])//[^\n]*", blank, text)


# 使わない絵文字（AIの文章によく出るもの）。★☆（お気に入り）・✕（閉じる）・▲▼（順位の上下）・○● などの、意味のある記号はよい
EMOJI = re.compile("[\U0001F000-\U0001FAFF️⬀-⯿☀-☄☇-✔✖-➿]")
CHEVRON = re.compile("[›»]|&rsaquo;|&raquo;")


def scan(pattern, files=FILES):
    out = []
    for p in files:
        for n, line in enumerate(code_only(open(p, encoding="utf-8").read()).split("\n"), 1):
            for m in pattern.finditer(line):
                out.append(f"{os.path.relpath(p, SITE)}:{n} {m.group(0)}")
    return out


print("■ サイトの作り（ページ・部品・スクリプト）")
check(f"調べるファイルがある（{len(FILES)}）", len(FILES) > 50, len(FILES))
hits = scan(EMOJI)
check("AIの文章によく出る絵文字（✨🚀💡✅ など）が無い", not hits, hits[:5])
hits = scan(CHEVRON)
check("右はしの「›」「»」が無い", not hits, hits[:5])
hits = scan(re.compile(r"[^\n]*?→\s*<|>\s*←"))
check("リンクの文字の頭・おしりに矢印（→ ←）を付けない", not hits, hits[:5])
hits = scan(AI_STYLE_RE)
check("AIの文章によく出る言い方（おすすめ・ぜひ・便利・簡単・安心・コツ・しましょう・——）が無い", not hits, hits[:5])

print("\n■ デザイン（site.css）")
css = code_only(open(CSS, encoding="utf-8").read())
check("右はしの矢印の飾り（content: '›' '↗' など）が無い", not re.search(r"content:\s*['\"][›»→↗>]['\"]", css),
      re.findall(r"content:\s*['\"][›»→↗>]['\"]", css)[:3])
check("英語の大文字の小見出し（text-transform: uppercase）が無い", "uppercase" not in css)
_tag = re.search(r"--r-tag:\s*(\d+)px", css)
_panel = re.search(r"--r-panel:\s*(\d+)px", css)
check("押せるもの・枠の角は小さく（ボタンは角ばった札＝4px まで・枠は6px まで。カプセルの丸にしない）",
      bool(_tag and _panel) and int(_tag.group(1)) <= 4 and int(_panel.group(1)) <= 6 and not re.search(r"border-radius:\s*(9{2,}|[1-9]\d{2,})px", css),
      (_tag and _tag.group(0), _panel and _panel.group(0)))
check("あちこちでふわっと出てくる動きが無い（動きは1つまで）", len(re.findall(r"@keyframes", css)) <= 1, len(re.findall(r"@keyframes", css)))

print("\n■ 2026-10-22 に増えた決まり（色の帯・並べた切りかえ・右はしの「見る」・NEW などのバッジ）")


def css_rules(text):
    """（セレクタ, 中身）。@media の中の決まりも1つずつ"""
    for m in re.finditer(r"([^{}]+)\{([^{}]*)\}", text):
        yield " ".join(m.group(1).split()), m.group(2)


band = re.findall(r"border-(?:left|inline-start)\s*:\s*[2-9]\d*px\s+solid[^;]*|box-shadow\s*:\s*inset\s+[2-9]\d*px\s+0\s+0[^;]*", css)
check("四角やカードの左はしに、色の太い帯（線）をつけない", not band, band[:3])
# えらんだもの（:checked・aria-pressed・aria-current）だけ、地を黄色・紙の色でぬる切りかえ（タブ・セグメント）にしない。
# 印（::before・::after・-mark）の色はよい（申込用紙の「○」「□」）
filled = [sel for sel, body in css_rules(css)
          if re.search(r":checked|aria-pressed=['\"]true|aria-current", sel) and not re.search(r"::?(before|after)|-mark", sel)
          and re.search(r"(?<![-\w])background(-color)?\s*:\s*var\(--(pop|paper)\)", body)]
check("切りかえ・絞り込みは、えらんだものだけ地をぬる四角いボタンにしない（印の「○」「□」で示す）", not filled, filled[:3])
_jump = " ".join(body for sel, body in css_rules(css) if sel == ".hero-jump .chip-link")
check("トップ・売り場の探し方のリンク（.hero-jump）は、同じ大きさの四角いボタンを並べた形にしない（枠と地をつけない）",
      bool(_jump) and re.search(r"border\s*:\s*0", _jump) and re.search(r"background\s*:\s*none", _jump), _jump[:120])
hits = scan(re.compile(r">\s*(見る|詳しく|くわしく|詳細)\s*<|['\"](見る|詳しく|くわしく)['\"]"))
check("行の右はしに置く小さな「見る」「詳しく」のボタンが無い（ボタンの言葉は「FANZAで見る」のように何をするかを書く）", not hits, hits[:5])
hits = scan(re.compile(r"\bNEW\b|準備中|近日公開|COMING SOON|pop-(new|wait)"))
check("「NEW」「準備中」のような小さなバッジ・表紙の「新作」「予約」のシールが無い", not hits, hits[:5])

# 付箋・テープのようにななめにずらして並べない（2026-10-26 連絡 C-002）。矢印の形（45°・90°の倍数）はよい。
# セール特集のカードの表紙の束（.camp-cover）は、運営者が「かっこいいから、そのまま」と決めたので例外
tilted = [sel for sel, body in css_rules(css)
          for deg in re.findall(r"rotate\(\s*(-?[\d.]+)deg", body)
          if float(deg) % 45 and "camp-cover" not in sel]
check("付箋・テープのような、少しだけかたむけた飾りが無い（表紙の束 .camp-cover だけ例外）", not tilted, tilted[:3])

_fav = open(os.path.join(SITE, "public", "favicon.svg"), encoding="utf-8").read()
check("ファビコンは、色つきの角丸の四角（器）の中に絵を入れた形にしない（もの＝値札の形そのもの。2026-10-23）",
      not re.search(r"<rect[^>]*\bwidth=\"64\"[^>]*\bheight=\"64\"", _fav) and "<path" in _fav)

print("\n■ この点検そのもの")
check("かたむきの検出: rotate(-4deg) は見つけ、rotate(45deg)・rotate(-135deg) は見のがす", all(float(d) % 45 for d in ["-4", "5", "10"]) and not any(float(d) % 45 for d in ["45", "-135", "90"]))
check("絵文字の検出: ✨ ✅ 🚀 は見つけ、★ ☆ ✕ ▲ ▼ は見のがす", all(EMOJI.search(c) for c in "✨✅🚀💡⚡") and not any(EMOJI.search(c) for c in "★☆✕▲▼○●"))
_c = code_only("a // ✨\n/* ✨ */ 'https://x' {/* › */}")
check("左の帯の検出: border-left: 3px solid は見つけ、border-left: 1px は見のがす",
      bool(re.search(r"border-(?:left|inline-start)\s*:\s*[2-9]\d*px\s+solid", "border-left: 3px solid red")) and not re.search(r"border-(?:left|inline-start)\s*:\s*[2-9]\d*px\s+solid", "border-left: 1px solid red"))
check("コメントの中は調べない（URL の // は消さない）", "✨" not in _c and "›" not in _c and "'https://x'" in _c and _c.count("\n") == 1, repr(_c))

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
