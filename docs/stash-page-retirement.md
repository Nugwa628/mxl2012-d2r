# Personal stash page 2 retirement (alpha update with CharmInv)

The alpha owner explicitly chose deletion instead of migration on 2026-11-10. This release removes the `stash2`
provider and both stash navigation arrows (the CharmInv change), then gives native custom page 6 to CharmInv.
Items left on the retired personal page are deleted. The developer menu can recreate them. There is no migration,
recovery page, automatic transfer or charm implementation in this lane.

## Where cleanup happens and why

`RetireStashPage` runs synchronously during mxl2012-core initialization, before character select, for the supported
93847 build. It resolves only the active mod's `modinfo.json` savepath under Saved Games/Diablo II Resurrected/mods;
relative parent traversal and absolute paths are refused, and it never recurses. The launcher and direct D2RLoader
starts therefore use the same behavior. The installer does not modify saves, and Python is not required at runtime.

D2RLoader owns restoration of custom-page items and can refuse the character before a game-thread callback runs.
Deleting items after character load would be too late and could expose old items through CharmInv. Offline deletion
also avoids placement, item creation and transaction rollback issues.

## Exact scope and origin

The reader accepts D2RLoader extended schema `0x44520005` with consistent D2RL v2 sidecar hashes, size and checksum.
Only top-level player items with stored location 0 and serialized page **7** (native page **6**) are removed, including
socket children belonging to those items. Remaining items are copied as raw byte ranges. Character header, stats,
skills, inventory, personal page 1, cube, equipment, belt, corpse, mercenary and golem bytes are preserved, except the
save size/checksum and player item count. Shared `.d2i` files are never opened by cleanup.

Origin is character-level, never guessed from item code, charm type or coordinates:

- A sidecar recording `d2rl-charm-inv.dll` is already a CharmInv character: preserve every page-6 item, even non-charms.
- A sidecar recording mxl2012-core **0.1.19 or newer** also preserves page 6. This is the one-time completion marker
  in D2RLoader's existing plugin-version field. It survives the loader rewriting the provider list after a refused
  load with CharmInv temporarily absent. Keep this threshold fixed in future releases.
- Earlier mxl2012-core saves without either origin record undergo cleanup. A save with no retired items is byte-identical
  and neither save nor sidecar is written. D2RLoader writes its normal new plugin records when it loads/saves the character.
- Missing sidecars (untagged retail/legacy characters) are never edited. Invalid pairs or unknown tagged formats/origins
  are left untouched and logged individually as warnings; scanning continues and startup has no modal dialog.

The pre-release CharmInv lane already saved some test characters with core 0.1.18; its CharmInv record protects them.
A sidecar manually stripped of both origin records, or a downgrade to old core followed by saving without CharmInv,
loses this evidence. Such manual downgrade/edit workflows are unsupported; keep the matching save and sidecar together.

## Pair writes and interruption

Before changing anything, keep a content-addressed original pair beside the character (`.d2s.stash2-<sha256>` and
its `.d2rl` companion). These are backups, never loaded as characters. Write a pending journal, replace the save and
sidecar through flushed temporary files, then remove the journal. A caught write failure restores both originals;
an interrupted conversion rolls back only a recognized half-written pair at the next startup, then retries cleanup.
A consistent current pair always wins over a stale journal; a newer save is never replaced with the backup. If recovery
fails or the pair is ambiguous, that character is skipped and warned about; other characters still load. Every completed deletion logs the character name and top-level item count.

`stash_retire_data.h` is generated from the built Median tables by `tools/stash_retire_data.py`. The native reader
follows `tools/d2save.py`'s extended codec, including rare affixes, item stat pairs, GUIDs, socket children and padding;
unknown fields skip that character without modifying its pair. Tests compare native output with independent Python-encoded fixtures and actual game saves.

## Verification

See [testing.md](testing.md), lane stashpage retirement. Test only isolated throwaway saves through slot locks.
The old-build fixture has seven page-2 items: three runes, a shrine, a normal charm, a body part and a noncompact scroll;
full personal/shared storage, inventory items and a cube.
Compare complete item identities before/after excluding exactly the retired items; add a new charm through CharmInv's
real grid, save/reload, and confirm it and every other item survive. Keep HD/legacy stash screenshots and CharmInv shots
with the logs outside git. CharmInv itself currently supplies HD layouts only (the charminv lane's existing limitation).

## Unreadable characters (stashfix)

Cleanup never disables the whole game because of one save. The warning names the skipped character and tells the
player not to load it until repaired. Its existing save/sidecar remain unchanged on parse or integrity failure.
D2RLoader still validates the character: damaged saves/pairs can be refused independently. A valid but unsupported
old save with page-6 items could load them through the registered CharmInv provider; skipping alone cannot prevent
that or safely infer their boundaries. Do not save that character until its reader/pair issue is resolved. No global
provider toggle or speculative item deletion is used, and the installed SDK has no per-character pre-load veto.

The release-blocking fixtures exposed Chronicle trailers (`0x10000000`, source u16, timestamp u32 unless compact,
4-bit recipient count capped at eight, then u64 recipients; compact flag `0x20000000` has one recipient), plus compact
quest-difficulty fields. A noncompact item also ends with the advanced-stash presence bit and optional 8-bit count,
then byte alignment. The earlier apparent extra padding byte was that presence bit. Native and Python readers now
handle these fields. See the [independent reader source](https://github.com/ResurrectedTrader/d2s-rs/blob/main/src/model/item.rs)
and the game-written byte fixtures in `tools/tests/test_stash_retire.py`.
