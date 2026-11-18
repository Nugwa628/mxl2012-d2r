// Unit tests of the D2R-XL 2012 additions to Floating Damage (legacy_projection.hpp, patch 0001). Built and run by
// tools/build_floatingdamage.ps1 (target floating_damage_mxl_tests).
#include "legacy_projection.hpp"

#include <cmath>
#include <cstdio>

namespace {
int failures = 0;

void Expect(bool ok, const char* what) {
    if (!ok) {
        std::printf("FAIL: %s\n", what);
        ++failures;
    }
}

bool Near(float a, float b) { return std::fabs(a - b) < 0.01f; }

void ClassicPoint() {
    using FloatingDamageMxl::ClassicUnitPoint;
    // the player: UpdateCamera sets the view so the player stands at (W / 2, H / 2 - 16), ViewOffsetY adds 8 back
    const auto p = ClassicUnitPoint(5000, 3000, 5000 - 400, 3000 - 300 + 16 - 8, 0);
    Expect(Near(p.x, 400.0f) && Near(p.y, 292.0f), "player point at 800x600");
    const auto head = ClassicUnitPoint(5000, 3000, 4600, 2708);
    Expect(Near(head.y, 292.0f - FloatingDamageMxl::LegacyHeadOffset), "head offset raises the point");
    // a side panel open: the view offset helper subtracts the shift, the unit moves right by it
    const auto shifted = ClassicUnitPoint(5000, 3000, 4600 - 200, 2708, 0);
    Expect(Near(shifted.x, 600.0f), "panel shift moves the point");
}

void Compose() {
    using FloatingDamageMxl::ClassicToDisplay;
    float x{}, y{};
    // 800x600 in a 1600x900 window: 1.5x, 200 px side bars
    Expect(ClassicToDisplay(400.0f, 300.0f, 800, 600, 1600.0f, 900.0f, x, y) && Near(x, 800.0f) && Near(y, 450.0f),
           "800x600 centre in 1600x900");
    Expect(ClassicToDisplay(0.0f, 0.0f, 800, 600, 1600.0f, 900.0f, x, y) && Near(x, 200.0f) && Near(y, 0.0f),
           "800x600 left edge after the side bar");
    // D2R Legacy 16:9: 1066x600 fills the 16:9 window (half a pixel bar)
    Expect(ClassicToDisplay(533.0f, 300.0f, 1066, 600, 1600.0f, 900.0f, x, y) && Near(x, 800.0f) && Near(y, 450.0f),
           "1066x600 centre in 1600x900");
    Expect(ClassicToDisplay(1066.0f, 600.0f, 1066, 600, 1600.0f, 900.0f, x, y) && Near(x, 1599.5f),
           "1066x600 right edge");
    // 640x480 in 1920x1080: 2.25x, 240 px bars
    Expect(ClassicToDisplay(320.0f, 240.0f, 640, 480, 1920.0f, 1080.0f, x, y) && Near(x, 960.0f) && Near(y, 540.0f),
           "640x480 centre in 1920x1080");
    // outside the display, unusable sizes
    Expect(!ClassicToDisplay(-200.0f, 300.0f, 800, 600, 1600.0f, 900.0f, x, y), "left of the side bar is off screen");
    Expect(!ClassicToDisplay(400.0f, -1.0f, 800, 600, 1600.0f, 900.0f, x, y), "above the window is off screen");
    Expect(!ClassicToDisplay(400.0f, 300.0f, 0, 600, 1600.0f, 900.0f, x, y), "zero classic width refused");
    Expect(!ClassicToDisplay(400.0f, 300.0f, 800, 600, 0.0f, 900.0f, x, y), "zero display refused");
    Expect(!ClassicToDisplay(400.0f, 300.0f, 100000, 600, 1600.0f, 900.0f, x, y), "absurd classic width refused");
}

void DpsCounter() {
    using FloatingDamageMxl::DisplayRect;
    DisplayRect frame{};
    DisplayRect hud{};
    // HD: no classic screen, the author's placement over the whole window
    Expect(!FloatingDamageMxl::LegacyFrame(0, 0, 1600.0f, 900.0f, frame, hud), "HD has no legacy frame");
    // 800x600 in 1600x900: 1.5x, the picture from 200 to 1400, the HUD 156 px high at the bottom
    Expect(FloatingDamageMxl::LegacyFrame(800, 600, 1600.0f, 900.0f, frame, hud)
               && Near(frame.left, 200.0f) && Near(frame.right, 1400.0f) && Near(hud.left, 200.0f)
               && Near(hud.right, 1400.0f) && Near(hud.top, 744.0f),
           "800x600 frame and HUD");
    float x{};
    float y{};
    // the shipped bottom left (2 %, 98 %): inside the picture, not the side bar, and above the life globe
    FloatingDamageMxl::PlaceInArea(frame, &hud, 2.0f, 98.0f, 80.0f, 30.0f, 15.0f, 9.0f, x, y);
    Expect(Near(x, 279.0f) && x - 40.0f >= frame.left, "4:3 counter inside the picture");
    Expect(Near(y, 720.0f) && y + 15.0f <= hud.top, "4:3 counter above the classic HUD");
    // 1066x600 (Legacy 16:9) in 1600x900: the picture fills the window, the HUD is centred, the corner is free
    Expect(FloatingDamageMxl::LegacyFrame(1066, 600, 1600.0f, 900.0f, frame, hud)
               && Near(frame.left, 0.5f) && Near(hud.left, 200.0f) && Near(hud.right, 1400.0f),
           "1066x600 frame and HUD");
    FloatingDamageMxl::PlaceInArea(frame, &hud, 2.0f, 98.0f, 80.0f, 30.0f, 15.0f, 9.0f, x, y);
    Expect(Near(x, 87.48f) && Near(y, 858.0f), "16:9 counter in the bottom left corner, left of the HUD");
    // no HUD given: only the area and margins count
    FloatingDamageMxl::PlaceInArea(frame, nullptr, 50.0f, 98.0f, 80.0f, 30.0f, 15.0f, 9.0f, x, y);
    Expect(Near(x, 800.0f) && Near(y, 858.0f), "centred at the bottom without a HUD");
}

void NumberSize() {
    using FloatingDamageMxl::LegacyNumberSize;
    // the shipped legacy_text_scale 2.5: text_size 38 at 900 px (scale 0.4167) is 15.83 px in HD, 39.58 px in legacy
    Expect(Near(LegacyNumberSize(38.0f * 900.0f / 2160.0f, false, 2.5f), 15.833f), "HD keeps the size");
    Expect(Near(LegacyNumberSize(38.0f * 900.0f / 2160.0f, true, 2.5f), 39.583f), "legacy is 2.5x");
    Expect(Near(LegacyNumberSize(20.0f, true, 1.0f), 20.0f), "scale 1 keeps the size");
}

void Rip() {
    // UpdateCamera 0xb9bbd: mov eax, [rip + 0x021e71a5], next instruction 0xb9bc3 -> 0x22a0d68 (ScreenSizeX)
    Expect(FloatingDamageMxl::RipTarget(0xb9bc3, 0x021e71a5) == 0x22a0d68, "rip target forward");
    Expect(FloatingDamageMxl::RipTarget(0x1000, -0x10) == 0xff0, "rip target backward");
}
}  // namespace

int main() {
    ClassicPoint();
    Compose();
    DpsCounter();
    NumberSize();
    Rip();
    if (failures) {
        std::printf("%d failure(s)\n", failures);
        return 1;
    }
    std::printf("FloatingDamageMxlTests: all passed\n");
    return 0;
}
