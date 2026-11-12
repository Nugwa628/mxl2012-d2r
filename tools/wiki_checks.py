"""In-game checks of the wiki panel (plugin part wiki, plugin/src/wiki.cpp, docs/wiki-panel.md), run through tools/game_checks.py:

  wiki       open by the real key, the Welcome page, a category, result pages (button, real click, mouse wheel), a typed search, an entry,
             scrolling its text (wheel, button, Page Down), a link and Back, Esc and the key from the list and from the search box, and the
             notice in classic graphics. Background screenshots `wiki_*`.
  wikilook   the panel at 1600 x 900 and 1280 x 720: Welcome, a long entry, a search. Screenshots `wiki_look_<w>_*`, judged by eye.
  wikilab    what D2R's text boxes show of colour codes inside a text, and how wide the Formal face is: screenshots `wiki_lab_*`, judged by eye.

The checks read the content table the build installs (work/mod/data/mxl2012-wiki/wiki.tsv) and pick their entries from it, so they run on
the exporter's table and on a hand-written sample alike. Before the exporter is part of the build, put a sample there and install the mod:

  py -3 tools/wiki_checks.py use-table <wiki.tsv>      copies it to work/mod/data/mxl2012-wiki/wiki.tsv (tools/install_mod.py installs it)

Any character will do (the panel reads no game state): MXL_CHAR=<letters only>.
"""
import ctypes
import ctypes.wintypes
import re
import shutil
import sys
import time
from pathlib import Path

import wiki_layout

ROOT = Path(__file__).resolve().parent.parent
TABLE = ROOT / "work" / "mod" / "data" / "mxl2012-wiki" / "wiki.tsv"
KEY = "j"  # the action's default key (wiki.cpp)
WM_KEYDOWN, WM_KEYUP, WM_MOUSEWHEEL = 0x0100, 0x0101, 0x020A
VK_PRIOR, VK_NEXT = 0x21, 0x22
WHEEL_LINES = 3


# ------------------------------------------------------------------------------------------------------------------ the table
def read_table(path=TABLE):
    """(categories [(id, label)], entries [{cat, name, subtitle, search, lines, links}]) of a content table, as the plugin reads it."""
    cats, entries = [], []
    for line in Path(path).read_text("utf-8").split("\n"):
        f = line.rstrip("\r").split("\t")
        if f[0] == "C" and len(f) >= 3:
            cats.append((f[1], f[2]))
        elif f[0] == "E" and len(f) >= 5:
            entries.append({"cat": f[1], "name": f[2], "subtitle": f[3], "search": f[4], "lines": [], "links": []})
        elif f[0] == "L" and len(f) >= 3 and entries:
            entries[-1]["lines"].append((f[1], f[2]))
        elif f[0] == "K" and len(f) >= 2 and entries:
            entries[-1]["links"].append(f[1])
    return cats, entries


def matches(entry, query):
    return all(w in entry["search"] for w in query.lower().split())


