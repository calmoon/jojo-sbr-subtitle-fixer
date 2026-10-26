"""
Tests for fix_jojo_subtitles.py.

    python tests/test_fixer.py          edge cases
    python tests/test_fixer.py --wiki   also check every English rename on JoJo Wiki

Only failures print names (spoilers).
"""
import os
import sys
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import fix_jojo_subtitles as fx  # noqa: E402

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

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
    ("His Stand, Tic tac boom!", "His Stand, Boku no Rhythm wo Kiitekure!", False),
    ("tic tac boom", "tic tac boom", False),
    ("They called him Joe Kid.", "They called him Joe Kidd.", False),
    ("Joe Kidd again.", "Joe Kidd again.", False),
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


def test_wiki():
    """Same check as `fix_jojo_subtitles.py --check-wiki`, but lists the missing names."""
    req = urllib.request.Request(fx.WIKI_RAW_URL, headers={"User-Agent": "Mozilla/5.0"})
    source = urllib.request.urlopen(req, timeout=30).read().decode("utf-8")
    renames = fx.wiki_renames(source)
    fails = 0
    for localized, original in renames:
        if not fx.handles_rename(localized, original):
            fails += 1
            print(f"FAIL wiki: {localized!r} is not restored to {original!r}")
    print(f"Wiki renames: {len(renames) - fails}/{len(renames)} restored")
    return fails


if __name__ == "__main__":
    failures = test_cases()
    if "--wiki" in sys.argv:
        failures += test_wiki()
    sys.exit(1 if failures else 0)
