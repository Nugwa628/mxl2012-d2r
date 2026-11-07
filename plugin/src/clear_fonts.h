// The clear legacy fonts setting (clear_fonts.cpp, clear_fonts_logic.h; lane fonttoggle). Off word: clearfonts.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// mxl2012-core.toml [fonts] legacy_clear_fonts (default false) and the Controls action "Clear Legacy Fonts" (mxl_clear_fonts,
// default Ctrl+F) switch the classic text between D2R's fonts and the clear set in data/local/font/latin/clear/, at once.
// selfPath: this DLL's path (UTF-8), to find the mod's files. True when the patches went in.
auto InstallClearFonts(const D2RL::PluginContext* context, const char* selfPath, char* report, size_t reportSize) noexcept -> bool;

// Test harness (UI thread): the setting and the fonts' state ("on=1 wanted=0 live=0 files=1 ...").
void ClearFontsStatus(char* out, size_t size) noexcept;
// Test harness (UI thread): what the key does (on < 0: flip), or set it on (1) / off (0); writes the settings file. False when off.
auto ClearFontsSet(int on) noexcept -> bool;
