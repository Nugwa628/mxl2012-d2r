// Skill tooltip labels in 1.13c's words (docs/bugs.md #396, off word skilltext).
//
// D2R's line renderer 0x287a50 appends D2R's printf-format labels to 1.13c's line types 9, 10, 11, 14, 22, 25, 27 and 28
// ("Fire Damage: %d-%d12-15"); the hook lets it draw the line, then cuts each raw label in the text it appended to 1.13c's
// words (skill_text_logic.h). The labels are read in the game's language through the renderer's own string call.
#include "skill_text.h"

#include "skill_text_logic.h"

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

// PUSH RBP / PUSH RBX / PUSH RSI / PUSH RDI / PUSH R12 / PUSH R13 / PUSH R14 / LEA RBP,[RSP-0x5e0]
constexpr uint8_t RendererEntry[] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41,
                                     0x56, 0x48, 0x8d, 0xac, 0x24, 0x20, 0xfa, 0xff, 0xff};

// (data flag, unit, char out[0x800], a4, then the stack slots: skill, level, ..., line index, ...): forwarded untouched.
using RendererFn = uint64_t (*)(uint64_t a1, void* a2, char* out, void* a4, uint64_t s5, uint64_t s6, uint64_t s7, uint64_t s8,
                                uint64_t s9, uint64_t s10, uint64_t s11, uint64_t s12);
using GetStringFn = const char* (*)(uint16_t id);
RendererFn g_renderer = nullptr;
GetStringFn g_getString = nullptr;
volatile LONG g_cut = 0;

uint64_t RendererHook(uint64_t a1, void* a2, char* out, void* a4, uint64_t s5, uint64_t s6, uint64_t s7, uint64_t s8, uint64_t s9,
                      uint64_t s10, uint64_t s11, uint64_t s12) noexcept {
	const size_t before = out != nullptr ? strnlen(out, skill_text::LineBuffer) : skill_text::LineBuffer;
	const uint64_t r = g_renderer(a1, a2, out, a4, s5, s6, s7, s8, s9, s10, s11, s12);
	// the renderer appends to `out` (it measures the text already there first); anything else is left as it is
	const size_t after = before < skill_text::LineBuffer ? strnlen(out, skill_text::LineBuffer) : skill_text::LineBuffer;
	if (after >= skill_text::LineBuffer || after <= before || std::strchr(out + before, '%') == nullptr) {
		return r;
	}
	for (const auto& label : skill_text::Labels) {
		const int n = skill_text::CutLabel(out + before, g_getString(label.id), label.keepSuffix);
		if (n > 0) {
			InterlockedExchangeAdd(&g_cut, n);
		}
	}
	return r;
}

}  // namespace

auto InstallSkillText(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_getString = reinterpret_cast<GetStringFn>(context->exeBase + skill_text::GetStringRva);
	const bool ok = context->InstallInlineHook(skill_text::RendererRva, RendererEntry, sizeof(RendererEntry),
	                                           reinterpret_cast<void*>(&RendererHook), reinterpret_cast<void**>(&g_renderer));
	std::snprintf(report, reportSize, "skill tooltip labels in 1.13c's words (0x287a50 hooked)%s", ok ? "" : " FAILED");
	return ok;
}

auto SkillTextCuts() noexcept -> long {
	return g_cut;
}
