"""
JoJo's Bizarre Adventure: Steel Ball Run - subtitle name restorer.

Drag one or more episode files (or folders containing them) onto this script.
For each video it:
  1. picks the standard English subtitle track (skipping SDH/CC, dubtitle,
     forced and signs/songs tracks),
  2. restores every name the official localization changed back to the
     author's original reference,
  3. saves the result next to the video, with the same base name.

Subtitle files (.srt / .ass / .ssa) can also be dropped; they are fixed in
place (running the fix twice is harmless).

--check-wiki  checks JoJo Wiki for documented renames this version doesn't
              handle yet, and warns if the name list needs updating.

Spoiler safety: the console output never shows any name, only counts, cue
numbers and timestamps.

Requires FFmpeg (ffmpeg + ffprobe) for video files:  winget install Gyan.FFmpeg
"""
import sys
import os
import re
import json
import glob
import shutil
import subprocess
import urllib.request

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ==============================================================================
# Localized name -> author's original name.
# Covers every English rename listed on https://jojowiki.com/Template:Part_7_Name_Variants
# (checked 2026-10-17). Not included: an in-story birth name and its native-tongue
# form, which are the same in the Japanese original, so they are not renames.
# Each entry: (localized form(s), original). Matching is case-aware: a form
# matches as written, Title Cased or ALL CAPS (eyecatches); lowercase text is
# never touched. ALL CAPS matches produce an ALL CAPS original.
# ==============================================================================
NAMES = [
    # Stands / eyecatches
    (("Tic Tac Boom",), "Boku no Rhythm wo Kiitekure"),
    (("Tomb of the Noise 123", "Tomb of the Noise 1 2 3", "Tomb of the Noise 1-2-3"), "Tomb of the Boom 1 2 3"),
    (("Tomb of the Noise",), "Tomb of the Boom"),
    (("Lasso Blues",), "Oh! Lonesome Me"),
    (("Filthy acts, at a reasonable price", "Filthy acts at a reasonable price",
      "Filthy acts, performed at a reasonable price", "Filthy acts performed at a reasonable price",
      "Devilish Deeds Done Damned Coldly"), "Dirty Deeds Done Dirt Cheap"),
    (("Frightening Monsters",), "Scary Monsters"),
    (("Stroboscope",), "Catch the Rainbow"),
    (("Silent Ways",), "In a Silent Way"),
    (("Millesimal Boy",), "20th Century BOY"),
    (("Man in Tatoo", "Man in Tattoo"), "TATOO YOU!"),
    (("The Abandoned",), "Civil War"),
    (("Tubular",), "Tubular Bells"),
    (("Roped",), "Wired"),
    (("Mando",), "Mandom"),
    (("Hey Yo!",), "Hey! Ya!"),
    (("Pitch Black Will",), "Dark Determination"),
    (("Axl",), "Axl RO"),
    (("Ticket of Tears",), "Ticket to Ride"),
    (("The World",), "THE WORLD"),

    # Characters / horses / racers
    (("Benny Boomboom",), "Benjamin Boomboom"),
    (("Andrew",), "Andre"),
    (("Laurence",), "L.A."),
    (("Boom Boom Family",), "Boomboom Family"),
    (("Sand Man",), "Sandman"),
    (("Robinson",), "Mrs. Robinson"),
    (("Oye",), "Oyecomova"),
    (("Shadow Rider",), "Ghost Rider in the Sky"),
    (("Flying Condor",), "El Condor Pasa"),
    (("Heavy Traffic",), "Crosstown Traffic"),
    (("Foxy Woman",), "Foxy Lady"),
    (("Tiny Wing",), "Little Wing"),
    (("Southern Chicken",), "Dixie Chicken"),
    (("Zen Monde",), "Zenyatta Mondatta"),
    (("Niel Berry",), "Nellyville"),
    (("Yacht Jet Black",), "Sloop John B"),
    (("European Express",), "Europe Express"),
    (("Wanderin' Man",), "Ramblin' Man"),
    (("Moon Vine",), "Moon Flower"),
    (("Nutcracker",), "Nut Rocker"),
    (("Waverider",), "Catch a Wave"),
    (("Endless Love",), "Love Unlimited"),
    (("Bamboo Hat Kid",), "Pork Pie Hat Kid"),
    (("Darkmore",), "Blackmore"),
    (("The Rotters' Club",), "Rotters' Club"),
    (("Nocturnal Fly",), "Nightfly"),
    (("Snow Mountain's Spring",), "Sugar Mountain's Spring"),
    (("Snow Mountain",), "Sugar Mountain"),
    (("Peggy",), "Peg"),
    (("Roxana",), "Roxanne"),
    (("Urmd Avdol",), "Urmd Avdul"),
    (("Dott Han",), "Dot Han"),
    (("Giddyup",), "Gets Up"),
    (("Steven Steele",), "Steven Steel"),
    (("Number One",), "♯1"),
    (("Doctor Ferdinand",), "Dr. Ferdinand"),
    (("Alternate World Diego", "Diego Brando (THE WORLD)"), "Parallel World Diego"),

    # Companies / places
    (("B&C Meatpacking Company",), "B&C Meat Company"),
    (("Horizontal Transcontinental Railroad Company",), "Horizontal Continental Railway Company"),
    (("Philadelphia Seaside", "Philadelphia Countryside"), "Philadelphia Coastline"),
]

