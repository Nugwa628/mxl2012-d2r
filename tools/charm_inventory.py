"""The mod's charm inventory: ONE switch for the build, the installs and the package.

  "charminv"  Dimentio's CharmInv 1.0.1 (docs/bundled-plugins.md "CharmInv")
  "invtabs"   our Inventory Tabs plugin on wild-healer's code (docs/invtabs.md)

Only one of them can own D2RLoader's custom player page, so the mod data is built for one of them (tools/build.py):

  charminv  data/global/excel/d2rloader/charm-inv/*.txt (tools/charm_inv.py); nothing of invtabs, and no Charms button in
            the classic inventory layouts (CharmInv has no classic panel: the button would open nothing)
  invtabs   INVTABS_DATA (tab type tables, HD cells, classic panel art) and the classic inventory's Charms button; no
            CharmInv tables

CHARM_INVENTORY is the default: invtabs since the release after 0.1.19 (owner decision, 2026-11-11). One run takes another with `--charm-inventory NAME` (tools/build.py, package_release.py)
or the environment variable MXL2012_CHARM_INVENTORY. package_release.py, verify_package.py and install_mod.py refuse or
name data that was built for the other one (data_problems).
"""
import os
import re
from pathlib import Path

CHARM_INVENTORY = "invtabs"
CHARM_INVENTORIES = ("charminv", "invtabs")
ENV = "MXL2012_CHARM_INVENTORY"

# invtabs' files in the mod's data folder (mxl2012.mpq/data), made by the build's invtabs steps
INVTABS_DATA = ("global/excel/d2rloader/invtabs/tabs.txt", "global/excel/d2rloader/invtabs/types_charms.txt",
                "hd/global/ui/panel/invtabs/stockgrid.sprite", "hd/global/ui/panel/invtabs/stockgrid.lowend.sprite",
                "global/ui/panel/invtabs_charms.dc6", "global/ui/panel/invtabs_tab_charms.dc6", "global/ui/panel/invtabs_button.dc6")
CHARMINV_DATA = ("global/excel/d2rloader/charm-inv/charminv.txt", "global/excel/d2rloader/charm-inv/charminvtypes.txt")
CLASSIC_INVENTORY = ("global/ui/layouts/playerinventoryoriginallayout.json", "global/ui/layouts/playerinventoryexpansionlayout.json")
BUTTON = re.compile(r'"name":\s*"InvTabsButton"')  # tools/invtabs_legacy.BUTTON_NAME (a unit test keeps the two equal)


def chosen(value: str = None) -> str:
    """The charm inventory of this run: `value` (a command line option), else MXL2012_CHARM_INVENTORY, else CHARM_INVENTORY."""
    name = value or os.environ.get(ENV) or CHARM_INVENTORY
    if name not in CHARM_INVENTORIES:
        raise SystemExit(f"charm inventory {name!r}: one of {', '.join(CHARM_INVENTORIES)}")
    return name


def has_button(data: Path, rel: str) -> bool:
    p = Path(data) / rel
    return p.is_file() and BUTTON.search(p.read_text("utf-8-sig")) is not None


def data_problems(data: Path, choice: str) -> list:
    """What is wrong with a mod data folder (work/mod/data or mxl2012.mpq/data) for the charm inventory `choice`: the other
    one's files in it, or its own missing. A classic inventory layout that is not there at all (a byte copy of D2R's is
    left out of a package; unit test folders) is not judged."""
    data = Path(data)
    fix = f"build the data for it: tools/build.py --charm-inventory {choice} (docs/invtabs.md \"Build wiring\")"
    if choice == "invtabs":
        problems = [f"{rel} is missing (invtabs' data; {fix})" for rel in INVTABS_DATA if not (data / rel).is_file()]
        problems += [f"{rel} has no Charms button (invtabs' classic inventory button; {fix})"
                     for rel in CLASSIC_INVENTORY if (data / rel).is_file() and not has_button(data, rel)]
        problems += [f"{rel} is CharmInv's table, the data was built for CharmInv ({fix})" for rel in CHARMINV_DATA if (data / rel).is_file()]
        return problems
    problems = [f"{rel} is invtabs' file, the data was built for invtabs ({fix})" for rel in INVTABS_DATA if (data / rel).is_file()]
    problems += [f"{rel} has invtabs' Charms button, which opens nothing with CharmInv ({fix})"
                 for rel in CLASSIC_INVENTORY if has_button(data, rel)]
    return problems


def built_for(data: Path) -> str:
    """The charm inventory a data folder was built for: "invtabs" when it holds any of invtabs' files or the button."""
    data = Path(data)
    if any((data / rel).is_file() for rel in INVTABS_DATA) or any(has_button(data, rel) for rel in CLASSIC_INVENTORY):
        return "invtabs"
    return "charminv"
