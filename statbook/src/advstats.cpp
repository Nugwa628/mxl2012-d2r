// The character sheet's Advanced Stats panel in groups (bugs #581 / #582, off word advstats, docs/plugin-plan.md section 37).
//
// D2R's panel lists the itemstatcost rows marked by `advdisplay` in table order, without headings, and only rebuilds its list
// when one of its "nonzero" rows turns on or off (advstats_logic.h). The part replaces the list builder (0x14eaf40): the rows
// of data/advanced_stats.tsv (advstats_table.h) per group with a gold heading, Avoid (passive_dodge / avoid / evade, whose own
// descstr is a placeholder) as one line or one line each, the elemental adds as "Adds x-y", and the skill speeds that have no
// descfunc. Every row sits in the panel's "always" vector, so D2R's Update re-texts all of them each frame; the Update slot
// wrapper rebuilds the list when a buff, state or item turns a row on or off. Plain rows keep D2R's own text (0x14eb250, the
// item tooltip line); the hook on 0x14eb250 texts only the part's own rows. Without the part the panel shows the advdisplay
// rows as before (txt_migrate.advanced_stats).
#include "advstats.h"

#include "advstats_logic.h"
#include "advstats_table.h"

#include <D2RLPlugin/localization.h>

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using namespace advstats;

using PanelFn = void (*)(uint8_t* panel);
using TextFn = uint64_t* (*)(uint8_t* panel, uint64_t* out, const uint8_t* record);
using PushFn = void* (*)(void* vector, const void* record);
using RowAddFn = void (*)(uint8_t* panel, const void* record);
using ClearFn = void (*)(void* container);
using ResizeFn = void* (*)(uint64_t* text, size_t length);
using GetStatFn = int32_t (*)(void* unit, int32_t stat, int32_t layer);
using TablesFn = const uint8_t* (*)(uint32_t dataFlag);
using FlagHolderFn = const uint8_t* (*)();

constexpr size_t RowCount = sizeof(Rows) / sizeof(Rows[0]);
constexpr size_t GroupCount = sizeof(Groups) / sizeof(Groups[0]);

const D2RL::PluginContext* g_context = nullptr;
const D2RL::LocalizationService* g_strings = nullptr;
PanelFn g_build = nullptr;
PanelFn g_update = nullptr;
TextFn g_text = nullptr;
PushFn g_push = nullptr;
RowAddFn g_rowAdd = nullptr;
ClearFn g_clear = nullptr;
ResizeFn g_resize = nullptr;
GetStatFn g_getStat = nullptr;
TablesFn g_tables = nullptr;
FlagHolderFn g_flagHolder = nullptr;
TextFn g_lineFn = nullptr;  // 0x14eb250 for StatLine

// the list the panel shows (main thread only: the builder, Update and the row text all run on it)
uint8_t* g_panel = nullptr;
Item g_plan[MaxItems];
size_t g_planCount = 0;

volatile LONG g_builds = 0;
volatile LONG g_rebuilds = 0;
volatile LONG g_texts = 0;
volatile LONG g_lastRows = 0;
volatile LONG g_stringsFrom = 0;

struct Cached {
	const char* key;
	char text[160];
};
Cached g_cache[48];
size_t g_cacheCount = 0;

auto Lookup(const char* key, char* out, size_t size) noexcept -> bool {
	if (g_strings == nullptr) {
		return false;
	}
	char full[96];
	std::snprintf(full, sizeof(full), "mxl2012:%s", key);
	uint32_t need = 0;
	out[0] = '\0';
	if (g_strings->getStringByKey(g_context, full, out, static_cast<uint32_t>(size), &need) == D2RL::Localization::Result::Success && out[0] != '\0') {
		return true;
	}
	out[0] = '\0';
	return g_strings->getStringByKey(g_context, key, out, static_cast<uint32_t>(size), &need) == D2RL::Localization::Result::Success && out[0] != '\0';
}

// The localized text of one of the part's keys, else its English text. Cached until the next build (the panel is rebuilt
// each time it opens, so a language change shows on the next open).
auto Text(const char* key, const char* english) noexcept -> const char* {
	for (size_t i = 0; i < g_cacheCount; ++i) {
		if (g_cache[i].key == key) {
			return g_cache[i].text;
		}
	}
	if (g_cacheCount == sizeof(g_cache) / sizeof(g_cache[0])) {
		return english;
	}
	Cached& c = g_cache[g_cacheCount++];
	c.key = key;
	if (Lookup(key, c.text, sizeof(c.text))) {
		g_stringsFrom = 1;
	} else {
		std::snprintf(c.text, sizeof(c.text), "%s", english);
		if (g_stringsFrom == 0) {
			g_stringsFrom = 2;
		}
	}
	return c.text;
}

