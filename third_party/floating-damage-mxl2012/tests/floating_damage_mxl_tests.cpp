// Unit tests of the D2R-XL 2012 additions to Floating Damage (legacy_projection.hpp, patch 0001; font_loading.hpp, patch
// 0005; general_key.hpp, patch 0006). Built and run by tools/build_floatingdamage.ps1 and tools/build_thirdparty_linux.py (target
// floating_damage_mxl_tests).
#include "font_loading.hpp"
#include "general_key.hpp"
#include "legacy_projection.hpp"

#include <cmath>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>

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
// A fresh ImGui context per test: the renderer loads its fonts right after creating its context, outside any frame.
struct Context {
    ImGuiContext* ctx = ImGui::CreateContext();
    Context() { ImGui::GetIO().IniFilename = nullptr; }  // as the renderer: no imgui.ini
    ~Context() { ImGui::DestroyContext(ctx); }
};

// head: the first bytes, then zeros up to size
std::string TempFile(const char* name, std::string head, std::size_t size) {
    const auto path = std::filesystem::temp_directory_path() / name;
    head.resize(size, '\0');
    std::ofstream(path, std::ios::binary | std::ios::trunc).write(head.data(), static_cast<std::streamsize>(head.size()));
    return path.string();
}

void MissingFont() {
    // Proton has no segoeui.ttf: Dear ImGui's AddFontFromFileTTF would open its error tooltip (ImGui::Begin) outside a
    // frame with no font and crash; AddFontFileIfPresent returns nullptr and touches nothing
    Context c;
    ImFontAtlas* atlas = ImGui::GetIO().Fonts;
    const auto missing = (std::filesystem::temp_directory_path() / "fd-mxl-no-such-font.ttf").string();
    std::filesystem::remove(missing);
    ImFontConfig config{};
    Expect(FloatingDamageMxl::AddFontFileIfPresent(atlas, missing.c_str(), 24.0f, &config, nullptr) == nullptr,
           "missing font file -> nullptr");
    Expect(atlas->Fonts.Size == 0 && atlas->ConfigData.Size == 0, "missing font file adds nothing to the atlas");
    Expect(c.ctx->Windows.Size == 0, "missing font file opens no window (no error tooltip)");
    Expect(c.ctx->ErrorFirst, "missing font file reports no ImGui error");
    Expect(FloatingDamageMxl::AddFontFileIfPresent(atlas, "", 24.0f, &config, nullptr) == nullptr, "empty path -> nullptr");
    Expect(FloatingDamageMxl::AddFontFileIfPresent(nullptr, missing.c_str(), 24.0f, &config, nullptr) == nullptr,
           "no atlas -> nullptr");
    // the renderer's fallback for that index: ImGui's built-in font, then a normal frame
    Expect(atlas->AddFontDefault() != nullptr, "built-in font added");
    bool fellBack = true;
    Expect(FloatingDamageMxl::BuildFontAtlasOrDefault(atlas, fellBack) && !fellBack, "built-in font builds");
    ImGuiIO& io = ImGui::GetIO();
    io.DisplaySize = ImVec2(800.0f, 600.0f);
    io.DeltaTime = 1.0f / 60.0f;
    ImGui::NewFrame();
    Expect(ImGui::GetFont() == atlas->Fonts[0], "frame uses the built-in font");
    ImGui::Render();
}

void NotAFont() {
    // a file that is no font (stb_truetype would read it out of bounds): refused like a missing file
    Context c;
    ImFontAtlas* atlas = ImGui::GetIO().Fonts;
    const auto junk = TempFile("fd-mxl-not-a-font.ttf", "<html>not a font</html>", 4096);
    const auto tiny = TempFile("fd-mxl-tiny-font.ttf", std::string("\0\1\0\0", 4), 64);
    ImFontConfig config{};
    Expect(FloatingDamageMxl::AddFontFileIfPresent(atlas, junk.c_str(), 32.0f, &config, nullptr) == nullptr,
           "file that is no font -> nullptr");
    Expect(FloatingDamageMxl::AddFontFileIfPresent(atlas, tiny.c_str(), 32.0f, &config, nullptr) == nullptr,
           "font signature but 100 bytes or less -> nullptr");
    Expect(atlas->Fonts.Size == 0 && c.ctx->Windows.Size == 0, "nothing added, no window");
    const unsigned char ttf[101] = {0, 1, 0, 0};
    const unsigned char otf[101] = {'O', 'T', 'T', 'O'};
    const unsigned char ttc[101] = {'t', 't', 'c', 'f'};
    const unsigned char apple[101] = {'t', 'r', 'u', 'e'};
    Expect(FloatingDamageMxl::IsFontData(ttf, sizeof ttf) && FloatingDamageMxl::IsFontData(otf, sizeof otf)
               && FloatingDamageMxl::IsFontData(ttc, sizeof ttc) && FloatingDamageMxl::IsFontData(apple, sizeof apple),
           "TrueType, OpenType, collection and Apple signatures are fonts");
    Expect(!FloatingDamageMxl::IsFontData(ttf, 100) && !FloatingDamageMxl::IsFontData(nullptr, 4096), "short or no data");
    std::filesystem::remove(junk);
    std::filesystem::remove(tiny);
}