# Localized forms that are also ordinary English. At the start of a sentence
# their capital letter proves nothing, so they are left alone there (unless the
# whole line is in caps, like an eyecatch) and reported for a manual check.
COMMON_WORDS = {
    "giddyup", "roped", "tubular", "nutcracker", "endless love", "the abandoned",
    "waverider", "heavy traffic", "snow mountain", "tiny wing", "silent ways",
    "stroboscope", "flying condor", "mando", "peggy", "number one", "the world",
}

VIDEO_EXTS = {".mkv", ".mp4", ".m4v", ".webm", ".avi", ".mov"}
SUB_EXTS = {".srt", ".ass", ".ssa"}
TEXT_SUB_CODECS = {"subrip", "srt", "ass", "ssa", "webvtt", "mov_text", "text"}

# Formatting that may sit inside a name split across lines: tags, direction marks, ASS \N.
_FMT = r"(?:<[^>]*>|\{[^}]*\}|[\u200e\u200f])"
SEP = rf"{_FMT}*(?:\s|\\[Nn])+(?:{_FMT}|\s|\\[Nn])*"
_SEP_RE = re.compile(f"({SEP})")
_STRIP_FMT_RE = re.compile(_FMT)


def _norm(text):
    """Collapse separators/formatting to single spaces and unify apostrophes."""
    return _SEP_RE.sub(" ", text).replace("\u2019", "'").strip()


def _title(text):
    return " ".join(w[:1].upper() + w[1:] for w in text.split(" "))


def _build_table():
    table = {}  # lowercase localized form -> (allowed casings, original)

    def add(form, original):
        casings = {form, form.upper(), _title(form), form[:1].upper() + form[1:]}
        table[form.lower()] = (casings, original)

    for forms, original in NAMES:
        for form in forms:
            add(form, original)
    # Text already showing the original must never be re-replaced
    # (keeps the fix idempotent, e.g. when the original contains the localized form).
    for forms, original in NAMES:
        if any(f.lower() in original.lower() for f in forms) and original.lower() not in table:
            add(original, original)

    alternatives = []
    for key in sorted(table, key=len, reverse=True):
        words = [re.escape(w).replace("'", "['\u2019]") for w in key.split(" ")]
        alternatives.append(SEP.join(words))
    pattern = re.compile(
        r"(?<!\w)(?P<name>" + "|".join(alternatives) + r")(?!\w)(?P<dot>\.(?!\.))?",
        re.IGNORECASE,
    )
    return table, pattern


TABLE, PATTERN = _build_table()


def _rejoin(replacement, separators):
    """Keep line breaks/tags that were inside the original match."""
    if all(s == " " for s in separators):
        return replacement
    words = replacement.split(" ")
    out = words[0]
    for i, word in enumerate(words[1:]):
        out += (separators[i] if i < len(separators) else " ") + word
    return out


