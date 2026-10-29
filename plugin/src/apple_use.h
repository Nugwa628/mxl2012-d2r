// The Apple's item spell (apple_use.cpp, bug #499).
#pragma once

#include <D2RLPlugin/api.h>

#include <cstddef>

// Puts its own functions in D2R's item-spell check slot 7 and use slot 10 (misc pSpell 10): an item other than the Book of Skill
// (`ass `) can always be used and casts skill 47 (Median's Apple Healing Spell) on the user as 1.13c did. The report gets one
// entry. Returns the number of the two slots written.
auto InstallAppleUse(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int;
// Since load: uses that cast skill 47, casts D2R refused, and Books of Skill left to D2R.
void AppleUseCounts(long* casts, long* refused, long* books) noexcept;
