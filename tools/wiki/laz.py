#!/usr/bin/env python3
"""Brother Laz's character pages (https://modsbylaz.vn.cz, used with his permission and credit) for the wiki: the class
prose and each skill's flavour text.

  py -3 tools/wiki/laz.py fetch [--force]    download the seven class pages and the item-only skills page into
                                             work/wiki/laz/ (raw HTML; files already there are kept unless --force)
  py -3 tools/wiki/laz.py intros             write tools/wiki/intro/<Class>.wiki: the class page's hand-written part
                                             (Laz's prose), which gen_skills.py puts above its generated part (which
                                             ends with the source credit) when it creates the page

The pages are Latin-1 / Windows-1252 HTML: a `<p class="genbig">` title per section, `<p class="content">` paragraphs,
skill tables with the name in a `<span>` (grey; red for devotion skills), the flavour text and an `<i>Effect: ...</i>` line, and on the
item-only page the classes that can get a skill as an oskill (`<img class="charicon" title="Amazon">`).
"""
import argparse
import html
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
LAZ = ROOT / "work" / "wiki" / "laz"
INTRO = Path(__file__).resolve().parent / "intro"
SITE = "https://modsbylaz.vn.cz/"
CLASS_PAGES = {"Amazon": "amazon", "Assassin": "assassin", "Barbarian": "barbarian", "Druid": "druid",
               "Necromancer": "necromancer", "Paladin": "paladin", "Sorceress": "sorceress"}
ITEM_ONLY = "itemonly"
# sections the generator writes from the port's own tables (base stats) or lists (the skill tables)
GENERATED_SECTIONS = {"BASE STATS", "SKILLS", "UBERSKILLS", "INNATE SKILL", "INNATE SKILLS"}
SECTION = re.compile(r'<p class="genbig">(.*?)</p>(.*?)(?=<p class="genbig">|</div>\s*</body>|$)', re.S)
ROW = re.compile(r'<tr><td[^>]*><span class="[a-z]+">(.*?)</span>(.*?)(?=<tr>|</table>)', re.S)
SMALL_WORDS = {"of", "the", "and", "a", "an", "in", "on", "to"}
UPPER_WORDS = {"xl": "XL", "ii": "II"}


def read(name: str) -> str:
    p = LAZ / f"{name}.html"
    return p.read_bytes().decode("cp1252", errors="replace") if p.exists() else ""


def fetch(force: bool) -> int:
    LAZ.mkdir(parents=True, exist_ok=True)
    for name in list(CLASS_PAGES.values()) + [ITEM_ONLY]:
        p = LAZ / f"{name}.html"
        if p.exists() and not force:
            continue
        req = urllib.request.Request(SITE + p.name, headers={"User-Agent": "mxl2012-d2r-wikitools"})
        with urllib.request.urlopen(req, timeout=60) as r:
            p.write_bytes(r.read())
        print(f"fetched {p.name}")
    return 0


def text(fragment: str) -> str:
    """Plain text of an HTML fragment, whitespace collapsed."""
    t = re.sub(r"<br\s*/?>", "\n", fragment)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    return "\n".join(" ".join(x.split()) for x in t.split("\n")).strip()


def wiki(fragment: str) -> str:
    """Wikitext of a section body: paragraphs, ''italics'', the black boxes as bullet lists."""
    out = []
    for m in re.finditer(r'<div class="black">(.*?)</div>|<p class="content">(.*?)</p>', fragment, re.S):
        if m.group(1) is not None:
            out.append("\n".join("* " + x for x in text(m.group(1)).split("\n") if x))
            continue
        body = m.group(2)
        if '<div class="black">' in body:
            continue
        body = re.sub(r"</?i>", "''", body)
        body = re.sub(r"</?u>", "", body)
        t = text(body)
        if t:
            out.append(t.replace("\n", "<br>\n"))
    return "\n\n".join(out)


def title_case(title: str) -> str:
    words = title.lower().split()
    return " ".join(UPPER_WORDS.get(w) or (w if i and w in SMALL_WORDS else w[:1].upper() + w[1:])
                    for i, w in enumerate(words))


def sections(name: str) -> list[tuple[str, str]]:
    return [(text(t), body) for t, body in SECTION.findall(read(name))]


def skill_rows(fragment: str) -> list[dict]:
    out = []
    for name, rest in ROW.findall(fragment):
        cells = rest.split("<td", 2)
        last = "<td" + cells[-1] if len(cells) > 1 else rest
        classes = re.findall(r'class="charicon"[^>]*title="([^"]+)"', last)
        effect = re.search(r"<i>(.*?)</i>", last, re.S)
        last = re.sub(r"<img[^>]*>", "", last)
        flavour = text(re.sub(r"<i>.*?</i>", "", last, flags=re.S).split(">", 1)[-1])
        out.append({"name": " ".join(text(name).split()), "flavour": flavour, "effect": text(effect.group(1)) if effect else "",
                    "classes": classes})
    return out


def skill_texts() -> dict[str, dict]:
    """UPPER-CASE skill name -> {"flavour", "effect", "source"} from all eight pages."""
    out = {}
    for page in list(CLASS_PAGES.values()) + [ITEM_ONLY]:
        for title, body in sections(page):
            for r in skill_rows(body):
                rec = {"effect": r["effect"], "source": f"{SITE}{page}.html"}
                if r["flavour"]:
                    rec["flavour"] = r["flavour"]
                out.setdefault(r["name"].upper(), rec)
    return out


def item_only_names() -> dict[str, dict]:
    """UPPER-CASE name -> {"group", "classes"} of the skills on Laz's item-only page (group: its table's section)."""
    out = {}
    for title, body in sections(ITEM_ONLY):
        for r in skill_rows(body):
            out.setdefault(r["name"].upper(), {"group": title_case(title), "classes": r["classes"]})
    return out


def intro(cls: str) -> str:
    """The class page's hand-written part from Laz's page: the lead, then his sections as level-2 headings."""
    page = CLASS_PAGES[cls]
    parts = []
    for i, (title, body) in enumerate(sections(page)):
        if title.upper() in GENERATED_SECTIONS:
            continue
        w = wiki(body)
        if not w:
            continue
        parts.append(w if i == 0 else f"== {title_case(title)} ==\n{w}")
    return "\n\n".join(parts)


def credit(page: str) -> str:
    return (f'<div class="source-credit">From [{SITE}{page}.html Brother Laz\'s Median XL documentation], '
            f"used with permission.</div>")


def cmd_intros() -> int:
    INTRO.mkdir(exist_ok=True)
    for cls, page in CLASS_PAGES.items():
        body = intro(cls)
        if not body:
            print(f"{cls}: no {page}.html in {LAZ} (run fetch first)")
            continue
        (INTRO / f"{cls}.wiki").write_text(body + "\n", encoding="utf-8")
        print(f"wrote intro/{cls}.wiki ({len(body)} characters)")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch")
    f.add_argument("--force", action="store_true")
    sub.add_parser("intros")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    return fetch(args.force) if args.cmd == "fetch" else cmd_intros()


if __name__ == "__main__":
    sys.exit(main())