def _is_sentence_start(prefix):
    prefix = _STRIP_FMT_RE.sub("", prefix).replace("\\N", " ").rstrip(" \t\r\n\"'\u201c\u2018-\u2013\u2014")
    return prefix == "" or prefix[-1] in ".!?\u2026:"


def fix_text(text, review):
    """Restore names in one cue's text. Returns (new_text, names_restored)."""
    count = 0

    def repl(m):
        nonlocal count
        name, dot = m.group("name"), m.group("dot") or ""
        parts = _SEP_RE.split(name)
        words, separators = parts[0::2], parts[1::2]
        normalized = _norm(" ".join(words))
        entry = TABLE.get(normalized.lower())
        if not entry or normalized not in entry[0]:
            return m.group(0)  # wrong casing: an ordinary word, not a name
        original = entry[1]
        if normalized in (original, original.upper()):
            return m.group(0)  # already the original

        is_caps = normalized == normalized.upper() and normalized != normalized.lower()
        if normalized.lower() in COMMON_WORDS:
            line_start = text.rfind("\n", 0, m.start()) + 1
            line_end = text.find("\n", m.end())
            line = _STRIP_FMT_RE.sub("", text[line_start:line_end if line_end != -1 else len(text)])
            eyecatch = is_caps and line == line.upper()
            if not eyecatch and _is_sentence_start(text[:m.start()]):
                review.append(1)
                return m.group(0)

        new = original.upper() if is_caps else original
        if "\u2019" in name:
            new = new.replace("'", "\u2019")
        if new.endswith("."):
            dot = ""  # "Laurence." must not become "L.A.."
        count += 1
        return _rejoin(new, separators) + dot

    return PATTERN.sub(repl, text), count


_TIMING_RE = re.compile(r"^\s*\d+:\d+:\d+[,.]\d+\s*-->")


def fix_srt(content):
    """Returns (fixed_content, names_restored, changed_cue_labels, review_cue_labels)."""
    blocks = re.split(r"(\n[ \t]*\n)", content)
    total, changed, review_cues = 0, [], []
    for i in range(0, len(blocks), 2):
        lines = blocks[i].split("\n")
        t = next((j for j, l in enumerate(lines) if _TIMING_RE.match(l)), None)
        if t is None:
            continue
        label = f"cue {lines[t - 1].strip() if t > 0 else '?'} ({lines[t].split('-->')[0].strip()})"
        head, body = "\n".join(lines[:t + 1]), "\n".join(lines[t + 1:])
        review = []
        new_body, n = fix_text(body, review)
        if n:
            total += n
            changed.append(label)
            blocks[i] = head + "\n" + new_body
        if review:
            review_cues.append(label)
    return "".join(blocks), total, changed, review_cues


def fix_ass(content):
    """Same as fix_srt, for ASS/SSA: only the text field of Dialogue lines is touched."""
    lines = content.split("\n")
    total, changed, review_cues = 0, [], []
    for i, line in enumerate(lines):
        if not line.startswith("Dialogue:"):
            continue
        fields = line.split(",", 9)
        if len(fields) < 10:
            continue
        label = f"line {i + 1} ({fields[1].strip()})"
        review = []
        new_text, n = fix_text(fields[9].replace("\\N", "\n"), review)
        if n:
            total += n
            changed.append(label)
            fields[9] = new_text.replace("\n", "\\N")
            lines[i] = ",".join(fields)
        if review:
            review_cues.append(label)
    return "\n".join(lines), total, changed, review_cues


# ==============================================================================
# Wiki check
# ==============================================================================
WIKI_RAW_URL = "https://jojowiki.com/Template:Part_7_Name_Variants?action=raw"
REPO_URL = "https://github.com/calmoon/jojo-sbr-subtitle-fixer"

