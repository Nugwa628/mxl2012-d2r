# D2R-XL 2012 Downloader

`D2R-XL-2012-Downloader.exe` installs, updates, repairs and uninstalls **D2R-XL 2012**, a free fan port of the Diablo II
mod Median XL 2012 to Diablo II: Resurrected, in your own D2R folder (`<D2R>\mods\mxl2012`). It checks every file
against the release's SHA-256, starts the game through D2RLoader, runs without administrator rights and sends no data
about you anywhere.

- The mod itself, its releases and its issue tracker: <https://github.com/Nugwa628/mxl2012-d2r>
- How the downloader works, where it writes, and how to remove everything again: [docs/launcher.md](docs/launcher.md)

## Code signing policy

Free code signing provided by SignPath.io, certificate by SignPath Foundation. Team roles, how a release is built and
signed, and the privacy statement: [docs/code-signing-policy.md](docs/code-signing-policy.md).

## Building

Windows, Visual Studio 2022 or newer with "Desktop development with C++", CMake 3.20+:

```
cmake -S launcher -B build/launcher -A x64
cmake --build build/launcher --config Release
build/launcher/tests/Release/launcher_tests.exe
python -m unittest discover -s tools -p "test_*.py"
```

The unsigned exe and its `.sha256` are in `build/launcher/Release`. `tools/sign_launcher.py` checks a signed copy
against that build. Releases are built and signed by `.github/workflows/sign-launcher.yml` (GitHub-hosted
`windows-latest`, then SignPath).

## Where this repository comes from

The downloader is developed inside the D2R-XL 2012 repository, which stays the source of truth. This repository is an
export of only the downloader's files, made by that repository's `tools/downloader_repo.py`; every commit here names the
D2R-XL 2012 commit it was exported from. Please report problems and send changes to
<https://github.com/Nugwa628/mxl2012-d2r/issues>. Paths in the docs that are not in this repository (other `docs/` pages,
`tools/` scripts) refer to that repository.

## License

MIT ([LICENSE](LICENSE)). The fonts and the 7z decoder keep their own open-source licences: [NOTICE.md](NOTICE.md).
D2R-XL 2012 is not affiliated with or endorsed by Blizzard Entertainment or Median XL's author.