auto Tables() noexcept -> const uint8_t* {
	const uint8_t* holder = g_flagHolder();
	return holder == nullptr ? nullptr : g_tables(holder[DataFlagOffset]);
}

auto Record(const uint8_t* tables, uint32_t stat) noexcept -> const uint8_t* {
	const auto count = *reinterpret_cast<const uint64_t*>(tables + StatsCount);
	const auto* data = *reinterpret_cast<const uint8_t* const*>(tables + StatsData);
	return data == nullptr || stat >= count ? nullptr : data + static_cast<size_t>(stat) * RecordSize;
}

}  // namespace

// The Stat Book's stat reader: GetStat, the stats table and its holder, checked by their entry bytes, without the panel hooks.
auto InitStatReader(const D2RL::PluginContext* context) noexcept -> bool {
	const uint64_t base = context->exeBase;
	const auto* b = reinterpret_cast<const uint8_t*>(base);
	if (std::memcmp(b + GetStatRva, GetStatEntry, sizeof(GetStatEntry)) != 0 || std::memcmp(b + TablesRva, TablesEntry, sizeof(TablesEntry)) != 0 ||
	    std::memcmp(b + FlagHolderRva, FlagHolderEntry, sizeof(FlagHolderEntry)) != 0) {
		return false;
	}
	g_getStat = reinterpret_cast<GetStatFn>(base + GetStatRva);
	g_tables = reinterpret_cast<TablesFn>(base + TablesRva);
	g_flagHolder = reinterpret_cast<FlagHolderFn>(base + FlagHolderRva);
	// the row text: D2R's bytes, or already the part's own hook (InstallAdvancedStats runs first), which passes other panels through
	g_lineFn = std::memcmp(b + TextRva, TextEntry, sizeof(TextEntry)) == 0 || g_text != nullptr ? reinterpret_cast<TextFn>(base + TextRva) : nullptr;
	if (g_context == nullptr) {
		g_context = context;
	}
	if (g_strings == nullptr && (context->QueryService(&g_strings) != D2RL::ServiceQueryResult::Success ||
	                             !D2RL::HasLocalizationServiceField(g_strings, D2RL::LocalizationServiceRequiredSize))) {
		g_strings = nullptr;
	}
	return true;
}

namespace {

// A stand-in for the Advanced Stats panel: 0x14eb250 reads the unit at +0x168 (PanelUnit); the rest stays zero.
alignas(16) uint8_t g_standIn[0x2000];

auto StatLineInner(void* unit, uint16_t stat, char* out, size_t size) -> bool {
	const uint8_t* tables = Tables();
	const uint8_t* rec = tables == nullptr ? nullptr : Record(tables, stat);
	if (rec == nullptr) {
		return false;
	}
	alignas(8) uint8_t copy[RecordSize];
	std::memcpy(copy, rec, RecordSize);
	*reinterpret_cast<void**>(g_standIn + PanelUnit) = unit;
	uint64_t text[8] = {};
	text[0] = reinterpret_cast<uint64_t>(&text[3]);
	text[2] = 0x800000000000000FULL;
	const uint64_t* got = g_lineFn(g_standIn, text, copy);
	if (got == nullptr) {
		return false;
	}
	const auto* data = reinterpret_cast<const char*>(got[0]);
	const auto n = static_cast<size_t>(got[1]);
	if (data == nullptr || n == 0 || n > 4096) {
		return false;
	}
	const size_t k = n < size - 1 ? n : size - 1;
	std::memcpy(out, data, k);
	out[k] = '\0';
	return true;
}

}  // namespace

