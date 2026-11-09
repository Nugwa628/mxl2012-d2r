"""Generate the HD menu ribbon override and its localized mod credit.

The character panel is separate. Controller ribbons inherit this PC ribbon.
D2RLoader 1.3.1 supplies D2RLoaderText in its ribbon override; retain that
caption when our mod takes precedence over the loader's layout.
"""
import json
import re

import fxpaths
from rotw_stash_legacy import lenient_json
from tbl2json import LANGS

KEY = "mxl2012:MenuCredit"
TEXT = "Median XL 2012\nBy BrotherLaz\n(D2R Fan Port)"


def build(source, data):
    panel = lenient_json(source.read_text("utf-8-sig"))
    ribbon = next(c for c in panel["children"] if c["name"] == "Ribbon")
    ribbon["children"].extend([
        {"type": "TextBoxWidget", "name": "D2RLoaderText", "fields": {
            "rect": {"x": 221, "y": 568, "width": 387, "height": 38, "scale": 0.99},
            "text": "D2RLOADER", "style": {
                "pointSize": "$MediumLargeFontSize", "spacing": {"kerning": 1.35},
                "dropShadow": {"shadowColor": {"r": 255, "g": 0, "b": 0, "a": 255}, "offset": {"x": 1, "y": 1}},
                "alignment": {"h": "left", "v": "center"},
                "fontColor": {"r": 103, "g": 84, "b": 66, "a": 255}}}},
        {"type": "TextBoxWidget", "name": "MedianMenuCredit", "fields": {
            "rect": {"x": 64, "y": 620, "width": 680, "height": 175},
            "fontType": "16pt", "text": "@" + KEY,
            "style": {"pointSize": 40, "alignment": {"h": "center", "v": "center"},
                      "fontColor": {"r": 199, "g": 179, "b": 139, "a": 255},
                      "dropShadow": "$DefaultDropShadow",
                      "options": {"newlineHandling": "standard", "lineWrap": True}}}}])
    target = data / "global/ui/layouts/mainmenubuttonribbonhd.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = re.sub(r'"@(?!mxl2012:|d2r:)([^"\n]+)"', r'"@d2r:\1"', json.dumps(panel, indent=2))
    target.write_text(encoded + "\n", encoding="utf-8")
    strings = data / "local/lng/strings/mxl2012/menu_credit.json"
    strings.parent.mkdir(parents=True, exist_ok=True)
    strings.write_text(json.dumps([{"Key": KEY.split(":", 1)[1], **dict.fromkeys(LANGS, TEXT)}], indent=2) + "\n", encoding="utf-8")



if __name__ == "__main__":
    build(fxpaths.D2R / "data/global/ui/layouts/mainmenubuttonribbonhd.json", fxpaths.OUT)