# ------------------------------------------------------------------------------------------------------------------ the harness
def parse(lines):
    out = {}
    for ln in lines:
        t = re.search(r'wiki texts query="(.*?)" selected="(.*?)" status="(.*)"', ln)
        if t:
            out.update({"query": t.group(1), "selected": t.group(2), "status": t.group(3)})
            continue
        m = re.search(r"wiki (on=.*)$", ln)
        if m:
            out.update({k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)\b", m.group(1))})
    return out


def state(gc, log):
    _ok, lines = gc.Hl("wiki state", log)
    return parse(lines)


def wait(gc, log, cond, timeout=6.0):
    t0 = time.time()
    st = state(gc, log)
    while not cond(st) and time.time() - t0 < timeout:
        time.sleep(0.25)
        st = state(gc, log)
    return st


def verb(gc, log, text):
    _ok, lines = gc.Hl("wiki " + text, log)
    return parse(lines)


def do(gc, log, button):
    verb(gc, log, "press " + button)
    time.sleep(0.3)
    return state(gc, log)


# ------------------------------------------------------------------------------------------------------------------ real input
def _window(gc):
    h = gc.g.need_window()
    l, t, r, b = gc.g.client_rect(h)
    return h, r - l, b - t


def to_fraction(gc, x, y):
    """A point of the panel (its own units) as a fraction of the client area."""
    m = wiki_layout.layout()["metrics"]
    _h, width, height = _window(gc)
    scale = height / 2160.0
    return (width / 2.0 + (m["panelX"] + x) * scale) / width, (height / 2.0 + (m["panelY"] + y) * scale) / height


def widget_centre(name):
    child = next(c for c in wiki_layout.layout()["root"]["children"] if c["name"] == name)
    x, y, w, h = wiki_layout.widget_box(child)
    return x + w / 2.0, y + h / 2.0


def click_widget(gc, name):
    """A real (posted) mouse click on the middle of a widget, at the position the layout puts it."""
    gc.g.click(*to_fraction(gc, *widget_centre(name)))


def click_empty(gc):
    """A click on an empty part of the panel (beside the title): the search box loses the keyboard."""
    gc.g.click(*to_fraction(gc, 300, 50))


def wheel(gc, pane, notches):
    """The mouse wheel over the middle of the list or the detail pane: the pointer is moved there, then WM_MOUSEWHEEL is posted."""
    m = wiki_layout.layout()["metrics"]
    fx, fy = to_fraction(gc, m[pane + "X"] + m[pane + "W"] / 2.0, m[pane + "Y"] + m[pane + "H"] / 2.0)
    gc.g.click(fx, fy, move_only=True)
    h, width, height = _window(gc)
    pt = ctypes.wintypes.POINT(int(fx * width), int(fy * height))
    ctypes.windll.user32.ClientToScreen(h, ctypes.byref(pt))
    ctypes.windll.user32.PostMessageW(h, WM_MOUSEWHEEL, ((notches * 120) & 0xFFFF) << 16, ((pt.y & 0xFFFF) << 16) | (pt.x & 0xFFFF))
    time.sleep(0.5)


def post_key(gc, vk):
    h = gc.g.need_window()
    ctypes.windll.user32.PostMessageW(h, WM_KEYDOWN, vk, 1)
    time.sleep(0.06)
    ctypes.windll.user32.PostMessageW(h, WM_KEYUP, vk, 0xC0000001)
    time.sleep(0.4)


def strips(gc):
    """The game picture left and right of the panel, where a game panel opened by a key shows (character left, inventory right)."""
    grabbed = gc.g.grab_client(gc.g.need_window()).convert("RGB")
    w, h = grabbed.size
    left, _ = to_fraction(gc, -40, 0)
    right, _ = to_fraction(gc, wiki_layout.PANEL_W + 40, 0)
    return [grabbed.crop((int(w * 0.02), int(h * 0.15), int(w * left), int(h * 0.8))), grabbed.crop((int(w * right), int(h * 0.15), int(w * 0.98), int(h * 0.8)))]


def changed(before, after):
    from PIL import ImageChops, ImageStat
    return any(max(ImageStat.Stat(ImageChops.difference(a, b)).mean) > 12.0 for a, b in zip(before, after))


def type_keys(gc, text):
    """Key down / key up only, as a keyboard does (tools/devmenu_checks.py type_keys)."""
    for ch in text:
        if ch == " ":
            gc.g.press("space")
        elif ch in gc.g.VK and not ch.isupper():
            gc.g.press(ch)
        else:
            gc.g.type_text(ch)


def typed(gc, log, text):
    type_keys(gc, text)
    st = wait(gc, log, lambda s: s.get("query") == text, 3.0)
    return st.get("query")


def clear_box(gc, log):
    for _ in range(4):
        for _ in range(30):
            gc.g.press("right", hold=0.02)
        for _ in range(30):
            gc.g.press("backspace", hold=0.02)
        time.sleep(0.5)
        if not state(gc, log).get("query"):
            return


def open_panel(gc, log):
    gc.g.press(KEY)
    st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
    by_key = st.get("open") == 1
    if not by_key:
        log.append("the key did not open the panel; `wiki open`")
        verb(gc, log, "open")
        st = wait(gc, log, lambda s: s.get("open") == 1, 4.0)
    time.sleep(0.8)
    return by_key, state(gc, log)


def close_panel(gc, log):
    verb(gc, log, "close")
    wait(gc, log, lambda s: s.get("open") == 0, 3.0)
    time.sleep(0.5)


def rows_helper():
    log, shots, rows = [], [], []

    def row(name, ok, note):
        rows.append((name, ok, note))
        log.append("ROW %s %s: %s" % (name, "PASS" if ok else ("SKIP" if ok is None else "FAIL"), note))

    return log, shots, rows, row


def picks(cats, entries):
    """The entries the checks use, from the installed table: a long one (to scroll), one with a link to an existing entry, a category
    with entries, and a search word that finds some but not all entries."""
    names = {e["name"] for e in entries}
    lower = [e["name"].lower() for e in entries]

    def alone(e):  # no other entry's name starts with this one: a search for the full name lists it first
        return len(e["name"]) <= 40 and sum(n.startswith(e["name"].lower()) for n in lower) == 1

    long_entry = max((e for e in entries if len(e["lines"]) <= 300 and alone(e)), key=lambda e: len(e["lines"]))
    linked = next((e for e in entries if any(k in names and k != e["name"] for k in e["links"]) and len(e["lines"]) <= 300 and alone(e)), None)
    by_cat = {}
    for e in entries:
        by_cat[e["cat"]] = by_cat.get(e["cat"], 0) + 1
    cat_index = next(i for i, (cid, _label) in enumerate(cats) if by_cat.get(cid))
    word = next((w for w in ("staff", "sword", "fire", "level") if 0 < sum(matches(e, w) for e in entries) < len(entries)), "a")
    return long_entry, linked, cat_index, by_cat[cats[cat_index][0]], word


def deep_hit(entries, visible):
    """(entry, query): a search that finds only that entry, by words of one of its lines below the first page; None when there is none."""
    lower = [e["name"].lower() for e in entries]
    for entry in sorted((e for e in entries if visible + 8 < len(e["lines"]) <= 300), key=lambda e: -len(e["lines"]))[:40]:
        if sum(n.startswith(entry["name"].lower()) for n in lower) != 1:
            continue
        for text in reversed([t for _c, t in entry["lines"]][visible + 4:]):
            words = text.lower().split()
            for part in (words, words[:4], words[-4:]):
                query = " ".join(part)
                if 2 <= len(part) <= 8 and len(query) <= 60 and all(w.isascii() and "\"" not in w for w in part) and sum(matches(e, query) for e in entries) == 1:
                    return entry, query
    return None


# ------------------------------------------------------------------------------------------------------------------ the checks
def run(gc):
    mark = gc.engine_mark()
    log, shots, rows, row = rows_helper()
    cats, entries = read_table()
    long_entry, linked, cat_index, cat_count, word = picks(cats, entries)
    m = wiki_layout.layout()["metrics"]
    log.append("table: %d entries, %d categories; long %r (%d lines), linked %r, category %s (%d), word %r" % (
        len(entries), len(cats), long_entry["name"], len(long_entry["lines"]), linked and linked["name"], cats[cat_index][1], cat_count, word))

    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    time.sleep(1.5)
    s0 = state(gc, log)
    row("table loaded", s0.get("on") == 1 and s0.get("table") == 1 and s0.get("entries") == len(entries), "on=%s table=%s entries=%s (file %d), load %s ms" % (
        s0.get("on"), s0.get("table"), s0.get("entries"), len(entries), s0.get("loadms")))

    # open by the real key: the Welcome page, the whole table listed, nothing else opened
    base = strips(gc)
    by_key, st = open_panel(gc, log)
    row("open by the key", by_key and st.get("open") == 1, "open=%s by key=%s" % (st.get("open"), by_key))
    has_welcome = any(e["name"] == "Welcome" for e in entries)
    row("opens on the Welcome page", st.get("selected") == ("Welcome" if has_welcome else "") and st.get("results") == len(entries) and st.get("rows") == min(m["rows"], len(entries)),
        "selected=%r results=%s rows=%s" % (st.get("selected"), st.get("results"), st.get("rows")))
    row("the key opens nothing else", not changed(base, strips(gc)), "side strips unchanged")
    shots.append(gc.sh("wiki_open_welcome"))

    # a category by a real click on its button, then All again
    click_widget(gc, "Btn_cat%d" % (cat_index + 1))
    st = wait(gc, log, lambda s: s.get("cat") == cat_index, 3.0)
    row("category by a real click", st.get("cat") == cat_index and st.get("results") == cat_count, "cat=%s results=%s (table %d)" % (st.get("cat"), st.get("results"), cat_count))
    shots.append(gc.sh("wiki_category"))
    st = do(gc, log, "cat0")
    row("All again", st.get("cat") == -1 and st.get("results") == len(entries), "cat=%s results=%s" % (st.get("cat"), st.get("results")))

    # result pages: the button, a real click on the arrow, the mouse wheel over the list
    pages = (len(entries) + m["rows"] - 1) // m["rows"]
    if pages > 1:
        st = do(gc, log, "next")
        ok = st.get("page") == 1 and st.get("pages") == pages
        click_widget(gc, "Btn_prev")
        st2 = wait(gc, log, lambda s: s.get("page") == 0, 3.0)
        row("result pages: button and real click", ok and st2.get("page") == 0, "next -> page %s of %s; click prev -> page %s" % (st.get("page"), st.get("pages"), st2.get("page")))
        wheel(gc, "list", -1)
        st = wait(gc, log, lambda s: s.get("page") == 1, 3.0)
        shots.append(gc.sh("wiki_list_page2"))
        wheel(gc, "list", 1)
        st2 = wait(gc, log, lambda s: s.get("page") == 0, 3.0)
        row("result pages: mouse wheel over the list", st.get("page") == 1 and st2.get("page") == 0, "wheel down -> page %s, wheel up -> page %s, wheels=%s" % (
            st.get("page"), st2.get("page"), st2.get("wheels")))
    else:
        row("result pages", None, "the table fits one page")

    # typed search with real keys: bound keys type, nothing fires
    click_widget(gc, wiki_layout.INPUT)
    time.sleep(0.5)
    st = state(gc, log)
    row("a click gives the box the keyboard", st.get("boxfocus") == 1 and st.get("boxclicked") == 1, "boxfocus=%s boxclicked=%s" % (st.get("boxfocus"), st.get("boxclicked")))
    base = strips(gc)
    got = typed(gc, log, word)
    want = sum(matches(e, word) for e in entries)
    st = state(gc, log)
    row("typed search", got == word and st.get("results") == want and not changed(base, strips(gc)), "query=%r results=%s (table %d) keysheld=%s" % (got, st.get("results"), want, st.get("keysheld")))
    shots.append(gc.sh("wiki_search"))
    clear_box(gc, log)
    got = typed(gc, log, "ictqmw 12")
    row("bound keys type into the box", got == "ictqmw 12" and not changed(base, strips(gc)), "query=%r, side strips unchanged" % got)
    clear_box(gc, log)
    type_keys(gc, "ab")
    gc.g.press("backspace")
    time.sleep(0.3)
    gc.g.press("enter")
    st = wait(gc, log, lambda s: s.get("query") == "a", 3.0)
    row("Backspace and Enter stay in the box", st.get("query") == "a", "query=%r" % st.get("query"))
    clear_box(gc, log)

    # an entry by its full name: the first row is it; a real click on the row's arrow shows it
    got = typed(gc, log, long_entry["name"].lower())
    time.sleep(0.4)
    click_widget(gc, "Btn_row0")
    st = wait(gc, log, lambda s: s.get("selected") == long_entry["name"], 3.0)
    row("select an entry by a real click", st.get("selected") == long_entry["name"] and st.get("lines", 0) >= len(long_entry["lines"]),
        "query=%r selected=%r lines=%s (table %d)" % (got, st.get("selected"), st.get("lines"), len(long_entry["lines"])))
    shots.append(gc.sh("wiki_entry"))

    # scrolling: the wheel over the text, the button, Page Down (the box does not have the keyboard after a click elsewhere)
    total = st.get("lines", 0)
    if total > m["lines"]:
        wheel(gc, "detail", -1)
        st = wait(gc, log, lambda s: s.get("scroll") == WHEEL_LINES, 3.0)
        ok_wheel = st.get("scroll") == min(WHEEL_LINES, total - m["lines"])
        st = do(gc, log, "down")
        ok_button = st.get("scroll") == min(WHEEL_LINES + m["lines"], total - m["lines"])
        shots.append(gc.sh("wiki_entry_scrolled"))
        before = st.get("scroll")
        click_empty(gc)
        time.sleep(0.3)
        post_key(gc, VK_NEXT)
        st = wait(gc, log, lambda s: s.get("scroll") != before, 2.0)
        ok_key = st.get("scroll") == min(before + m["lines"], total - m["lines"])
        for _ in range(total // m["lines"] + 2):
            verb(gc, log, "press down")
        st = wait(gc, log, lambda s: s.get("scroll") == total - m["lines"], 4.0)
        row("scroll the text: wheel, button, Page Down, end", ok_wheel and ok_button and ok_key and st.get("scroll") == total - m["lines"],
            "wheel %s, button %s, Page Down %s, end scroll=%s of %d lines (%d shown)" % (ok_wheel, ok_button, ok_key, st.get("scroll"), total, m["lines"]))
        shots.append(gc.sh("wiki_entry_end"))
        for _ in range(total // (200 * WHEEL_LINES) + 1):
            wheel(gc, "detail", 200)
        st = wait(gc, log, lambda s: s.get("scroll") == 0, 3.0)
        row("the wheel stops at the top", st.get("scroll") == 0, "scroll=%s" % st.get("scroll"))
    else:
        row("scroll the text", None, "the longest entry fits the pane")

    # a link and Back: the linked entry's links are its last lines
    if linked is not None:
        verb(gc, log, "input " + linked["name"].lower())
        time.sleep(0.5)
        st = do(gc, log, "row0")
        for _ in range(st.get("lines", 0) // m["lines"] + 1):
            verb(gc, log, "press down")
        st = wait(gc, log, lambda s: s.get("links", 0) > 0, 3.0)
        scroll_before, first_link = st.get("scroll"), st.get("firstlink", -1)
        shots.append(gc.sh("wiki_links"))
        # the links are the entry's last lines, one each, in the table's order (those without a page are not shown)
        lower = {e["name"].lower() for e in entries}
        shown = [k for k in linked["links"] if k.lower() in lower]
        index = scroll_before + first_link - (st.get("lines", 0) - len(shown))
        target = shown[index] if first_link >= 0 and 0 <= index < len(shown) else None
        if first_link >= 0:
            click_widget(gc, "Btn_line%d" % first_link)
        st2 = wait(gc, log, lambda s: s.get("selected") != linked["name"], 3.0)
        row("follow a link by a real click", st.get("selected") == linked["name"] and first_link >= 0 and target is not None and st2.get("selected", "").lower() == target.lower() and st2.get("history") == 1,
            "from %r (links shown %s, first at line %s) to %r, history=%s" % (st.get("selected"), st.get("links"), first_link, st2.get("selected"), st2.get("history")))
        shots.append(gc.sh("wiki_link_followed"))
        click_widget(gc, "Btn_back")
        st3 = wait(gc, log, lambda s: s.get("selected") == linked["name"], 3.0)
        row("Back returns", st3.get("selected") == linked["name"] and st3.get("history") == 0 and st3.get("scroll") == scroll_before,
            "selected=%r history=%s scroll=%s (was %s)" % (st3.get("selected"), st3.get("history"), st3.get("scroll"), scroll_before))
        verb(gc, log, "box")
    else:
        row("follow a link", None, "no entry of the table links to another entry")

    # a search hit deep in an entry: opened from the search, the text starts near the first line with the typed words, and that line is marked
    hit = deep_hit(entries, m["lines"])
    if hit is not None:
        hit_entry, hit = hit
        verb(gc, log, "input " + hit)
        time.sleep(0.5)
        st = do(gc, log, "row0")
        match, total = st.get("match", -1), st.get("lines", 0)
        row("an entry opened from a search starts at the hit", st.get("selected") == hit_entry["name"] and match >= m["lines"] and
            st.get("scroll") == min(match - 2, total - m["lines"]), "query %r: selected=%r first hit line %s, scroll=%s of %s lines" % (
                hit, st.get("selected"), match, st.get("scroll"), total))
        shots.append(gc.sh("wiki_search_hit"))
        verb(gc, log, "box")
        time.sleep(0.5)
    else:
        row("an entry opened from a search starts at the hit", None, "no line deep in the long entry that only it has")

    # closing: Esc and the key; a search left in the box is still there on the next opening, with the entry that was shown
    click_empty(gc)
    time.sleep(0.3)
    before = state(gc, log)
    gc.g.press("esc")
    st = wait(gc, log, lambda s: s.get("open") == 0, 3.0)
    row("Esc closes", st.get("open") == 0, "open=%s" % st.get("open"))
    time.sleep(0.6)
    shots.append(gc.sh("wiki_closed"))
    _by, st = open_panel(gc, log)
    row("reopens with the search and the entry as they were", bool(before.get("query")) and st.get("query") == before.get("query") and st.get("selected") == before.get("selected"),
        "query=%r selected=%r (before: %r, %r)" % (st.get("query"), st.get("selected"), before.get("query"), before.get("selected")))
    gc.g.press(KEY)
    st = wait(gc, log, lambda s: s.get("open") == 0, 3.0)
    row("the key closes", st.get("open") == 0, "open=%s" % st.get("open"))
    time.sleep(0.6)
    open_panel(gc, log)
    click_widget(gc, wiki_layout.INPUT)
    time.sleep(0.4)
    clear_box(gc, log)
    gc.g.press("esc")
    st = wait(gc, log, lambda s: s.get("open") == 0, 3.0)
    row("Esc closes from the search box", st.get("open") == 0, "open=%s" % st.get("open"))
    if st.get("open") != 0:
        close_panel(gc, log)
    time.sleep(0.6)
    _by, st = open_panel(gc, log)
    row("with an empty box it opens on Welcome again", st.get("selected") == ("Welcome" if has_welcome else "") and st.get("query") == "",
        "selected=%r query=%r" % (st.get("selected"), st.get("query")))
    close_panel(gc, log)

    # with the panel closed the key's letter is the game's again; in classic graphics the key prints one line and nothing opens
    if gc.set_graphics("legacy"):
        time.sleep(1.5)
        n0 = state(gc, log).get("notices", 0)
        gc.g.press(KEY)
        time.sleep(1.0)
        st = state(gc, log)
        row("classic graphics: a notice, no panel", st.get("open") == 0 and st.get("notices", 0) == n0 + 1, "open=%s notices %s -> %s" % (st.get("open"), n0, st.get("notices")))
        shots.append(gc.sh("wiki_classic_notice"))
        gc.set_graphics("hd")
        time.sleep(1.0)
    else:
        row("classic graphics", False, "legacy graphics not reached")

    st = state(gc, log)
    log.append("final %s" % st)
    ok = all(r[1] for r in rows if r[1] is not None) and not st.get("faults") and not st.get("textfails")
    gc.finish("wiki", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else ("skip" if r[1] is None else "FAIL")) for r in rows), mark, shots, log)


LOOK_SIZES = ((1600, 900), (1280, 720))
LOOK_ENTRIES = ("Death Pit Stake", "Cornerstone of the World")  # a unique with all its tiers in one entry, and one with 149 skill lines


def run_look(gc):
    mark = gc.engine_mark()
    log, shots, rows, row = rows_helper()
    cats, entries = read_table()
    long_entry, _linked, _cat_index, _cat_count, word = picks(cats, entries)
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    h = gc.g.need_window()
    try:
        for w, hgt in LOOK_SIZES:
            gc.g.CLIENT_W, gc.g.CLIENT_H = w, hgt
            r = gc.g.fit_window(h)
            time.sleep(2.0)
            row("%dx%d window" % (w, hgt), (r[2] - r[0], r[3] - r[1]) == (w, hgt), "client rect %s" % (r,))
            _by, st = open_panel(gc, log)
            row("%d open" % w, st.get("open") == 1, "open=%s" % st.get("open"))
            shots.append(gc.sh("wiki_look_%d_welcome" % w))
            verb(gc, log, "input " + long_entry["name"].lower())
            time.sleep(0.5)
            st = do(gc, log, "row0")
            row("%d long entry" % w, st.get("selected") == long_entry["name"], "selected=%r" % st.get("selected"))
            shots.append(gc.sh("wiki_look_%d_entry" % w))
            verb(gc, log, "press down")
            time.sleep(0.4)
            shots.append(gc.sh("wiki_look_%d_entry_page2" % w))
            verb(gc, log, "input " + word)
            time.sleep(0.6)
            shots.append(gc.sh("wiki_look_%d_search" % w))
            for name in LOOK_ENTRIES:  # the long entries of the exporter's table, when the installed table has them
                if not any(e["name"] == name for e in entries):
                    continue
                verb(gc, log, "input " + name.lower())
                time.sleep(0.5)
                st = do(gc, log, "row0")
                tag = "wiki_look_%d_%s" % (w, name.lower().replace(" ", "_"))
                row("%d %s" % (w, name), st.get("selected") == name, "selected=%r lines=%s" % (st.get("selected"), st.get("lines")))
                shots.append(gc.sh(tag))
                wheel(gc, "detail", -12)
                st = state(gc, log)
                log.append("%s after 12 wheel notches: scroll=%s of %s lines" % (name, st.get("scroll"), st.get("lines")))
                shots.append(gc.sh(tag + "_scrolled"))
            verb(gc, log, "box")
            close_panel(gc, log)
    finally:
        gc.g.CLIENT_W, gc.g.CLIENT_H = 1600, 900
        gc.g.fit_window(h)
        time.sleep(1.0)
    st = state(gc, log)
    ok = all(r[1] for r in rows if r[1] is not None) and not st.get("faults")
    gc.finish("wikilook", ok, "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows), mark, shots, log)


LAB = (("codes", "DetailText20_0 ^1red ^4gold |c4pipe-four |cffff0000pipe-red|r plain"),
       ("ruler_digits", "DetailText22_0 " + "0123456789" * 8),
       ("ruler_capitals", "DetailText23_0 " + "THE QUICK BROWN FOX JUMPS OVER THE LAZY DOG AND THEN RUNS BACK HOME AGAIN TODAY"),
       ("ruler_prose", "DetailText24_0 The quick brown fox jumps over the lazy dog and then the quick brown fox jumps over it."),
       ("ruler_row_digits", "RowText20_0 " + "0123456789" * 6),
       ("ruler_row_prose", "RowText21_0 The quick brown fox jumps over the lazy dog and then again."))


def run_lab(gc):
    mark = gc.engine_mark()
    log, shots, rows, row = rows_helper()
    gc.goto(1, timeout=60)
    gc.set_graphics("hd")
    _by, st = open_panel(gc, log)
    row("open", st.get("open") == 1, "open=%s" % st.get("open"))
    shots.append(gc.sh("wiki_lab_start"))
    for name, text in LAB:
        ok, _lines = gc.Hl("wiki raw " + text, log)
        time.sleep(0.5)
        row(name, ok, text)
    shots.append(gc.sh("wiki_lab_texts"))
    close_panel(gc, log)
    st = state(gc, log)
    gc.finish("wikilab", all(r[1] for r in rows) and not st.get("faults"), "; ".join("%s %s" % (r[0], "ok" if r[1] else "FAIL") for r in rows), mark, shots, log)


def main() -> int:
    if len(sys.argv) == 3 and sys.argv[1] == "use-table":
        TABLE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(sys.argv[2], TABLE)
        cats, entries = read_table()
        print("%s: %d categories, %d entries" % (TABLE.relative_to(ROOT), len(cats), len(entries)))
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