# English wiki rows that are deliberately not applied: same wording in the
# Japanese original, or a styling of the series title.
WIKI_NOT_RENAMES = {"Sound Man", '"He who plays sound"', "STEEL BALL RUN JoJo's Bizarre Adventure"}
# Rows restored to a more specific original than their wiki section title.
WIKI_EXPECTED = {
    "Tomb of the Noise 1": "Tomb of the Boom 1",
    "Snow Mountain's Spring": "Sugar Mountain's Spring",
}


def _split_wiki_cells(s):
    """Split template arguments on '|' outside nested {{...}} / [[...]]."""
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


def wiki_renames(page_source):
    """Parse the wiki page source into [(localized English name, original name)]."""
    lines = page_source.split("\n")
    official, renames = None, []
    for i, line in enumerate(lines):
        m = re.match(r"^\|(.+)\|$", line)
        if m and i + 1 < len(lines) and lines[i + 1].startswith("{{NV"):
            official = re.sub(r" \(Stand\)$", "", m.group(1))
            continue
        if official is None or not (line.lower().startswith("{{row") and "{{Flag|USA}}" in line):
            continue
        cells = _split_wiki_cells(line[2:-2])
        if len(cells) < 6:
            continue
        variant = re.sub(r"\{\{Nihongo\|([^|}]*)\|.*", r"\1", cells[5])
        variant = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]*)\]\]", r"\1", variant).strip()
        if variant == official or variant in WIKI_NOT_RENAMES or variant.startswith("{{"):
            continue  # "{{..." rows are abbreviations identical to the original
        renames.append((variant, WIKI_EXPECTED.get(variant, official)))
    return renames


def handles_rename(localized, original):
    """True if the name is restored both in dialogue and in an ALL CAPS eyecatch."""
    return (fix_text(f"We saw {localized} today.", [])[0] == f"We saw {original} today."
            and fix_text(f"[STAND NAME] {localized.upper()}", [])[0] == f"[STAND NAME] {original.upper()}")


def check_wiki():
    """Warn if JoJo Wiki documents renames this version doesn't handle. Prints no names.

    Returns True if up to date, False if renames are missing, None if the check failed.
    """
    print("\nChecking JoJo Wiki for documented renames...")
    try:
        req = urllib.request.Request(WIKI_RAW_URL, headers={"User-Agent": "Mozilla/5.0 (jojo-sbr-subtitle-fixer)"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            source = resp.read().decode("utf-8", errors="replace")
    except Exception as e:
        print(f"  [ERROR] Could not download the wiki page: {e}")
        return None
    renames = wiki_renames(source)
    if len(renames) < len(NAMES):
        print("  [WARNING] Found fewer renames on the wiki than expected; the page layout may have")
        print("  changed, so this check couldn't be done reliably.")
        return None
    missing = sum(not handles_rename(localized, original) for localized, original in renames)
    if missing:
        print(f"  [WARNING] {missing} of {len(renames)} renames documented on the wiki are not handled by")
        print(f"  this version. The name list probably needs updating: {REPO_URL}")
        print("  (Names aren't shown, to avoid spoilers. tests/test_fixer.py --wiki lists them.)")
        return False
    print(f"  Up to date: all {len(renames)} renames documented on the wiki are handled.")
    return True


# ==============================================================================
# FFmpeg helpers
# ==============================================================================
def find_tool(tool_name):
    """Find an executable next to this script, in PATH, or in common install folders."""
    exe = f"{tool_name}.exe" if os.name == "nt" else tool_name
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), exe)
    if os.path.isfile(local):
        return local
    found = shutil.which(tool_name)
    if found:
        return found
    candidates = [
        os.path.join(base, "ffmpeg", "bin", exe)
        for base in (r"C:\Program Files", r"C:\Program Files (x86)", "C:\\")
    ]
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if local_app_data:
        candidates += glob.glob(os.path.join(local_app_data, "Microsoft", "WinGet", "Links", exe))
        candidates += glob.glob(os.path.join(local_app_data, "Microsoft", "WinGet", "Packages", "*", "*", "bin", exe))
    candidates += [os.path.join(os.environ.get("ProgramData", r"C:\ProgramData"), "chocolatey", "bin", exe),
                   os.path.join(os.path.expanduser("~"), "scoop", "shims", exe)]
    return next((c for c in candidates if os.path.isfile(c)), None)


