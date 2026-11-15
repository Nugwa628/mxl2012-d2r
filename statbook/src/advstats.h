// The Advanced Stats panel in groups with headings, Avoid and the other own rows, rebuilt when a buff turns a row on or off
// (advstats.cpp, bugs #581 / #582).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>
#include <cstdint>

// Hooks the panel's list builder 0x14eaf40 and row text 0x14eb250 and wraps its Update slot (advstats_logic.h). The report
// gets one entry. Returns true when all three are in place; on any byte difference nothing is written.
auto InstallAdvancedStats(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Lists built since load (panel opened or rebuilt), of them rebuilds from the Update wrapper, own row texts, rows last listed,
// and how the strings were found (0 none yet, 1 mxl2012: keys, 2 English fallback).
void AdvancedStatsCounts(long* builds, long* rebuilds, long* texts, long* lastRows, int* strings) noexcept;
// The stat reader the Stat Book's pages use (GetStat >> ValShift), usable without the panel hooks; false: bytes differ.
auto InitStatReader(const D2RL::PluginContext* context) noexcept -> bool;
auto ShiftedStat(void* unit, uint32_t stat, int32_t layer) noexcept -> int32_t;
// The game's own Advanced Stats line of `stat` for `unit` (0x14eb250 with a stand-in panel that holds only the unit; the All Stats
// list of the sheet host). False when the function's bytes differed at InitStatReader or it faulted.
auto StatLine(void* unit, uint16_t stat, char* out, size_t size) noexcept -> bool;
// A string by key ("mxl2012:<key>" first, then <key>) from D2RLoader's localization; false when neither is there.
auto LookupString(const char* key, char* out, size_t size) noexcept -> bool;
