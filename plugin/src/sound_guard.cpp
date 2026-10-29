// Sound guard (docs/crash-audit.md C17; off word soundguard). D2R build 93847.
//
// The client monster update 0x1079e0 plays the monsounds Neutral sound through 0x107dd0(unit, sound id); 0x107dd0 calls
// 0xd8c70(id), which returns field +0xc7 of the sounds record and reads null+0xc7 (D2R.exe+0xd8cea) when the id is < 0 or past
// the row count. Every function of the image that turns a sound id into a sounds.txt record (the callers of the row count
// 0x3b20c0 / record 0x3b1fd0) checks the id but then goes on with a null record: 0xd8c70 (+0xc7), 0xd9180 (+0xb0), 0xd9030
// (copies the path from +0x32), 0xd9e60 and 0xda360 (pick the variant of a sound group, +0x96). Each is hooked at its entry; an
// id outside the table returns what the function returns for an empty table (0, an empty path, the id itself), and 0x107dd0
// returns null (not playing). The others need nothing: 0xd9210 / 0xd92f0 test the record, 0xd96a0 returns null, 0xdb700 /
// 0xdb8f0 / 0x1fd600 walk all rows.
//
// When it happens: on the start that builds D2RLoader 1.3.1's base compiler snapshot (<D2R>\d2rloader\data\compiler\<version>,
// missing after installing or updating D2RLoader or D2R) the sound step compiles only D2R's own sounds.txt (11913 rows), so
// every Median-only sound name (206 here: monsounds Neutral of l4dwitchsnd / malewitchsnd, taunts, skills, missiles, states)
// is -1 for that start. CheckSoundTable (after every table load, D2RLoader's DataTablesLoaded listener) tells the player to
// restart; until then those sounds are silent.
//
// Part spiritsound (InstallSpiritSound, off word spiritsound, bug #502): the client play 0x1a0780 skips ancient_death_hd for
// the Barbarian's spirit summons (monsters 1085-1087, drawn with D2R's HD Ancients). Their HD death timeline played the
// Ancients' death roar each time a spirit died or was cast again ("ancient armor noises"); legacy never played it.
//
// Dev builds: MXL_SOUNDGUARD_TEST=1 turns the Neutral sound id (caller +0x107cd4) into -1 and lets the 0x107dd0 hook skip it,
// =2 passes the -1 on to 0x107dd0, where the record reader hook on 0xd8c70 has to catch it.
// MXL_SOUND_TRACE=<file>: every id the five record readers, 0x107dd0 and the client play 0x1a0780 (part spiritsound, not
// counted when it is off) see is counted per function, and the file is rewritten at most every
// second with one line per id seen ("<id> <c7> <b0> <path> <pick> <variant> <unit sound 0x107dd0> <client play 0x1a0780>"), so a check can tell which sounds the game
// resolved while it did something (lane sound, bugs #501 / #502).
#include "sound_guard.h"

#include "build_guard.h"
#include "sound_guard_logic.h"

#include <windows.h>

#include <intrin.h>

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace sound_guard;

using PlayingSoundFn = void* (*)(void* unit, int id) noexcept;
using SoundCountFn = int (*)() noexcept;
using ReaderFn = uint64_t (*)(int id, uint64_t a, uint64_t b, uint64_t c) noexcept;

const D2RL::PluginContext* g_context = nullptr;
PlayingSoundFn g_original = nullptr;
SoundCountFn g_count = nullptr;
uint64_t g_base = 0;
int g_test = 0;
std::atomic<uint32_t> g_skipped{0};
std::atomic<int> g_lastId{0};
std::atomic<uint64_t> g_lastCaller{0};
std::atomic<uint64_t> g_lastSite{0};
ReaderFn g_fieldC7 = nullptr;
ReaderFn g_fieldB0 = nullptr;
ReaderFn g_path = nullptr;
ReaderFn g_pick = nullptr;
ReaderFn g_variant = nullptr;
using ClientPlayFn = uint64_t (*)(int32_t id, const void* unit, uint64_t a, uint64_t b, uint64_t c) noexcept;
ClientPlayFn g_clientPlay = nullptr;
std::atomic<uint32_t> g_spiritSkips{0};