auto StatLine(void* unit, uint16_t stat, char* out, size_t size) noexcept -> bool {
	if (g_lineFn == nullptr || unit == nullptr || out == nullptr || size < 2) {
		return false;
	}
	__try {
		return StatLineInner(unit, stat, out, size);
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

auto LookupString(const char* key, char* out, size_t size) noexcept -> bool {
	return key != nullptr && key[0] != '\0' && std::strcmp(key, "-") != 0 && Lookup(key, out, size);
}

// The stat as the sheet shows it: GetStat(unit, stat, layer) >> the stat's ValShift; 0 for a stat the table lacks.
auto ShiftedStat(void* unit, uint32_t stat, int32_t layer) noexcept -> int32_t {
	if (unit == nullptr || g_getStat == nullptr) {
		return 0;
	}
	const uint8_t* tables = Tables();
	const uint8_t* rec = tables == nullptr ? nullptr : Record(tables, stat);
	if (rec == nullptr) {
		return 0;
	}
	return g_getStat(unit, static_cast<int32_t>(stat), layer) >> (rec[RecordValShift] & 0x1f);
}

namespace {

// the stat as D2R's panel reads it (0x14eb1b0): layer 0, >> ValShift
auto Value(void* unit, const uint8_t* tables, uint32_t stat) noexcept -> int32_t {
	const uint8_t* rec = Record(tables, stat);
	if (unit == nullptr || rec == nullptr) {
		return 0;
	}
	return g_getStat(unit, static_cast<int32_t>(stat), 0) >> (rec[RecordValShift] & 0x1f);
}

// every stat of the table is the record of its id in this bank
auto IdsOk(const uint8_t* tables) noexcept -> bool {
	for (const Row& r : Rows) {
		const int n = r.kind == Kind::Avoid ? 3 : r.kind == Kind::Range ? 2 : 1;
		for (int k = 0; k < n; ++k) {
			const uint8_t* rec = Record(tables, r.stat[k]);
			if (rec == nullptr || *reinterpret_cast<const uint16_t*>(rec) != r.stat[k]) {
				return false;
			}
		}
	}
	return true;
}

auto MakePlan(void* unit, const uint8_t* tables, Item* out) noexcept -> size_t {
	return BuildPlan(GroupCount, Rows, RowCount, [&](uint16_t stat) { return Value(unit, tables, stat); }, out, MaxItems);
}

void BuildHook(uint8_t* panel) noexcept {
	const uint8_t* tables = Tables();
	if (panel == nullptr || tables == nullptr || !IdsOk(tables)) {
		g_panel = nullptr;
		g_build(panel);
		return;
	}
	InterlockedIncrement(&g_builds);
	void* unit = *reinterpret_cast<void**>(panel + PanelUnit);
	*reinterpret_cast<uint64_t*>(panel + PanelAlways + 8) = 0;
	*reinterpret_cast<uint64_t*>(panel + PanelNonzero + 8) = 0;
	*reinterpret_cast<uint64_t*>(panel + PanelShownCount) = 0;
	g_cacheCount = 0;
	g_planCount = MakePlan(unit, tables, g_plan);
	g_panel = panel;
	g_lastRows = static_cast<LONG>(g_planCount);
	alignas(8) uint8_t rec[RecordSize];
	for (size_t i = 0; i < g_planCount; ++i) {
		const Item& item = g_plan[i];
		// a heading's record is any valid one (D2R's debug row path reads its stat id); a row's is its own stat's
		const uint16_t stat = item.heading != 0 ? 0 : Rows[item.index].stat[item.part == 0 ? 0 : item.part - 1];
		const uint8_t* source = Record(tables, stat);
		std::memcpy(rec, source, RecordSize);
		g_push(panel + PanelAlways, rec);
		const auto* data = *reinterpret_cast<uint8_t* const*>(panel + PanelAlways);
		const auto count = *reinterpret_cast<const uint64_t*>(panel + PanelAlways + 8);
		g_rowAdd(panel, data + (count - 1) * RecordSize);
	}
}

// D2R's string (0x14eb250's out: {data, length, capacity | flag}, 15 chars inline at +0x18) set to `text`
void SetText(uint64_t* out, const char* text) noexcept {
	out[2] = 0x800000000000000FULL;
	out[0] = reinterpret_cast<uint64_t>(&out[3]);
	out[1] = 0;
	*reinterpret_cast<char*>(&out[3]) = '\0';
	const size_t n = std::strlen(text);
	g_resize(out, n);
	auto* p = reinterpret_cast<char*>(out[0]);
	std::memcpy(p, text, n);
	p[n] = '\0';
	out[1] = n;
}

uint64_t* TextHook(uint8_t* panel, uint64_t* out, const uint8_t* record) noexcept {
	if (panel != nullptr && panel == g_panel && record != nullptr) {
		const auto* data = *reinterpret_cast<uint8_t* const*>(panel + PanelAlways);
		const auto count = *reinterpret_cast<const uint64_t*>(panel + PanelAlways + 8);
		if (data != nullptr && record >= data && record < data + count * RecordSize && (record - data) % RecordSize == 0) {
			const auto i = static_cast<size_t>((record - data) / RecordSize);
			if (i < g_planCount) {
				const Item& item = g_plan[i];
				char text[256];
				bool own = false;
				if (item.heading != 0) {
					HeadingText(Text(Groups[item.index].key, Groups[item.index].english), text, sizeof(text));
					own = true;
				} else if (const uint8_t* tables = Tables(); tables != nullptr) {
					void* unit = *reinterpret_cast<void**>(panel + PanelUnit);
					own = RowText(
					    Rows[item.index], item.part, [&](uint16_t stat) { return Value(unit, tables, stat); },
					    [](const char* key, const char* english) { return Text(key, english); }, text, sizeof(text));
				}
				if (own) {
					InterlockedIncrement(&g_texts);
					SetText(out, text);
					return out;
				}
			}
		}
	}
	return g_text(panel, out, record);
}

// Update wrapper: rebuild when the rows to show changed (#582), then D2R's Update, which re-texts every row.
void UpdateHook(uint8_t* panel) noexcept {
	if (panel != nullptr && panel == g_panel) {
		void* unit = *reinterpret_cast<void**>(panel + PanelUnit);
		const uint8_t* tables = unit != nullptr ? Tables() : nullptr;
		if (tables != nullptr) {
			Item now[MaxItems];
			const size_t n = MakePlan(unit, tables, now);
			if (!SamePlan(now, n, g_plan, g_planCount)) {
				InterlockedIncrement(&g_rebuilds);
				g_clear(*reinterpret_cast<void**>(panel + PanelContainer));
				BuildHook(panel);
			}
		}
	}
	g_update(panel);
}

}  // namespace

auto InstallAdvancedStats(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> bool {
	const uint64_t base = context->exeBase;
	const auto* b = reinterpret_cast<const uint8_t*>(base);
	const uint64_t update = *reinterpret_cast<const uint64_t*>(base + UpdateSlotRva);
	const struct {
		uint64_t rva;
		const uint8_t* bytes;
		size_t size;
	} checks[] = {{UpdateRva, UpdateEntry, sizeof(UpdateEntry)}, {BuildRva, BuildEntry, sizeof(BuildEntry)},
	              {TextRva, TextEntry, sizeof(TextEntry)},       {PushRva, PushEntry, sizeof(PushEntry)},
	              {RowAddRva, RowAddEntry, sizeof(RowAddEntry)}, {ClearRva, ClearEntry, sizeof(ClearEntry)},
	              {ResizeRva, ResizeEntry, sizeof(ResizeEntry)}, {GetStatRva, GetStatEntry, sizeof(GetStatEntry)},
	              {TablesRva, TablesEntry, sizeof(TablesEntry)}, {FlagHolderRva, FlagHolderEntry, sizeof(FlagHolderEntry)}};
	for (const auto& c : checks) {
		if (std::memcmp(b + c.rva, c.bytes, c.size) != 0) {
			std::snprintf(report, reportSize, "advstats off: bytes differ at 0x%llx, panel left as D2R", static_cast<unsigned long long>(c.rva));
			return false;
		}
	}
	if (update != base + UpdateRva) {
		std::snprintf(report, reportSize, "advstats off: the Update slot 0x1fdd6a0 is not D2R's 0x14ed3a0, panel left as D2R");
		return false;
	}
	g_context = context;
	g_update = reinterpret_cast<PanelFn>(update);
	g_push = reinterpret_cast<PushFn>(base + PushRva);
	g_rowAdd = reinterpret_cast<RowAddFn>(base + RowAddRva);
	g_clear = reinterpret_cast<ClearFn>(base + ClearRva);
	g_resize = reinterpret_cast<ResizeFn>(base + ResizeRva);
	g_getStat = reinterpret_cast<GetStatFn>(base + GetStatRva);
	g_tables = reinterpret_cast<TablesFn>(base + TablesRva);
	g_flagHolder = reinterpret_cast<FlagHolderFn>(base + FlagHolderRva);
	if (context->QueryService(&g_strings) != D2RL::ServiceQueryResult::Success ||
	    !D2RL::HasLocalizationServiceField(g_strings, D2RL::LocalizationServiceRequiredSize)) {
		g_strings = nullptr;  // English texts
	}
	// the text hook and the Update wrapper pass everything through until the builder hook has built a list
	if (!context->InstallInlineHook(TextRva, TextEntry, sizeof(TextEntry), reinterpret_cast<void*>(&TextHook), reinterpret_cast<void**>(&g_text))) {
		std::snprintf(report, reportSize, "advstats off: the row text hook 0x14eb250 FAILED");
		return false;
	}
	if (!context->PatchWriteU64(UpdateSlotRva, &update, sizeof(update), reinterpret_cast<uint64_t>(&UpdateHook))) {
		std::snprintf(report, reportSize, "advstats off: the Update slot 0x1fdd6a0 write was refused");
		return false;
	}
	if (!context->InstallInlineHook(BuildRva, BuildEntry, sizeof(BuildEntry), reinterpret_cast<void*>(&BuildHook), reinterpret_cast<void**>(&g_build))) {
		std::snprintf(report, reportSize, "advstats off: the list builder hook 0x14eaf40 FAILED");
		return false;
	}
	std::snprintf(report, reportSize, "advstats on: Advanced Stats in %zu groups, %zu rows (builder 0x14eaf40, row text 0x14eb250, Update slot 0x1fdd6a0)",
	              GroupCount, RowCount);
	return true;
}

void AdvancedStatsCounts(long* builds, long* rebuilds, long* texts, long* lastRows, int* strings) noexcept {
	*builds = g_builds;
	*rebuilds = g_rebuilds;
	*texts = g_texts;
	*lastRows = g_lastRows;
	*strings = static_cast<int>(g_stringsFrom);
}
