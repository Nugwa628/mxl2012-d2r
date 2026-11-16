# Left-click skills and Move Only

D2R-XL 2012 lets you put any skill you can cast on the left mouse button, not only on the right one, and gives every
character a new skill, **Move Only**, that walks without ever attacking.

## For players

- **Every castable skill works on left click.** Open the left skill menu (the button at the bottom left of the skill bar,
  or the left half of the skill bar in HD) and pick it, as you would on the right. This covers class skills, skills from
  items (charges and oskills) and the common skills.
- **What stays right-click only:**
  - the Barbarian's Stances (Wolf, Lion, Snake, Bear, Eagle): they are auras, and the game runs an aura from the right
    button only, as in the original game;
  - skills cast on a corpse: the Necromancer's totems (Death's Fury, Frostclaw, Fireheart, Howling, Stormeye), the
    Amazon's Fairy Ring and Spirit of Vengeance, Engorge, Cold Blood, and item skills of the same kind (Raise Skeleton,
    Raise Skeletal Mage, the item totems). The game's left click picks no corpse, so on the left they would cast
    nothing (tested with Death's Fury Totem: a left click on a monster did nothing, on the ground it only walked);
  - Scroll / Book of Identify and Scroll / Book of Town Portal: they are used from the item;
  - passive skills: they are never on a button.
- **Move Only** is on both skill menus of every class, among the common skills (with Throw and Unsummon). It costs no
  skill point and has no place on a skill tree; old characters have it too. On a button:
  - a click on the ground walks (or runs, with run on) to that spot;
  - a click on a monster walks up to it and stops: no attack, no skill, no mana spent.
  It is handy for left click when you want to walk through a crowd without swinging at it, with a skill on the right.
- Your left skill is saved with your character, as before.
- With a gamepad nothing changes: in the Skill Tree, focus a skill (Move Only is among the General Skills), press X
  (Bind Skill) and then the pad button to put it on.

## How it is made

- `tools/txt_migrate.py` `skill_rules`: every skills.txt row with `rightskill 1` gets `leftskill 1`, except auras
  (`aura 1`), corpse-targeted rows (`SelectProc` or `TargetCorpse` set) and `RIGHT_ONLY` (the scroll and book skills,
  D2R's own portal skill). D2R reads `leftskill` both in the
  client's skill menu and in the server's select-skill packet (0x3c), so the table change is the whole change; 1.13c's
  DLLs ignored the column. The build report (`work/mod/migrate_report.md`) counts the rows: 295 in the current build (32 corpse-targeted rows left out).
- `tools/move_only.py`: the Move Only rows (skills.txt id 1110 after Median's 0-1109, skilldesc `move_only`), its texts in
  the 13 languages (`tools/tbl2json.py` adds them to the `mxl2012` string namespace) and the charstats starting skill
  (first empty `Skill N` of each class). The icon is D2R's Burst of Speed picture
  (`tools/data/item_skill_icons.tsv`, `tools/shared_icons.py`).
- Move Only's row has no do function, missile or damage; its animation `WL` puts the player in the walk mode, so the
  game starts no skill: a click on the ground walks there, a click on a monster walks up to it (`TargetableOnly 1`, range
  `h2h`) and nothing more. In game the harness cast at a monster (the cast packets' own path) also only walked.
- `plugin/src/move_only.cpp` (off word `moveonly`) is a guard behind that: srvstfunc 71, a free slot of D2R's server start
  table, refuses every cast of the row should the game ever start it (its `mxl` counter stayed 0 in the runs). The row
  shape and the start-slot idea come from our Sigma port's Move Only.
- Check `leftskills` (`tools/game_checks.py`) proves it in game; `docs/testing.md` has the run.
