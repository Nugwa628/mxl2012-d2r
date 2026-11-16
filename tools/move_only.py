"""Move Only: a class-less skill every character has that only walks or runs to the cursor (docs/left-skills.md).

Ported from our Median XL Sigma port (its `move_only` row and the start function that refuses every cast), adapted to
Median XL 2012's build. tools/txt_migrate.py (`Migrator.move_only`) adds the row to skills.txt / skilldesc.txt of both banks,
after every other row, and gives it to every class through charstats.txt (the first empty `Skill N` column), the way Kick,
Throw and Unsummon are given: no skill point, no tree slot, also for characters made before it existed (the game adds the
charstats skills each time a character is loaded).

How it moves the character and never attacks:
  * `TargetableOnly 1`: a click on the ground with the skill on a button is a walk (a run with the run toggle on), as D2R
    does for every targeted skill;
  * a click on a monster: the server walks the character into reach (`range h2h`) and then runs the skill's start function,
    srvstfunc 71, which the mxl2012-core plugin fills with a function that refuses every cast (plugin/src/move_only.cpp, off
    word `moveonly`). Nothing is cast, nothing is hit, no mana is spent: the character stops next to the monster;
  * no do functions, no missile, no damage: with the plugin part off a click on a monster would only play the walk frames
    in place.

The texts are ours, in the 13 languages the mod ships (tools/tbl2json.py adds them to the mod's string namespace; written
with escapes so the file stays ASCII). The icon is D2R's Burst of Speed picture (tools/data/item_skill_icons.tsv row
`move_only`, tools/shared_icons.py).
"""
from __future__ import annotations

SKILL = "Move Only"           # skills.txt `skill`
DESC = "move_only"            # skilldesc.txt `skilldesc` (the row's key)
START_SLOT = 71               # srvstfunc: a free slot of D2R's server start table (0x238e710, 91 slots, D2R uses 0-70)
ICON_DONOR = "d2r:quickness"  # D2R's Burst of Speed row: a running figure

NAME_KEY, SHORT_KEY, LONG_KEY = "SkillnameMoveOnly", "SkillsdMoveOnly", "SkillldMoveOnly"

# skills.txt columns of the row (every other column blank). Modelled on D2R's Attack row without anything that attacks.
SKILL_COLUMNS = {
    "skill": SKILL, "skilldesc": DESC,
    "srvstfunc": str(START_SLOT),
    "range": "h2h", "anim": "WL", "seqtrans": "WL", "monanim": "xx",
    "TargetableOnly": "1", "AttackNoMana": "1", "interrupt": "1",
    "reqlevel": "1", "maxlvl": "1", "restrict": "1",
    "leftskill": "1", "rightskill": "1",
    "InTown": "1", "InGame": "1",
}
# skilldesc.txt columns: no tree page (SkillPage 0), shown among the class-less skills of the skill pop-up (ListRow 0).
# IconCel 0 is the shared sheet's "?" until tools/shared_icons.py gives the row its donor's frame.
SKILLDESC_COLUMNS = {
    "skilldesc": DESC, "SkillPage": "0", "SkillRow": "0", "SkillColumn": "0", "ListRow": "0", "IconCel": "0",
    "str name": NAME_KEY, "str short": SHORT_KEY, "str long": LONG_KEY, "str alt": NAME_KEY,
}

