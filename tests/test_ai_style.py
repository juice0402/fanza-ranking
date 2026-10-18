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
check("右はしの矢印の飾り（content: '›' など）が無い", not re.search(r"content:\s*['\"][›»→>]['\"]", css),
      re.findall(r"content:\s*['\"][›»→>]['\"]", css)[:3])
check("英語の大文字の小見出し（text-transform: uppercase）が無い", "uppercase" not in css)
_tag = re.search(r"--r-tag:\s*(\d+)px", css)
_panel = re.search(r"--r-panel:\s*(\d+)px", css)
check("押せるもの・枠の角は小さく（ボタンは角ばった札＝4px まで・枠は6px まで。カプセルの丸にしない）",
      bool(_tag and _panel) and int(_tag.group(1)) <= 4 and int(_panel.group(1)) <= 6 and not re.search(r"border-radius:\s*(9{2,}|[1-9]\d{2,})px", css),
      (_tag and _tag.group(0), _panel and _panel.group(0)))
check("あちこちでふわっと出てくる動きが無い（動きは1つまで）", len(re.findall(r"@keyframes", css)) <= 1, len(re.findall(r"@keyframes", css)))

print("\n■ この点検そのもの")
check("絵文字の検出: ✨ ✅ 🚀 は見つけ、★ ☆ ✕ ▲ ▼ は見のがす", all(EMOJI.search(c) for c in "✨✅🚀💡⚡") and not any(EMOJI.search(c) for c in "★☆✕▲▼○●"))
_c = code_only("a // ✨\n/* ✨ */ 'https://x' {/* › */}")
check("コメントの中は調べない（URL の // は消さない）", "✨" not in _c and "›" not in _c and "'https://x'" in _c and _c.count("\n") == 1, repr(_c))

print(f"\n=== {passed}/{passed + failed} 合格 ===")
sys.exit(1 if failed else 0)