_SDH_RE = re.compile(r"\b(sdh|cc|hi|hoh)\b|hearing|closed.?caption", re.IGNORECASE)
_DUB_RE = re.compile(r"dub", re.IGNORECASE)
_SKIP_RE = re.compile(r"forced|\bsigns?\b|\bsongs?\b|commentary|karaoke", re.IGNORECASE)


def pick_english_stream(video_path, ffprobe_exe):
    """Returns (stream_index, codec, title, kind) or None. kind: standard/SDH/dubtitle."""
    cmd = [ffprobe_exe, "-v", "error", "-select_streams", "s",
           "-show_entries", "stream=index,codec_name:stream_tags=language,title:stream_disposition",
           "-of", "json", video_path]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0:
        return None
    try:
        streams = json.loads(res.stdout.decode("utf-8", errors="replace")).get("streams", [])
    except ValueError:
        return None

    standard, sdh, dub = [], [], []
    for s in streams:
        tags = {k.lower(): v for k, v in s.get("tags", {}).items()}
        disp = s.get("disposition", {})
        lang = str(tags.get("language", "")).lower()
        title = str(tags.get("title", ""))
        if not (lang in ("en", "eng") or lang.startswith("en-") or "english" in title.lower()):
            continue
        if s.get("codec_name") not in TEXT_SUB_CODECS:
            continue  # image-based (PGS/VobSub) can't be edited as text
        if disp.get("forced") or disp.get("comment") or _SKIP_RE.search(title):
            continue
        info = (s["index"], s.get("codec_name"), title, bool(disp.get("default")))
        if _DUB_RE.search(title):
            dub.append(info)
        elif disp.get("hearing_impaired") or _SDH_RE.search(title):
            sdh.append(info)
        else:
            standard.append(info)

    for kind, group in (("standard", standard), ("SDH", sdh), ("dubtitle", dub)):
        if group:
            group.sort(key=lambda x: not x[3])  # prefer the default-flagged track
            index, codec, title, _ = group[0]
            return index, codec, title, kind
    return None


def extract_stream(video_path, ffmpeg_exe, index, codec):
    as_ass = codec in ("ass", "ssa")
    fmt = "ass" if as_ass else "srt"
    cmd = [ffmpeg_exe, "-v", "error", "-nostdin", "-i", video_path,
           "-map", f"0:{index}", "-c:s", fmt, "-f", fmt, "-"]
    res = subprocess.run(cmd, capture_output=True)
    if res.returncode != 0 or not res.stdout.strip():
        err = res.stderr.decode("utf-8", errors="replace").strip().splitlines()
        return None, None, (err[-1] if err else "no subtitle data")
    text = res.stdout.decode("utf-8", errors="replace").lstrip("\ufeff")
    return text.replace("\r\n", "\n").replace("\r", "\n"), ("." + fmt), None