LANGS = ("enUS", "zhTW", "deDE", "esES", "frFR", "itIT", "koKR", "plPL", "esMX", "jaJP", "ptBR", "ruRU", "zhCN")
_NAME = {
    "enUS": "Move Only",
    "deDE": "Nur bewegen",
    "frFR": "D\U000000e9placement seul",
    "esES": "Solo moverse",
    "esMX": "Solo moverse",
    "itIT": "Solo movimento",
    "ptBR": "Apenas mover",
    "plPL": "Tylko ruch",
    "ruRU": "\U00000422\U0000043e\U0000043b\U0000044c\U0000043a\U0000043e \U00000434\U00000432\U00000438\U00000436\U00000435\U0000043d\U00000438\U00000435",
    "koKR": "\U0000c774\U0000b3d9 \U0000c804\U0000c6a9",
    "jaJP": "\U000079fb\U000052d5\U0000306e\U0000307f",
    "zhTW": "\U000050c5\U000079fb\U000052d5",
    "zhCN": "\U00004ec5\U000079fb\U000052a8",
}
_SHORT = {
    "enUS": "Walk or run to the cursor",
    "deDE": "Zum Mauszeiger gehen oder laufen",
    "frFR": "Marcher ou courir jusqu'au curseur",
    "esES": "Caminar o correr hasta el cursor",
    "esMX": "Caminar o correr hasta el cursor",
    "itIT": "Cammina o corri fino al cursore",
    "ptBR": "Andar ou correr at\U000000e9 o cursor",
    "plPL": "Id\U0000017a lub biegnij do kursora",
    "ruRU": "\U00000418\U00000434\U00000442\U00000438 \U00000438\U0000043b\U00000438 \U00000431\U00000435\U00000436\U00000430\U00000442\U0000044c \U0000043a \U0000043a\U00000443\U00000440\U00000441\U0000043e\U00000440\U00000443",
    "koKR": "\U0000cee4\U0000c11c \U0000c704\U0000ce58\U0000b85c \U0000ac77\U0000ac70\U0000b098 \U0000b2ec\U0000b9bd\U0000b2c8\U0000b2e4",
    "jaJP": "\U000030ab\U000030fc\U000030bd\U000030eb\U0000306e\U00004f4d\U00007f6e\U0000307e\U00003067\U00006b69\U0000304f\U0000304b\U00008d70\U0000308b",
    "zhTW": "\U00008d70\U00006216\U00008dd1\U00005230\U00006e38\U00006a19\U00008655",
    "zhCN": "\U00008d70\U00006216\U00008dd1\U00005230\U00005149\U00006807\U00005904",
}
_LONG = {
    "enUS": "Walks or runs to the spot you click.\nNever attacks and never uses a skill.",
    "deDE": "Geht oder l\U000000e4uft zu der Stelle, die du anklickst.\nGreift nie an und setzt nie eine Fertigkeit ein.",
    "frFR": "Marche ou court jusqu'\U000000e0 l'endroit cliqu\U000000e9.\nN'attaque jamais et n'utilise jamais de comp\U000000e9tence.",
    "esES": "Camina o corre hasta el punto en que haces clic.\nNunca ataca ni usa una habilidad.",
    "esMX": "Camina o corre hasta el punto en que haces clic.\nNunca ataca ni usa una habilidad.",
    "itIT": "Cammina o corre fino al punto cliccato.\nNon attacca mai e non usa mai un'abilit\U000000e0.",
    "ptBR": "Anda ou corre at\U000000e9 o ponto clicado.\nNunca ataca e nunca usa uma habilidade.",
    "plPL": "Idzie lub biegnie w klikni\U00000119te miejsce.\nNigdy nie atakuje i nie u\U0000017cywa umiej\U00000119tno\U0000015bci.",
    "ruRU": "\U00000418\U00000434\U00000451\U00000442 \U00000438\U0000043b\U00000438 \U00000431\U00000435\U00000436\U00000438\U00000442 \U0000043a \U0000043c\U00000435\U00000441\U00000442\U00000443, \U0000043f\U0000043e \U0000043a\U0000043e\U00000442\U0000043e\U00000440\U0000043e\U0000043c\U00000443 \U00000432\U0000044b \U00000449\U00000451\U0000043b\U0000043a\U0000043d\U00000443\U0000043b\U00000438.\n\U0000041d\U00000438\U0000043a\U0000043e\U00000433\U00000434\U00000430 \U0000043d\U00000435 \U00000430\U00000442\U00000430\U0000043a\U00000443\U00000435\U00000442 \U00000438 \U0000043d\U00000435 \U0000043f\U00000440\U00000438\U0000043c\U00000435\U0000043d\U0000044f\U00000435\U00000442 \U00000443\U0000043c\U00000435\U0000043d\U00000438\U0000044f.",
    "koKR": "\U0000d074\U0000b9ad\U0000d55c \U0000c704\U0000ce58\U0000b85c \U0000ac77\U0000ac70\U0000b098 \U0000b2ec\U0000b9bd\U0000b2c8\U0000b2e4.\n\U0000acf5\U0000aca9\U0000d558\U0000c9c0 \U0000c54a\U0000c73c\U0000ba70 \U0000ae30\U0000c220\U0000c744 \U0000c0ac\U0000c6a9\U0000d558\U0000c9c0 \U0000c54a\U0000c2b5\U0000b2c8\U0000b2e4.",
    "jaJP": "\U000030af\U000030ea\U000030c3\U000030af\U00003057\U0000305f\U00005834\U00006240\U0000307e\U00003067\U00006b69\U0000304f\U0000304b\U00008d70\U0000308a\U0000307e\U00003059\U00003002\n\U0000653b\U00006483\U00003082\U000030b9\U000030ad\U000030eb\U0000306e\U00004f7f\U00007528\U00003082\U0000884c\U00003044\U0000307e\U0000305b\U00003093\U00003002",
    "zhTW": "\U00008d70\U00006216\U00008dd1\U00005230\U00004f60\U00009ede\U000064ca\U00007684\U00004f4d\U00007f6e\U00003002\n\U00004e0d\U00006703\U0000653b\U000064ca\U0000ff0c\U00004e5f\U00004e0d\U00006703\U000065bd\U0000653e\U00006280\U000080fd\U00003002",
    "zhCN": "\U00008d70\U00006216\U00008dd1\U00005230\U00004f60\U000070b9\U000051fb\U00007684\U00004f4d\U00007f6e\U00003002\n\U00004e0d\U00004f1a\U0000653b\U000051fb\U0000ff0c\U00004e5f\U00004e0d\U00004f1a\U000065bd\U0000653e\U00006280\U000080fd\U00003002",
}
TEXTS = {NAME_KEY: _NAME, SHORT_KEY: _SHORT, LONG_KEY: _LONG}


