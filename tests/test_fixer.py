"""
Tests for fix_jojo_subtitles.py.

    python tests/test_fixer.py          edge cases
    python tests/test_fixer.py --wiki   also check every English rename on JoJo Wiki

Only failures print names (spoilers).
"""
import os
import re
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fix_jojo_subtitles as fx  # noqa: E402

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

WIKI_URL = "https://jojowiki.com/Template:Part_7_Name_Variants?action=raw"

# (input, expected output, expect a "review" note)
CASES = [
    ("He roped the calf.", "He roped the calf.", False),
    ("Roped him in, didn't you?", "Roped him in, didn't you?", True),
    ("{\\an8}‎[STAND NAME] ROPED", "{\\an8}‎[STAND NAME] WIRED", False),
    ("They call it Roped.", "They call it Wired.", False),
    ("I know Laurence.", "I know L.A.", False),
    ("Laurence... wait.", "L.A.... wait.", False),
    ("Tubular Bells is here.", "Tubular Bells is here.", False),
    ("Mrs. Robinson came.", "Mrs. Robinson came.", False),
    ("Ask Robinson's men.", "Ask Mrs. Robinson's men.", False),
    ("Hey Yo! is near.", "Hey! Ya! is near.", False),
    ("the Sand\n‎Man arrives", "the Sandman arrives", False),
    ("<i>Tomb of the</i>\n<i>Noise 123</i>", "<i>Tomb of the</i>\n<i>Boom 1 2 3</i>", False),
    ("Wanderin’ Man!", "Ramblin’ Man!", False),
    ("Andrews and Andrew", "Andrews and Andre", False),
    ("‎[STAND MASTER] OYE", "‎[STAND MASTER] OYECOMOVA", False),
    ("Giddyup! Go!", "Giddyup! Go!", True),
    ("Get on Giddyup now.", "Get on Gets Up now.", False),
    ("The World is wide.", "The World is wide.", True),
    ("THE WORLD", "THE WORLD", False),
]

SRT = "1\n00:00:01,000 --> 00:00:02,000\nI saw Sand Man.\n\n2\n00:00:03,000 --> 00:00:04,000\nNothing here.\n"
SRT_FIXED = "1\n00:00:01,000 --> 00:00:02,000\nI saw Sandman.\n\n2\n00:00:03,000 --> 00:00:04,000\nNothing here.\n"


def test_cases():
    fails = 0
    for src, want, want_review in CASES:
        review = []
        got, _ = fx.fix_text(src, review)
        if got != want or bool(review) != want_review:
            fails += 1
            print(f"FAIL {src!r} -> {got!r} (expected {want!r}, review={bool(review)})")
    out, total, changed, review = fx.fix_srt(SRT)
    if out != SRT_FIXED or total != 1 or changed != ["cue 1 (00:00:01,000)"]:
        fails += 1
        print(f"FAIL fix_srt -> {out!r}")
    if fx.fix_srt(out)[1] != 0:
        fails += 1
        print("FAIL fix_srt is not idempotent")
    print(f"Edge cases: {len(CASES) + 2 - fails}/{len(CASES) + 2} passed")
    return fails


def _split_top(s):
    parts, depth, cur, i = [], 0, "", 0
    while i < len(s):
        two = s[i:i + 2]
        if two in ("{{", "[["):
            depth, cur, i = depth + 1, cur + two, i + 2
        elif two in ("}}", "]]"):
            depth, cur, i = depth - 1, cur + two, i + 2
        else:
            if s[i] == "|" and depth == 0:
                parts.append(cur)
                cur = ""
            else:
                cur += s[i]
            i += 1
    parts.append(cur)
    return parts


def _plain(s):
    s = re.sub(r"\{\{Nihongo\|([^|}]*)\|.*", r"\1", s)
    return re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", s).strip()


# Wiki rows that are not renames of an original name.
NOT_RENAMES = {
    "Sound Man", '"He who plays sound"',          # same wording in the Japanese original
    "STEEL BALL RUN JoJo's Bizarre Adventure",    # series title styling
}
# Rows whose restored form is a more specific original than the wiki section title.
EXPECTED = {
    "Tomb of the Noise 1": "Tomb of the Boom 1",
    "Snow Mountain's Spring": "Sugar Mountain's Spring",
}


def test_wiki():
    req = urllib.request.Request(WIKI_URL, headers={"User-Agent": "Mozilla/5.0"})
    lines = urllib.request.urlopen(req, timeout=30).read().decode("utf-8").split("\n")
    official, checked, fails = None, 0, 0
    for i, line in enumerate(lines):
        m = re.match(r"^\|(.+)\|$", line)
        if m and i + 1 < len(lines) and lines[i + 1].startswith("{{NV"):
            official = re.sub(r" \(Stand\)$", "", m.group(1))
            continue
        if not (line.lower().startswith("{{row") and "{{Flag|USA}}" in line):
            continue
        variant = _plain(_split_top(line[2:-2])[5])
        if variant == official or variant in NOT_RENAMES or variant.startswith("{{"):
            continue
        want = EXPECTED.get(variant, official)
        checked += 1
        got = fx.fix_text(f"We saw {variant} today.", [])[0]
        got_caps = fx.fix_text(f"[STAND NAME] {variant.upper()}", [])[0]
        if got != f"We saw {want} today." or got_caps != f"[STAND NAME] {want.upper()}":
            fails += 1
            print(f"FAIL wiki: {variant!r} -> {got!r} / {got_caps!r} (expected {want!r})")
    print(f"Wiki renames: {checked - fails}/{checked} restored")
    return fails


if __name__ == "__main__":
    failures = test_cases()
    if "--wiki" in sys.argv:
        failures += test_wiki()
    sys.exit(1 if failures else 0)
