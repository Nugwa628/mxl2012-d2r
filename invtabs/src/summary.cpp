// The charm-tab summary's game side (summary.h says what the core calls and when; docs/invtabs-summary.md the design).
//
// Read: each item's own stat list (flags 0x40), as the item tooltip reads it (0x2dc4b0). Count: an item counts while its
// stats are merged into its owner (0x2f8120): requirements met and, for carry1 uniques, the active copy (docs/d2r-addresses.md
// 22c). Sum: summary_logic.h Sum, raw values per (stat, param). Format: the totals go into a new stat list that is handed to
// the tooltip's own stat block writer (0x2da760: descpriority order, grouped lines such as all resistances and min-max
// damage, per-level wording), with the first counting charm as the context item, exactly as the tooltip calls it; the
// block is split into lines. Without that writer the one-stat formatter of the Advanced Stats panel (0x2d97e0) words each
// total on its own, in the tooltip's order (no grouped lines).
#include "summary.h"

#include "summary_natives.h"

#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include <cstdarg>
#include <cstdio>
#include <cstring>

namespace invtabs::summary {
namespace {

// The second-to-last argument of the stat block writer: the tooltip passes its Chronicle span; {0, 0} = none.
struct ChronicleSpan {
	std::uint64_t value;
	std::uint8_t  has;
};

struct StringView {
	const char* data;
	std::size_t size;
};

using GetStatListFn   = void* (*)(void* unit, int state, std::uint32_t flags);
using AllocStatListFn = void* (*)(std::uint32_t flags, int timeout, int ownerType, std::uint32_t ownerId);
using DataFlagFn      = std::uint8_t (*)(void* unit);
using StatListAddFn   = void (*)(std::uint8_t dataFlag, void* list, int stat, int value, int layer);
using StatListTextFn  = void (*)(std::uint8_t dataFlag, char* out, int outSize, void* context, void* list, int newline, int* hasLine,
                                void* chronicle, ChronicleSpan* span, std::uint8_t bullet);
using FreeStatListFn  = void (*)(std::uint8_t dataFlag, void* list);
using MergedFn        = void* (*)(void* item, std::uint32_t* active);
using FormatOneFn     = bool (*)(const void* record, int value, char* out, int layer);
using StatRecordFn    = const std::uint8_t* (*)(std::uint8_t dataFlag, int stat);
using FindPanelFn     = void* (*)(void* root, const char* name128);
using FindChildFn     = void* (*)(void* widget, const char* name);
using SetTextFn       = void (*)(void* widget, const StringView* text);

// Stat list (D2R x64): entries at +0x30, count in the low 16 bits of +0x38; entry {u16 layer, u16, u32 stat, i32 value, i32}.
constexpr std::size_t ListEntries = 0x30, ListCount = 0x38, EntrySize = 16;
// itemstatcost row (stride 0x144): descpriority i16 at +0x30, descfunc u8 at +0x32.
constexpr std::size_t RecDescPriority = 0x30, RecDescFunc = 0x32;
// Unit: id at +0x08 (type at +0x00, class at +0x04).
constexpr std::size_t UnitIdOffset = 0x08;
constexpr int         UnitTypeItem = 4;
constexpr std::uint32_t ItemOwnList = 0x40;
constexpr int         TextBufferSize = 32 * 1024;
constexpr int         OneBufferSize  = 2048;

template <class T> T At(const void* base, std::size_t off) {
	T v;
	std::memcpy(&v, static_cast<const std::uint8_t*>(base) + off, sizeof(T));
	return v;
}

// The calls into the game, each behind SEH: a bad unit pointer must not take the game down with the summary.
bool SafeReadList(GetStatListFn getList, void* item, StatValue* out, std::size_t cap, std::size_t* n) {
	__try {
		*n = 0;
		void* list = getList(item, 0, ItemOwnList);
		if (list == nullptr) return true;
		const auto* entries = At<const std::uint8_t*>(list, ListEntries);
		const std::size_t count = At<std::uint64_t>(list, ListCount) & 0xffff;
		for (std::size_t k = 0; entries != nullptr && k < count && *n < cap; ++k) {
			const std::uint8_t* e = entries + k * EntrySize;
			out[(*n)++] = { static_cast<std::uint16_t>(At<std::uint32_t>(e, 4)), At<std::uint16_t>(e, 0), At<std::int32_t>(e, 8) };
		}
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		*n = 0;
		return false;
	}
}

bool SafeMerged(MergedFn merged, void* item, bool* counts) {
	__try {
		*counts = merged(item, nullptr) != nullptr;
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		*counts = false;
		return false;
	}
}

struct TextCall {
	AllocStatListFn alloc;
	DataFlagFn      dataFlag;
	StatListAddFn   add;
	StatListTextFn  text;
	FreeStatListFn  free;
};

bool SafeStatListText(const TextCall& f, void* context, const StatValue* totals, std::size_t n, char* out, int outSize) {
	__try {
		out[0] = '\0';
		const std::uint8_t df   = f.dataFlag(context);
		void*              list = f.alloc(0, 0, UnitTypeItem, At<std::uint32_t>(context, UnitIdOffset));
		if (list == nullptr) return false;
		for (std::size_t i = 0; i < n; ++i) f.add(df, list, totals[i].stat, totals[i].value, totals[i].param);
		int           hasLine = 0;
		ChronicleSpan span { 0, 0 };
		f.text(df, out, outSize, context, list, 1, &hasLine, nullptr, &span, 0);
		out[outSize - 1] = '\0';
		f.free(df, list);
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		out[0] = '\0';
		return false;
	}
}

bool SafeRecord(StatRecordFn record, std::uint8_t df, int stat, const std::uint8_t** rec) {
	__try {
		*rec = record(df, stat);
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		*rec = nullptr;
		return false;
	}
}

bool SafeFormatOne(FormatOneFn one, const void* rec, int value, int layer, char* out, int outSize) {
	__try {
		out[0] = '\0';
		const bool ok = one(rec, value, out, layer);
		out[outSize - 1] = '\0';
		return ok;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		out[0] = '\0';
		return false;
	}
}

bool SafeDataFlag(DataFlagFn dataFlag, void* unit, std::uint8_t* df) {
	__try {
		*df = dataFlag(unit);
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

bool SafeSetRow(FindPanelFn findPanel, FindChildFn findChild, SetTextFn setText, void* root, const char* panelName128, const char* row,
                const char* text, std::size_t size, bool* found) {
	__try {
		*found         = false;
		void* panel    = findPanel(root, panelName128);
		void* widget   = panel != nullptr ? findChild(panel, row) : nullptr;
		if (widget == nullptr) return true;
		const StringView view { text, size };
		setText(widget, &view);
		*found = true;
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

void Logf(LogFn log, const char* fmt, ...) {
	if (log == nullptr) return;
	char    line[512];
	va_list ap;
	va_start(ap, fmt);
	std::vsnprintf(line, sizeof(line), fmt, ap);
	va_end(ap);
	log(line);
}

bool TextSection(const void* module, const std::uint8_t** text, std::size_t* size, std::size_t* textRva) {
	const auto* base = static_cast<const std::uint8_t*>(module);
	const auto* dos  = reinterpret_cast<const IMAGE_DOS_HEADER*>(base);
	if (dos->e_magic != IMAGE_DOS_SIGNATURE) return false;
	const auto* nt = reinterpret_cast<const IMAGE_NT_HEADERS64*>(base + dos->e_lfanew);
	if (nt->Signature != IMAGE_NT_SIGNATURE) return false;
	const IMAGE_SECTION_HEADER* sec = IMAGE_FIRST_SECTION(nt);
	for (unsigned i = 0; i < nt->FileHeader.NumberOfSections; ++i, ++sec) {
		if (std::memcmp(sec->Name, ".text", 5) == 0) {
			*textRva = sec->VirtualAddress;
			*text    = base + sec->VirtualAddress;
			*size    = sec->Misc.VirtualSize;
			return true;
		}
	}
	return false;
}

} // namespace

bool Summary::Init(const void* gameModule, LogFn log) {
	log_   = log;
	ready_ = false;
	const std::uint8_t* text = nullptr;
	std::size_t         size = 0, textRva = 0;
	if (gameModule == nullptr || !TextSection(gameModule, &text, &size, &textRva)) {
		Logf(log_, "summary off: the game module has no .text section");
		return false;
	}
	const auto base = reinterpret_cast<std::uintptr_t>(gameModule);
	bool       ok   = true;
	for (int n = 0; n < SummaryNativeCount; ++n) {
		const SummaryPattern& p  = SummaryPatterns[n];
		const auto            at = FindUnique(text, size, p.pattern);
		if (!at) {
			fn_[n] = 0;
			Logf(log_, "summary: pattern %s not found once (93847 had it at 0x%llx)%s", p.name, static_cast<unsigned long long>(p.rva93847),
			     SummaryNativeOptional(n) ? "" : ": summary off");
			ok = ok && SummaryNativeOptional(n);
			continue;
		}
		const std::int64_t rel = p.rip >= 0 ? RipTarget(text, *at + static_cast<std::size_t>(p.rip)) : static_cast<std::int64_t>(*at) + p.adjust;
		fn_[n] = base + textRva + static_cast<std::uintptr_t>(rel);
		if (fn_[n] - base != p.rva93847) {
			Logf(log_, "summary: %s at 0x%llx (93847: 0x%llx)", p.name, static_cast<unsigned long long>(fn_[n] - base),
			     static_cast<unsigned long long>(p.rva93847));
		}
	}
	ready_ = ok;
	Logf(log_, ok ? "summary ready%s" : "summary off", ok && fn_[StatListText] == 0 ? " (one-stat formatter only)" : "");
	return ok;
}

bool Summary::ItemCounts(void* item) const {
	if (!ready_ || item == nullptr) return false;
	bool counts = false;
	if (!SafeMerged(reinterpret_cast<MergedFn>(fn_[Merged]), item, &counts)) Logf(log_, "summary: merged test faulted");
	return counts;
}

std::vector<StatValue> Summary::ReadItem(void* item) const {
	std::vector<StatValue> out;
	if (!ready_ || item == nullptr) return out;
	StatValue   buf[512];
	std::size_t n = 0;
	if (!SafeReadList(reinterpret_cast<GetStatListFn>(fn_[GetStatList]), item, buf, 512, &n)) {
		Logf(log_, "summary: reading an item's stats faulted");
		return out;
	}
	out.assign(buf, buf + n);
	return out;
}

std::vector<std::string> Summary::Format(const std::vector<StatValue>& totals, void* context) {
	fallback_ = false;
	if (totals.empty() || context == nullptr) return {};
	if (fn_[StatListText] != 0) {
		const TextCall    f { reinterpret_cast<AllocStatListFn>(fn_[AllocStatList]), reinterpret_cast<DataFlagFn>(fn_[DataFlag]),
                           reinterpret_cast<StatListAddFn>(fn_[StatListAdd]), reinterpret_cast<StatListTextFn>(fn_[StatListText]),
                           reinterpret_cast<FreeStatListFn>(fn_[FreeStatList]) };
		std::vector<char> buf(TextBufferSize);
		if (SafeStatListText(f, context, totals.data(), totals.size(), buf.data(), TextBufferSize)) return TooltipOrder(SplitLines(buf.data()));
		Logf(log_, "summary: the stat block writer faulted; using the one-stat formatter");
	}
	if (fn_[FormatOne] == 0 || fn_[StatRecord] == 0) return {};
	fallback_ = true;
	std::uint8_t df = 0;
	if (!SafeDataFlag(reinterpret_cast<DataFlagFn>(fn_[DataFlag]), context, &df)) return {};
	const auto recordOf = reinterpret_cast<StatRecordFn>(fn_[StatRecord]);
	const auto info     = [&](std::uint16_t stat) -> std::optional<StatInfo> {
        const std::uint8_t* rec = nullptr;
        if (!SafeRecord(recordOf, df, stat, &rec) || rec == nullptr) return std::nullopt;
        return StatInfo { At<std::int16_t>(rec, RecDescPriority), At<std::uint8_t>(rec, RecDescFunc) != 0 };
	};
	std::vector<std::string> lines;
	char                     one[OneBufferSize];
	for (const StatValue& s : OrderForDisplay(totals, info)) {
		const std::uint8_t* rec = nullptr;
		if (!SafeRecord(recordOf, df, s.stat, &rec) || rec == nullptr) continue;
		if (!SafeFormatOne(reinterpret_cast<FormatOneFn>(fn_[FormatOne]), rec, s.value, s.param, one, OneBufferSize)) continue;
		for (std::string& l : SplitLines(one)) lines.push_back(std::move(l));
	}
	return lines;
}

void Summary::Refresh(void* const* items, std::size_t count) {
	totals_.clear();
	lines_.clear();
	counted_ = skipped_ = 0;
	if (!ready_) return;
	std::vector<ItemStats> stats;
	void*                  context = nullptr;
	for (std::size_t i = 0; i < count; ++i) {
		if (items[i] == nullptr) continue;
		ItemStats s;
		s.counts = ItemCounts(items[i]);
		if (s.counts) {
			s.stats = ReadItem(items[i]);
			if (context == nullptr) context = items[i];
			++counted_;
		} else {
			++skipped_;
		}
		stats.push_back(std::move(s));
	}
	totals_ = Sum(stats);
	lines_  = Format(totals_, context);
	lines_.insert(lines_.begin(), notice_.begin(), notice_.end()); // the core's notice first (a read-only tab in a joined game)
	lines_  = CapLines(std::move(lines_));
	first_  = ClampFirst(static_cast<long long>(first_), lines_.size(), rows_);
}

std::string Summary::Fragment(LayoutMode mode, Rect area) {
	mode_  = mode;
	rows_  = LayoutRows(mode, area.height, lines_.size());
	first_ = 0;
	shown_.assign(rows_, std::string("\x01")); // never equal to a real text: the first ApplyTexts sets every row
	return LayoutFragment(mode, area, rows_);
}

void Summary::ApplyTexts(const char* panelName, bool force) {
	if (!ready_ || panelName == nullptr || rows_ == 0) return;
	void* root = *reinterpret_cast<void* const*>(fn_[UiRoot]);
	if (root == nullptr) return;
	char name[128] = {};
	strncpy_s(name, panelName, sizeof(name) - 1);
	const std::size_t first = mode_ == LayoutMode::Classic ? first_ : 0;
	for (std::size_t i = 0; i < rows_; ++i) {
		const std::string want = RowText(lines_, first, i);
		if (!force && i < shown_.size() && shown_[i] == want) continue;
		bool found = false;
		if (!SafeSetRow(reinterpret_cast<FindPanelFn>(fn_[UiFindPanel]), reinterpret_cast<FindChildFn>(fn_[UiFindChild]),
		                reinterpret_cast<SetTextFn>(fn_[TextBoxSetText]), root, name, RowName(i).c_str(), want.c_str(), want.size(), &found)) {
			Logf(log_, "summary: setting row %zu faulted", i);
			return;
		}
		if (!found) {
			Logf(log_, "summary: %s has no row %s (panel not open?)", panelName, RowName(i).c_str());
			return;
		}
		if (i < shown_.size()) shown_[i] = want;
	}
}

void Summary::ScrollBy(long long delta) {
	if (mode_ != LayoutMode::Classic) return;
	first_ = Scroll(first_, delta, lines_.size(), rows_);
}

} // namespace invtabs::summary