def string_records(langs: tuple[str, ...] = LANGS) -> list[dict]:
    """The skill's three texts as D2R string records ({"Key": ..., "enUS": ..., ...}); every language is required."""
    out = []
    for key, texts in TEXTS.items():
        missing = [lang for lang in langs if not texts.get(lang)]
        if missing:
            raise ValueError(f"move_only: {key} has no text for {', '.join(missing)}")
        out.append({"Key": key, **{lang: texts[lang] for lang in langs}})
    return out


def is_row(row: list[str]) -> bool:
    """A data row: not an empty line and not an "Expansion" separator."""
    return bool(row) and any(c.strip() for c in row) and row[0] != "Expansion"


def make_row(header: list[str], columns: dict[str, str], row_id: int | None = None) -> list[str]:
    """A row of `header` with `columns` set and every other column blank (the `*Id` comment column = `row_id`)."""
    unknown = [c for c in columns if c not in header]
    if unknown:
        raise ValueError(f"move_only: no column {', '.join(unknown)}")
    row = [""] * len(header)
    for c, v in columns.items():
        row[header.index(c)] = v
    if row_id is not None and "*Id" in header:
        row[header.index("*Id")] = str(row_id)
    return row


def add_skill(header: list[str], rows: list[list[str]]) -> int:
    """Append the Move Only row to skills.txt `rows` (or rewrite it when present) and return its id (its row index)."""
    records = [r for r in rows if is_row(r)]
    st = header.index("srvstfunc")
    taken = [r[0] for r in records if r[0] != SKILL and len(r) > st and r[st] == str(START_SLOT)]
    if taken:  # tools/idmap.py FREE_SLOTS may hand out 71 to a moved 1.13c start: the plugin's function is Move Only's
        raise ValueError(f"move_only: srvstfunc {START_SLOT} is Move Only's, also used by {', '.join(taken)}")
    for i, r in enumerate(records):
        if r[0] == SKILL:
            r[:] = make_row(header, SKILL_COLUMNS, i)
            return i
    row_id = len(records)
    rows.append(make_row(header, SKILL_COLUMNS, row_id))
    return row_id


def add_skilldesc(header: list[str], rows: list[list[str]]) -> None:
    """Append (or rewrite) the Move Only row of skilldesc.txt."""
    new = make_row(header, SKILLDESC_COLUMNS)
    for r in rows:
        if is_row(r) and r[0] == DESC:
            r[:] = new
            return
    rows.append(new)


def add_to_classes(header: list[str], rows: list[list[str]]) -> list[str]:
    """Give Move Only to every class row of charstats.txt (rows with a `Skill 1`) in its first empty `Skill N` column;
    return the classes given it. A class with every column taken raises (the skill must reach every class)."""
    cols = [i for i, c in enumerate(header) if c.startswith("Skill ") and c[6:].isdigit()]
    first = header.index("Skill 1")
    given = []
    for r in rows:
        if not is_row(r) or len(r) <= first or not r[first]:
            continue
        if any(r[i] == SKILL for i in cols):
            given.append(r[0])
            continue
        free = next((i for i in cols if i < len(r) and not r[i]), None)
        if free is None:
            raise ValueError(f"move_only: charstats row {r[0]} has no empty Skill column")
        r[free] = SKILL
        given.append(r[0])
    return given