# ==============================================================================
# Processing
# ==============================================================================
def save_and_report(content, ext, out_path):
    fixer = fix_ass if ext in (".ass", ".ssa") else fix_srt
    fixed, total, changed, review = fixer(content)
    with open(out_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write(fixed.rstrip("\n") + "\n")
    print(f"  Saved: {os.path.basename(out_path)}")
    print(f"  Restored {total} name(s) in {len(changed)} cue(s).")
    if review:
        print(f"  {len(review)} cue(s) start a sentence with a word that might be a renamed name;")
        print("  left unchanged, worth a quick look:")
        for label in review:
            print(f"    - {label}")
    return True


def process_video(video_path, ffmpeg_exe, ffprobe_exe):
    print(f"\nProcessing: {os.path.basename(video_path)}")
    if not ffmpeg_exe or not ffprobe_exe:
        print("  [ERROR] FFmpeg (ffmpeg + ffprobe) not found. Install it with: winget install Gyan.FFmpeg")
        print("          or put ffmpeg.exe and ffprobe.exe next to this script.")
        return False
    stream = pick_english_stream(video_path, ffprobe_exe)
    if stream is None:
        print("  [ERROR] No text-based English subtitle track found.")
        return False
    index, codec, title, kind = stream
    print(f"  Using stream #{index} ({codec}{', ' + title if title else ''}).")
    if kind != "standard":
        print(f"  [WARNING] No standard English track; falling back to the {kind} track.")
    content, ext, err = extract_stream(video_path, ffmpeg_exe, index, codec)
    if content is None:
        print(f"  [ERROR] Failed to extract subtitle track: {err}")
        return False
    return save_and_report(content, ext, os.path.splitext(video_path)[0] + ext)


def process_subtitle(sub_path):
    print(f"\nProcessing: {os.path.basename(sub_path)}")
    with open(sub_path, "r", encoding="utf-8-sig", errors="replace") as f:
        content = f.read().replace("\r\n", "\n").replace("\r", "\n")
    return save_and_report(content, os.path.splitext(sub_path)[1].lower(), sub_path)


def collect_targets(args):
    targets = []
    for arg in args:
        path = os.path.abspath(arg.strip('"'))
        if os.path.isdir(path):
            targets += sorted(p for p in glob.glob(os.path.join(glob.escape(path), "*"))
                              if os.path.splitext(p)[1].lower() in VIDEO_EXTS)
        elif os.path.isfile(path):
            targets.append(path)
        else:
            print(f"[WARNING] Not found, skipped: {arg}")
    return targets


def confirm(question):
    """Ask until the user answers yes or no. Without an interactive console, answers no."""
    if not (sys.stdin and sys.stdin.isatty()):
        print(f"{question} No answer possible (no interactive console), so: no.")
        return False
    while True:
        try:
            answer = input(f"{question} [y/n] ").strip().lower()
        except EOFError:
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("n", "no"):
            return False
        print("Please answer y or n.")


def main():
    args = [a for a in sys.argv[1:] if a not in ("--no-pause", "--check-wiki")]
    print("=" * 60)
    print(" JoJo's Bizarre Adventure: Steel Ball Run")
    print(" Subtitle Extractor & Original Name Restorer")
    print("=" * 60)

    up_to_date = None
    if "--check-wiki" in sys.argv:
        up_to_date = check_wiki()
        if not args:  # only the check was asked for
            return 0 if up_to_date else 1

    # No arguments (double-click): process the videos in this script's folder.
    targets = collect_targets(args or [os.path.dirname(os.path.abspath(__file__))])
    if not targets:
        print("No video files found.")
        print("Usage: drag episode files (.mkv, .mp4, ...) or folders onto this script.")
        return 1

    # Only an outdated name list needs a decision; a failed check just warned above.
    if up_to_date is False and not confirm(f"\nProcess {len(targets)} file(s) anyway?"):
        print("Nothing processed.")
        return 1

    needs_ffmpeg = any(os.path.splitext(t)[1].lower() not in SUB_EXTS for t in targets)
    ffmpeg_exe = find_tool("ffmpeg") if needs_ffmpeg else None
    ffprobe_exe = find_tool("ffprobe") if needs_ffmpeg else None

    print(f"Found {len(targets)} file(s) to process.")
    ok = 0
    for target in targets:
        try:
            if os.path.splitext(target)[1].lower() in SUB_EXTS:
                ok += process_subtitle(target)
            else:
                ok += process_video(target, ffmpeg_exe, ffprobe_exe)
        except Exception as e:  # keep going with the other files
            print(f"  [ERROR] {type(e).__name__}: {e}")

    print("\n" + "=" * 60)
    print(f"Done: {ok}/{len(targets)} subtitle file(s) created.")
    print("=" * 60)
    return 0 if ok == len(targets) else 1


if __name__ == "__main__":
    code = main()
    # Keep the window open when launched by drag-and-drop / double-click.
    if "--no-pause" not in sys.argv and sys.stdin and sys.stdin.isatty():
        try:
            input("\nPress Enter to close...")
        except EOFError:
            pass
    sys.exit(code)