#ifndef MXL_RELEASE
// The dev trace (MXL_SOUND_TRACE): counts per id and reader, written by whichever thread passes the one-second mark.
constexpr int TraceIds = 16384;
constexpr int TraceReaders = 7;  // the five readers, the unit sound 0x107dd0, the client play 0x1a0780
char g_tracePath[MAX_PATH] = "";
std::atomic<uint32_t> g_trace[TraceIds][TraceReaders];
std::atomic<uint64_t> g_traceDue{0};
std::atomic<bool> g_traceWriting{false};

auto ReaderSlot(uint64_t site) noexcept -> int {
	return site == RvaFieldC7 ? 0 : site == RvaFieldB0 ? 1 : site == RvaPath ? 2 : site == RvaPick ? 3 : site == RvaVariant ? 4 : site == RvaPlayingSound ? 5 : 6;
}

void Trace(int id, uint64_t site) noexcept {
	if (g_tracePath[0] == '\0' || id < 0 || id >= TraceIds) {
		return;
	}
	++g_trace[id][ReaderSlot(site)];
	const uint64_t now = GetTickCount64();
	if (now < g_traceDue.load() || g_traceWriting.exchange(true)) {
		return;
	}
	g_traceDue = now + 1000;
	FILE* f = nullptr;
	if (fopen_s(&f, g_tracePath, "w") == 0 && f != nullptr) {
		for (int i = 0; i < TraceIds; ++i) {
			uint32_t n[TraceReaders];
			uint32_t any = 0;
			for (int r = 0; r < TraceReaders; ++r) {
				any |= n[r] = g_trace[i][r].load();
			}
			if (any != 0) {
				std::fprintf(f, "%d %u %u %u %u %u %u %u\n", i, n[0], n[1], n[2], n[3], n[4], n[5], n[6]);
			}
		}
		std::fclose(f);
	}
	g_traceWriting = false;
}
#else
void Trace(int, uint64_t) noexcept {}
#endif

// True (counted, the first five logged) when `id` is not a row of the loaded sounds table.
auto Skip(int id, uint64_t site, uint64_t caller) noexcept -> bool {
	Trace(id, site);
	const int rows = g_count();
	if (!Skips(id, rows)) {
		return false;
	}
	const uint32_t n = ++g_skipped;
	g_lastId = id;
	g_lastSite = site;
	g_lastCaller = caller;
	if (n <= 5 && g_context != nullptr) {
		char line[192];
		std::snprintf(line, sizeof(line), "mxl2012-core: sound id %d is not in sounds.txt (%d rows), skipped in 0x%llx (caller +0x%llx)", id,
		              rows, static_cast<unsigned long long>(site), static_cast<unsigned long long>(caller));
		g_context->LogWarn(line);
	}
	return true;
}

auto Caller(void* ret) noexcept -> uint64_t {
	return reinterpret_cast<uint64_t>(ret) - g_base;
}

uint64_t FieldC7Hook(int id, uint64_t a, uint64_t b, uint64_t c) noexcept {
	return Skip(id, RvaFieldC7, Caller(_ReturnAddress())) ? FieldAnswer() : g_fieldC7(id, a, b, c);
}

uint64_t FieldB0Hook(int id, uint64_t a, uint64_t b, uint64_t c) noexcept {
	return Skip(id, RvaFieldB0, Caller(_ReturnAddress())) ? FieldAnswer() : g_fieldB0(id, a, b, c);
}

uint64_t PathHook(int id, uint64_t buffer, uint64_t size, uint64_t c) noexcept {
	if (!Skip(id, RvaPath, Caller(_ReturnAddress()))) {
		return g_path(id, buffer, size, c);
	}
	if (buffer != 0 && size != 0) {
		*reinterpret_cast<char*>(buffer) = '\0';
	}
	return 0;
}

uint64_t PickHook(int id, uint64_t a, uint64_t b, uint64_t c) noexcept {
	return Skip(id, RvaPick, Caller(_ReturnAddress())) ? PickAnswer(id) : g_pick(id, a, b, c);
}

uint64_t VariantHook(int id, uint64_t a, uint64_t b, uint64_t c) noexcept {
	return Skip(id, RvaVariant, Caller(_ReturnAddress())) ? PickAnswer(id) : g_variant(id, a, b, c);
}

