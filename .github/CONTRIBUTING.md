# Contributing

Thanks for helping with D2R-XL 2012. Short version: report bugs, send small focused pull requests, and follow Median XL.

## Where the code lives

The **main repository is the forge** (<https://git.werdegames.com/WerdeGames/mxl2012-d2r>). The GitHub repository is a mirror
that takes issues and releases. **Pull requests on GitHub are welcome.** The maintainers apply accepted ones to the forge
(keeping your authorship) and the next mirror push brings them back; your PR is then closed with a link to the commit.
Because of that, keep PRs small, rebased on `main`, and one topic each.

## The rule: follow Median XL

The port follows Median XL 2012 (v005), not Diablo II: Resurrected, wherever the two differ (respecs, drops, caps, formulas,
ordering). That includes things D2R would do better. If a Median behaviour cannot be reproduced yet, do not drop it:

1. use the closest working approximation,
2. add a row to [docs/unported.md](../docs/unported.md) (area, what Median does, what the port does, status, what is
   needed). Status words are defined at the top of that file.

HD graphics first; the classic graphics mode is deferred. Custom art comes last: use the closest vanilla stand-in.
Strings go in the `mxl2012` namespace ([docs/strings-namespace.md](../docs/strings-namespace.md)).

## Building and testing

- Setup: [docs/setup.md](../docs/setup.md). Build: `py -3 tools/build.py` (the whole pipeline, never `txt_migrate.py`
  alone), plugin: `tools\build_plugin.ps1`.
- CI (on the forge) cross-builds the plugin, runs the unit tests in `plugin/tests`, byte-compiles `tools/` and runs
  `tools/check_public.py`. Run what you can locally.
- In-game checks (`tools/game_checks.py`, [docs/testing.md](../docs/testing.md)) need a game copy; if you change engine
  behaviour, describe how you tested it. Tests must run in background mode and must never steal mouse, keyboard or focus.
- Each plugin part has an off word in `mxl2012-core-off.txt` and a line in the `mxl` console command; see an existing part.

## What never goes into the repository

- Blizzard game files, extractions, memory dumps, saves (`.d2s`, `.d2i`), screenshots of game files.
- Median XL's original files outside the asset pack.
- Private details: user-home paths, machine names, addresses, tokens. `py -3 tools/check_public.py` finds them; fix
  the text instead of allowlisting it unless the hit is intentional.

## Style

Match the surrounding code: comment density, naming, idiom. C++20 in `plugin/`, Python 3.12 in `tools/`. Every hook checks
the bytes it patches before writing.

## Commits and licensing

Write a clear commit message. By contributing you agree your contribution is licensed under the project's
[MIT license](../LICENSE). Median XL's data and art are not ours to relicense: see [NOTICE.md](../NOTICE.md).
