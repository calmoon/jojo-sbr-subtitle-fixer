# JoJo's Bizarre Adventure: Steel Ball Run — Subtitle Name Restorer

> [!WARNING]
> **Spoilers.** The script and tests contain the full list of renamed and original
> names for the whole of *Steel Ball Run*, including characters and Stands that
> haven't shown up in the anime yet. Using the tool is spoiler-free (it never
> prints a name), but **don't read the source code** if you want to stay unspoiled.

Many names in *JoJo* are references to the author's favourite music, and the
official English localization renames a lot of them. Drop your episodes on this
tool and it writes an English subtitle file with the original names restored,
next to each video.

## Requirements

- Windows (also works on macOS/Linux from the command line)
- [Python 3.8+](https://www.python.org/downloads/)
- [FFmpeg](https://ffmpeg.org/) (`ffmpeg` and `ffprobe`): `winget install Gyan.FFmpeg`,
  or put `ffmpeg.exe` and `ffprobe.exe` next to the script

## Usage

Keep `fix_jojo_subtitles.py` and `Fix JoJo Subtitles.bat` in the same folder, then
drag one or more episode files, or a folder of episodes, onto **`Fix JoJo Subtitles.bat`**.

For each video the tool:

1. picks the standard English subtitle track (it skips SDH/CC, dubtitle, forced
   and signs/songs tracks, and falls back with a warning if there's no standard track),
2. restores the original names,
3. saves `<video name>.srt` (or `.ass` for styled tracks) next to the video.

Other ways to run it:

- Double-click the `.bat` to process every video in its own folder.
- Drag a `.srt` / `.ass` file on it to fix that file in place. Running the fix twice is harmless.
- From a terminal: `python fix_jojo_subtitles.py "episode.mkv" [more files or folders] [--no-pause]`

### Checking for missing names

```
python fix_jojo_subtitles.py --check-wiki
```

This downloads JoJo Wiki's name list and warns you if it documents renames this
version doesn't handle yet, which means the script probably needs updating. It
prints only counts, never names. If you also pass files or folders, it runs the
check first. If it confirms the name list is complete, it goes straight on to
processing. If it finds missing names, or the check couldn't run (no internet,
wiki page changed), it asks whether to process the files anyway (`y`/`n`).

### Words that might be names

A few of the localized names are also ordinary English words. Lowercase uses are
never touched. At the start of a sentence a capital letter proves nothing, so those
are left unchanged and listed by cue number and timestamp for you to check.

## Name list

The list covers every English rename documented on JoJo Wiki's
[Part 7 Name Variants](https://jojowiki.com/Template:Part_7_Name_Variants) page,
checked on 2026-10-17. To add a name, append a `(("Localized name",), "Original name")`
entry to `NAMES` in `fix_jojo_subtitles.py`.

## Tests

```
python tests/test_fixer.py          # edge cases
python tests/test_fixer.py --wiki   # also check every rename on the wiki page (needs internet)
```

The `--wiki` option runs the same check as `--check-wiki`, but lists the missing
names (spoilers) so you can add them to `NAMES`.

## License

[MIT](LICENSE)