void UnbuildableFont() {
    // a font file with no tables: added (as AddFontFromFileTTF would), the build fails, the atlas falls back to ImGui's
    // built-in font only and is built
    Context c;
    ImFontAtlas* atlas = ImGui::GetIO().Fonts;
    const auto empty = TempFile("fd-mxl-no-tables.ttf", std::string("\0\1\0\0", 4), 4096);
    ImFontConfig config{};
    ImFont* font = FloatingDamageMxl::AddFontFileIfPresent(atlas, empty.c_str(), 32.0f, &config, nullptr);
    Expect(font != nullptr && atlas->Fonts.Size == 1, "readable font file is added");
    Expect(font != nullptr && std::string(font->ConfigData->Name) == "fd-mxl-no-tables.ttf, 32px",
           "unnamed font gets the file name and size, as AddFontFromFileTTF names it");
    bool fellBack = false;
    Expect(FloatingDamageMxl::BuildFontAtlasOrDefault(atlas, fellBack), "atlas built after the fallback");
    Expect(fellBack, "fallback reported");
    Expect(atlas->Fonts.Size == 1 && atlas->Fonts[0]->IsLoaded() && atlas->IsBuilt(), "only the built-in font, loaded");
    unsigned char* pixels = nullptr;
    int w = 0, h = 0;
    atlas->GetTexDataAsRGBA32(&pixels, &w, &h);
    Expect(pixels != nullptr && w > 0 && h > 0, "texture data for the backend");
    std::filesystem::remove(empty);
}
}  // namespace

void GeneralKey() {
    using FloatingDamageMxl::SetGeneralBool;
    // the shipped file: the value is replaced in place, comments and the other tables untouched
    std::string text = "# c\n[general]\n# Master switch.\nenabled = true\n\nshow_numbers = true # x\n\n[appearance]\nshow_numbers = true\n";
    Expect(SetGeneralBool(text, "show_numbers", false), "show_numbers set");
    Expect(text == "# c\n[general]\n# Master switch.\nenabled = true\n\nshow_numbers = false # x\n\n[appearance]\nshow_numbers = true\n",
        "show_numbers replaced in [general] only");
    // a file from before 0.1.30 (no show_numbers): added after the header, with the file's line ends
    std::string old = "[general]\r\nenabled = true\r\n[animation]\r\n";
    Expect(SetGeneralBool(old, "show_numbers", false) && old == "[general]\r\nshow_numbers = false\r\nenabled = true\r\n[animation]\r\n",
        "show_numbers added to an old file");
    Expect(SetGeneralBool(old, "show_numbers", true) && old == "[general]\r\nshow_numbers = true\r\nenabled = true\r\n[animation]\r\n",
        "show_numbers turned back on");
    Expect(SetGeneralBool(old, "enabled", false) && old.find("enabled = false\r\n") != std::string::npos, "enabled set");
    std::string commented = "[general]\n# show_numbers = true\nshow_numbers_x = 1\n";
    Expect(SetGeneralBool(commented, "show_numbers", false) && commented == "[general]\nshow_numbers = false\n# show_numbers = true\nshow_numbers_x = 1\n",
        "comments and longer keys are not the key");
    std::string last = "[general]";
    Expect(SetGeneralBool(last, "show_numbers", true) && last == "[general]\nshow_numbers = true\n", "header on the last line");
    std::string none = "[appearance]\ntext_size = 38\n";
    Expect(!SetGeneralBool(none, "show_numbers", true) && none == "[appearance]\ntext_size = 38\n", "no [general]: refused");
}

int main() {
    GeneralKey();
    ClassicPoint();
    Compose();
    DpsCounter();
    NumberSize();
    Rip();
    MissingFont();
    NotAFont();
    UnbuildableFont();
    if (failures) {
        std::printf("%d failure(s)\n", failures);
        return 1;
    }
    std::printf("FloatingDamageMxlTests: all passed\n");
    return 0;
}
