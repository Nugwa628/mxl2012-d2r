// Baal's laugh in the chat at most once every 30 s, the soldiers' "Over here!" / "Help us!" once every 5 s each (docs/bugs.md
// #508, docs/plugin-plan.md section 27, off word vochat).
//
// D2R writes "<speaker> says: <line>" into the chat whenever a voice file plays whose name is a key of vo.json. Median gives Baal's
// laugh (`baallaugh1`, "*Laughing*", "LOL" with the mod's d2r:baallaugh1 override) to many skills and missiles (Spawn Edyrem of
// the monsters dark_master1/2 and evil4spw, Spawn Dragon procs, Belial Volcano ...), so the line came on every cast. The client
// play 0x1a0780 starts the sound and then, with subtitles on, calls the subtitle 0x1a0da0(sound id, 0) (vo_chat_logic.h), whose
// return is not used. The hook on 0x1a0da0 reads the sound's path the way the subtitle does (0xd96a0, record +0x32); for the
// key baallaugh1 it returns without printing when the last line was printed less than 30 s ago (sol_overhere / sol_helpus: 5 s). Every other voice line, and
// the sound, are unchanged.
#include "vo_chat.h"

#include "vo_chat_logic.h"

#include <windows.h>

#include <atomic>
#include <cstdint>
#include <cstdio>

namespace {

using namespace vo_chat;

using SubtitleFn = void (*)(int32_t id, uint64_t flag) noexcept;
using RecordFn = const uint8_t* (*)(int32_t id, uint64_t a, uint64_t b) noexcept;

SubtitleFn g_original = nullptr;
RecordFn g_record = nullptr;
std::atomic<uint64_t> g_last[LimitedCount]{};
std::atomic<long> g_printed{0};
std::atomic<long> g_dropped{0};

void SubtitleHook(int32_t id, uint64_t flag) noexcept {
	const uint8_t* record = g_record(id, 0, 0);
	const int limited = record != nullptr ? LimitedIndex(reinterpret_cast<const char*>(record + RecordPath)) : -1;
	if (limited >= 0) {
		const uint64_t now = GetTickCount64();
		if (!LineAllowed(now, g_last[limited].load(), LimitedLines[limited].cooldownMs)) {
			++g_dropped;
			return;
		}
		g_last[limited] = now;
		++g_printed;
	}
	g_original(id, flag);
}

}  // namespace

auto InstallVoChat(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_record = reinterpret_cast<RecordFn>(context->exeBase + RvaSoundRecord);
	const bool ok = context->InstallInlineHook(RvaVoSubtitle, VoSubtitleEntry, sizeof(VoSubtitleEntry), reinterpret_cast<void*>(&SubtitleHook),
	                                           reinterpret_cast<void**>(&g_original));
	std::snprintf(report, reportSize,
	              ok ? "vochat on: the %s chat line at most once every %llu s, %s / %s every %llu s (voice subtitle 0x1a0da0)"
	                 : "vochat off: the voice subtitle hook 0x1a0da0 FAILED (%s %llu s, %s / %s %llu s)",
	              LimitedKey, static_cast<unsigned long long>(CooldownMs / 1000), SoldierOverHere, SoldierHelpUs,
	              static_cast<unsigned long long>(SoldierCooldownMs / 1000));
	return ok;
}

void VoChatCounts(long* printed, long* dropped) noexcept {
	*printed = g_printed.load();
	*dropped = g_dropped.load();
}
