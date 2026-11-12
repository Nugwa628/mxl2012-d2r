// The in-game wiki panel (wiki.cpp, wiki_logic.h, docs/wiki-panel.md; off word wiki): its own Controls action opens a native HD panel that
// lists and shows the mod's own reference text (uniques, sets, runewords, base items, cube recipes, monsters, skills, ubers and the prose
// pages) from the content table data/mxl2012-wiki/wiki.tsv in the mod. It reads no game state and changes nothing, so it has no single-player
// gate. HD graphics only.
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// `selfPath` is this DLL's path (UTF-8): the content table is read from the mod folder relative to it. True when the part is on.
auto InstallWiki(const D2RL::PluginContext* context, const char* selfPath, char* report, size_t reportSize) noexcept -> bool;

// One line of counters and state for the `mxl` console line and the harness.
void WikiStatus(char* out, size_t size) noexcept;

// Test harness: `open`, `close`, `press <button>` ("cat1", "row0", "line3", "next", "down", "back", ...), `input <text>` (instead of the
// search box), `box` (the search box again), `raw <widget> <text>` (sets one text box as given: `\n` is a line break, `^` D2R's colour prefix).
// False when the part is off or the argument is unknown.
auto WikiHarness(const char* verb, const char* argument) noexcept -> bool;