// The client play 0x1a0780: the Ancients' HD death sound of a spirit summon returns 0 (nothing played), bug #502.
uint64_t ClientPlayHook(int32_t id, const void* unit, uint64_t a, uint64_t b, uint64_t c) noexcept {
	Trace(id, RvaClientPlay);
	if (id == AncientDeathHd && unit != nullptr &&
	    SkipsSpiritDeath(id, *static_cast<const int32_t*>(unit), *reinterpret_cast<const int32_t*>(static_cast<const uint8_t*>(unit) + 4))) {
		++g_spiritSkips;
		return 0;
	}
	return g_clientPlay(id, unit, a, b, c);
}

void* PlayingSoundHook(void* unit, int id) noexcept {
	const uint64_t caller = Caller(_ReturnAddress());
	if (g_test != 0 && caller == RvaNeutralCallRet) {
		id = -1;
		if (g_test == 2) {
			return g_original(unit, id);
		}
	}
	return Skip(id, RvaPlayingSound, caller) ? nullptr : g_original(unit, id);
}

// The sounds table the game loaded: below ours a warning goes to the log and `notice` gets the screen line for the player (empty
// when the table is ours or not loaded yet). Returns the row count.
auto CheckSoundTable(const D2RL::PluginContext* context, char* notice, size_t noticeSize) noexcept -> int {
	notice[0] = '\0';
	if (g_count == nullptr) {
		g_count = reinterpret_cast<SoundCountFn>(context->exeBase + RvaSoundCount);
	}
	const int rows = g_count();
	char line[512];
	switch (CheckTable(rows)) {
	case Table::NotLoaded:
		return 0;
	case Table::Ours:
		std::snprintf(line, sizeof(line), "mxl2012-core: sounds table %d rows (D2R-XL 2012 %d), ok", rows, ModSoundRows);
		context->LogInfo(line);
		return rows;
	case Table::Short:
		break;
	}
	std::snprintf(line, sizeof(line),
	              "mxl2012-core: the game loaded a sounds table of %d rows, not D2R-XL 2012's %d: every Median sound is silent (the sound "
	              "guard skips them). D2RLoader does this on the start that builds its table cache (first start after installing or "
	              "updating D2RLoader or D2R). Close the game and start it again (docs/crash-audit.md C17).",
	              rows, ModSoundRows);
	context->LogWarn(line);
	std::snprintf(notice, noticeSize,
	              "D2R-XL 2012: D2RLoader built its table cache on this start and the mod's sounds did not load. Close the game and start it again.");
	return rows;
}

// Game thread, after each completed table load (also reloads).
void __cdecl OnDataTablesLoaded(const D2RL::PluginContext* context, const D2RL::Lifecycle::DataTablesLoadedEvent*, void*) noexcept {
	char notice[256];
	if (CheckSoundTable(context, notice, sizeof(notice)) > 0 && notice[0] != '\0' && !NoticeShown() && !ShowNotice(context, notice)) {
		context->LogWarn("mxl2012-core: no overlay service, the sounds table warning is in this log only");
	}
}

}  // namespace

auto InstallSoundGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	g_context = context;
	g_base = context->exeBase;
	g_count = reinterpret_cast<SoundCountFn>(g_base + RvaSoundCount);
#ifndef MXL_RELEASE
	char env[8] = "";
	if (GetEnvironmentVariableA("MXL_SOUNDGUARD_TEST", env, sizeof(env)) > 0) {
		g_test = env[0] == '2' ? 2 : (env[0] == '1' ? 1 : 0);
	}
	if (GetEnvironmentVariableA("MXL_SOUND_TRACE", g_tracePath, sizeof(g_tracePath)) >= sizeof(g_tracePath)) {
		g_tracePath[0] = '\0';
	}
