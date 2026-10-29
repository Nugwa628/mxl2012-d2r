## What and why

<!-- One or two sentences. Link the issue it fixes. -->

## Follows Median XL?

- [ ] This matches Median XL 2012 (v005) (source or evidence: ...), or it is a documented deviation.
- [ ] Anything that cannot be ported has a row in `docs/unported.md`.

## Checks

- [ ] `py -3 tools/check_public.py` passes (no private paths, addresses or credentials).
- [ ] `py -3 -m compileall -q tools` passes; for plugin changes the unit tests in `plugin/tests` pass.
- [ ] No Blizzard or Median XL game files, saves, dumps or screenshots of game files in the diff.
- [ ] Tested in game, or this change cannot be (say which).

<!-- GitHub pull requests are applied to the forge (the main repository) by the maintainers; this PR will be closed
     with a link once that is done. -->
