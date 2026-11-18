# Secret uniques

Median XL 2012 v005 has uniques that it never lets drop. The community wiki's "Secrets" page lists 28 of them. On
2026-11-16 the owner asked for the ones with stats on that page to drop, except Aerial's Skull and the Token beta ring.
That is 9 items. The page's 17 names without stats (Laz' Social Experiment, Queen Esu's Consort, Heartcore, The Coliseum,
Foramen, En Taro Idunn, Jaguar Warrior, Echo Shard, Free Tone, Gatecrasher, Kriss Talline, Ring of Mourning, Black Hand
Sigil, Akarat's Nails, The Tesseract, Khanduran Royal Pendant, Locket of Dreams) stay as Median has them: no drop.

Build step: `tools/secret_items.py apply`, after `txt_migrate.py` and before `chronicle.py` (which then lists them in the
Chronicle). Data: `data/secret_items.tsv`. Test: `tools/tests/test_secret_items.py`. Report with the shares below:
`work/mod/secret_items_report.md`. In-game check: `secrets` (tools/secrets_checks.py, docs/testing.md "Lane secrets").

## What changes

In v005 all nine rows have a blank `enabled` column, which becomes D2R's `spawnable`. The step does three things:

- It sets `spawnable` to 1 and gives each row its new rarity: 1 for each sacred item, and Lady of Storms 1, Atomus 2,
  Bard's Joke 3 for the jewels.
- It changes Lady of Storms' required level from 555 to 40 (owner).
- It multiplies the rarity of every other spawnable unique on the same base: x4 on the six sacred bases and x10 on
  jewels. When an item rolls unique, the game picks among the rows of its base by rarity weight. Median's other uniques on
  these bases already have rarity 1 or 2, so a secret item can only be rarer if they go up. Multiplying them all by the
  same factor keeps their odds against each other as Median set them.

Median's stats, item levels (`lvl`, the qlvl: 120, Bard's Joke 40) and treasure classes are unchanged. The bases already
drop, so no treasure class change is needed.

## Odds

The shares below are among the uniques of the same base, once a drop of that base has rolled unique. Magic find changes
how often the unique roll happens, not this pick. Item level 120 unless noted.

| Item | Base | Share | Rarest other unique of the base | Most common other |
|-|-|-|-|-|
| Lady of Storms | Jewel | 1 in 41,596 | 1 in 4,160 (each Cornerstone of the Roflworld row) | 1 in 8.3 |
| Atomus | Jewel | 1 in 20,798 | 1 in 4,160 | 1 in 8.3 |
| Bard's Joke | Jewel | 1 in 13,865 (ilvl 40-99: 1 in 5,751) | 1 in 4,160 | 1 in 8.3 |
| Grand Armor, Siggard's Revenge, Aeterna, Sword of the White Void, Fury of Hellfire, Soul Reaver | their sacred base | 1 in 13 | 1 in 3.25 | 1 in 1.6 |

The sacred bases had two uniques each, weighted 2 and 1 (67% / 33%). They now read 8 : 4 : 1 (62% / 31% / 8%). In game,
the generator's own pick over 360 unique rolls gave 29 secrets (1 in 12.4).

## Stat differences from the wiki

Median's stats are kept. The tooltips match the wiki line for line apart from these display differences:

- Aeterna shows an "Amazing Grace" line and Soul Reaver a "Mega Impact" line. These are Median's innate item skills, and
  the wiki leaves them out. Aeterna's proc is skill 340, which Median names Singularity, as the wiki says.
- The wiki's required strength is before the item's own requirement modifier. Aeterna (-50%) shows 244 instead of 488,
  and Grand Armor (+500%) shows 3996 instead of 666.
- Bard's Joke rolled "Adds 6-10 damage" in the test. The wiki says 5-10, and the row is `dmg-norm` 5-10. Not
  investigated further. Its "+1 to Disco Inferno" line shows, even though Median marks the row "UNFINISHED OSKILL".