#endif
	const bool ok = context->InstallInlineHook(RvaPlayingSound, PlayingSoundEntry, sizeof(PlayingSoundEntry),
	                                           reinterpret_cast<void*>(&PlayingSoundHook), reinterpret_cast<void**>(&g_original));
	struct Reader {
		uint64_t rva;
		const uint8_t* entry;
		uint32_t size;
		void* hook;
		ReaderFn* original;
	};
	const Reader readers[] = {
	    {RvaFieldC7, FieldC7Entry, sizeof(FieldC7Entry), reinterpret_cast<void*>(&FieldC7Hook), &g_fieldC7},
	    {RvaFieldB0, FieldB0Entry, sizeof(FieldB0Entry), reinterpret_cast<void*>(&FieldB0Hook), &g_fieldB0},
	    {RvaPath, PathEntry, sizeof(PathEntry), reinterpret_cast<void*>(&PathHook), &g_path},
	    {RvaPick, PickEntry, sizeof(PickEntry), reinterpret_cast<void*>(&PickHook), &g_pick},
	    {RvaVariant, VariantEntry, sizeof(VariantEntry), reinterpret_cast<void*>(&VariantHook), &g_variant},
	};
	constexpr int ReaderCount = static_cast<int>(sizeof(readers) / sizeof(readers[0]));
	int in = 0;
	char failed[96] = "";
	for (const Reader& r : readers) {
		if (context->InstallInlineHook(r.rva, r.entry, r.size, r.hook, reinterpret_cast<void**>(r.original))) {
			++in;
		} else {
			const size_t len = std::strlen(failed);
			std::snprintf(failed + len, sizeof(failed) - len, " 0x%llx", static_cast<unsigned long long>(r.rva));
		}
	}
	// The sounds table check after each table load (D2RLoader's lifecycle listener).
	const D2RL::LifecycleService* lifecycle = nullptr;
	bool listening = false;
	if (context->QueryService(&lifecycle) == D2RL::ServiceQueryResult::Success && lifecycle != nullptr &&
	    D2RL::HasLifecycleServiceField(lifecycle, D2RL::LifecycleServiceRequiredSize)) {
		const D2RL::Lifecycle::DataTablesLoadedListener listener{D2RL::Lifecycle::DataTablesLoadedListenerSize, 0, OnDataTablesLoaded, nullptr};
		D2RL::Lifecycle::ListenerHandle handle = D2RL::Lifecycle::InvalidHandle;
		listening = lifecycle->registerDataTablesLoadedListener(context, &listener, &handle) == D2RL::Lifecycle::Result::Success &&
		            handle != D2RL::Lifecycle::InvalidHandle;
	}
	const bool all = ok && in == ReaderCount;
	std::snprintf(report, reportSize, "sound ids outside sounds.txt skipped: unit sound 0x107dd0%s, record readers %d of %d%s%s; sounds table checked after each table load%s%s%s",
	              ok ? "" : " FAILED", in, ReaderCount, failed[0] != '\0' ? " (FAILED:" : "", failed[0] != '\0' ? failed : "",
	              failed[0] != '\0' ? ")" : "", listening ? "" : " (NO LISTENER)",
	              g_test == 0 ? "" : (g_test == 2 ? " (TEST 2: Neutral id -1 passed on)" : " (TEST 1: Neutral id -1)"));
#ifndef MXL_RELEASE
	if (g_tracePath[0] != '\0') {
		const size_t len = std::strlen(report);
		std::snprintf(report + len, reportSize - len, " (TRACE to %s)", g_tracePath);
	}
#endif
	return all;
}

auto InstallSpiritSound(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	const bool ok = context->InstallInlineHook(RvaClientPlay, ClientPlayEntry, sizeof(ClientPlayEntry), reinterpret_cast<void*>(&ClientPlayHook),
	                                           reinterpret_cast<void**>(&g_clientPlay));
	std::snprintf(report, reportSize,
	              ok ? "spiritsound on: ancient_death_hd (%d) of the spirit summons %d-%d not played (client play 0x1a0780)"
	                 : "spiritsound off: the client play hook 0x1a0780 FAILED (ancient_death_hd %d, spirits %d-%d)",
	              AncientDeathHd, SpiritFirst, SpiritLast);
	return ok;
}

auto SpiritSoundSkips() noexcept -> long {
	return static_cast<long>(g_spiritSkips.load());
}

void SoundGuardStatus(char* out, size_t outSize) noexcept {
	const int rows = g_count != nullptr ? g_count() : 0;
	std::snprintf(out, outSize, "sounds.txt %d rows (D2R-XL 2012 %d)%s, %u bad sound ids skipped (last id %d in 0x%llx from +0x%llx)", rows,
	              ModSoundRows, CheckTable(rows) == Table::Short ? " NOT D2R-XL 2012's table" : "", g_skipped.load(), g_lastId.load(),
	              static_cast<unsigned long long>(g_lastSite.load()), static_cast<unsigned long long>(g_lastCaller.load()));
}
