// Median XL 2012's rune letters in the runeword tooltip (rune_letters.cpp, bug #334, lane runeletters).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Answers the tooltip's rune letter lookup (call 0x2c29da) with the gems record's own cell when the cell is not one of D2R's
// r01L..r33L keys or has no text, as 1.14d draws it (rune_letters_logic.h). The report gets one entry. Returns true when the
// lookup slot was taken over; on any byte difference nothing is written.
auto InstallRuneLetters(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool;
// Letters drawn from the cell since load, letters left to D2R's lookup (r01L..r33L with a text).
void RuneLetterCounts(long* drawn, long* kept) noexcept;
