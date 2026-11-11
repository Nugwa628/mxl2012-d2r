// invtabs multiplayer protocol and host-side rules. See mp_protocol.h and docs/invtabs-mp.md.
#include "mp_protocol.h"

#include <algorithm>
#include <cmath>

namespace invtabs::mp {
namespace {

constexpr std::size_t kVersionBytes = 16; // 15 chars + NUL

class Writer {
public:
	void U8(std::uint8_t v) { out_.push_back(v); }
	void U16(std::uint16_t v) { for (int i = 0; i < 2; ++i) out_.push_back(static_cast<std::uint8_t>(v >> (8 * i))); }
	void U32(std::uint32_t v) { for (int i = 0; i < 4; ++i) out_.push_back(static_cast<std::uint8_t>(v >> (8 * i))); }
	void U64(std::uint64_t v) { for (int i = 0; i < 8; ++i) out_.push_back(static_cast<std::uint8_t>(v >> (8 * i))); }
	void Text(std::string_view s) {
		const std::size_t n = std::min(s.size(), kVersionBytes - 1);
		for (std::size_t i = 0; i < kVersionBytes; ++i) out_.push_back(i < n ? static_cast<std::uint8_t>(s[i]) : 0);
	}
	Bytes Take() { return std::move(out_); }

private:
	Bytes out_;
};

class Reader {
public:
	explicit Reader(std::span<const std::uint8_t> in) : in_(in) {}
	std::uint8_t U8() { return in_[pos_++]; }
	std::uint16_t U16() { std::uint16_t v = 0; for (int i = 0; i < 2; ++i) v |= static_cast<std::uint16_t>(in_[pos_++]) << (8 * i); return v; }
	std::uint32_t U32() { std::uint32_t v = 0; for (int i = 0; i < 4; ++i) v |= static_cast<std::uint32_t>(in_[pos_++]) << (8 * i); return v; }
	std::uint64_t U64() { std::uint64_t v = 0; for (int i = 0; i < 8; ++i) v |= static_cast<std::uint64_t>(in_[pos_++]) << (8 * i); return v; }
	// Printable ASCII up to the first NUL; nullopt when unterminated or not printable.
	std::optional<std::string> Text() {
		std::string s;
		bool ended = false;
		for (std::size_t i = 0; i < kVersionBytes; ++i) {
			const std::uint8_t c = in_[pos_++];
			if (ended) continue;
			if (c == 0) { ended = true; continue; }
			if (c < 0x20 || c > 0x7E) return std::nullopt;
			s.push_back(static_cast<char>(c));
		}
		if (!ended) return std::nullopt;
		return s;
	}

private:
	std::span<const std::uint8_t> in_;
	std::size_t pos_ = 0;
};

struct Fnv {
	std::uint64_t h = 0xCBF29CE484222325ULL;
	void Byte(std::uint8_t b) { h ^= b; h *= 0x100000001B3ULL; }
	void U32(std::uint32_t v) { for (int i = 0; i < 4; ++i) Byte(static_cast<std::uint8_t>(v >> (8 * i))); }
	void Str(std::string_view s) { U32(static_cast<std::uint32_t>(s.size())); for (char c : s) Byte(static_cast<std::uint8_t>(c)); }
};

bool Overlaps(int ax, int ay, int aw, int ah, int bx, int by, int bw, int bh) noexcept {
	return ax < bx + bw && bx < ax + aw && ay < by + bh && by < ay + ah;
}

} // namespace

std::uint64_t TableHash(std::span<const Tab> tabs) {
	Fnv f;
	f.Str("invtabs-tabs-1");
	f.U32(static_cast<std::uint32_t>(tabs.size()));
	for (const Tab& t : tabs) {
		f.Str(t.name);
		f.Byte(t.rect.x); f.Byte(t.rect.y); f.Byte(t.rect.w); f.Byte(t.rect.h);
		f.Byte(t.countsCharms ? 1 : 0);
		std::vector<std::string> types = t.types;
		std::sort(types.begin(), types.end());
		types.erase(std::unique(types.begin(), types.end()), types.end());
		f.U32(static_cast<std::uint32_t>(types.size()));
		for (const std::string& ty : types) f.Str(ty);
	}
	return f.h;
}

Bytes EncodeHello(const Hello& m) {
	Writer w; w.U16(m.protocol); w.U64(m.tableHash); w.Text(m.version); return w.Take();
}
Bytes EncodeWelcome(const Welcome& m) {
	Writer w; w.U16(m.protocol); w.U8(static_cast<std::uint8_t>(m.verdict)); w.U64(m.tableHash); w.Text(m.version); return w.Take();
}
Bytes EncodeMove(const Move& m) {
	Writer w; w.U32(m.seq); w.U32(m.runtimeId); w.U8(static_cast<std::uint8_t>(m.kind)); w.U8(m.tab); return w.Take();
}
Bytes EncodeMoveDone(const MoveDone& m) {
	Writer w; w.U32(m.seq); w.U32(m.runtimeId); w.U8(static_cast<std::uint8_t>(m.result)); w.U8(m.x); w.U8(m.y); return w.Take();
}

std::optional<Hello> DecodeHello(std::span<const std::uint8_t> in) {
	if (in.size() != kHelloSize) return std::nullopt;
	Reader r(in);
	Hello m;
	m.protocol = r.U16();
	m.tableHash = r.U64();
	auto v = r.Text();
	if (!v || m.protocol == 0) return std::nullopt;
	m.version = std::move(*v);
	return m;
}

std::optional<Welcome> DecodeWelcome(std::span<const std::uint8_t> in) {
	if (in.size() != kWelcomeSize) return std::nullopt;
	Reader r(in);
	Welcome m;
	m.protocol = r.U16();
	const std::uint8_t verdict = r.U8();
	if (verdict > static_cast<std::uint8_t>(WelcomeVerdict::TableMismatch)) return std::nullopt;
	m.verdict = static_cast<WelcomeVerdict>(verdict);
	m.tableHash = r.U64();
	auto v = r.Text();
	if (!v) return std::nullopt;
	m.version = std::move(*v);
	return m;
}

std::optional<Move> DecodeMove(std::span<const std::uint8_t> in) {
	if (in.size() != kMoveSize) return std::nullopt;
	Reader r(in);
	Move m;
	m.seq = r.U32();
	m.runtimeId = r.U32();
	const std::uint8_t kind = r.U8();
	m.tab = r.U8();
	if (kind != static_cast<std::uint8_t>(MoveKind::IntoTab) && kind != static_cast<std::uint8_t>(MoveKind::OutOfPage)) return std::nullopt;
	m.kind = static_cast<MoveKind>(kind);
	if (m.kind == MoveKind::IntoTab && m.tab >= kMaxTabs) return std::nullopt;
	if (m.kind == MoveKind::OutOfPage && m.tab != 0) return std::nullopt;
	return m;
}

std::optional<MoveDone> DecodeMoveDone(std::span<const std::uint8_t> in) {
	if (in.size() != kMoveDoneSize) return std::nullopt;
	Reader r(in);
	MoveDone m;
	m.seq = r.U32();
	m.runtimeId = r.U32();
	const std::uint8_t result = r.U8();
	if (result > static_cast<std::uint8_t>(MoveResult::NotOnPage)) return std::nullopt;
	m.result = static_cast<MoveResult>(result);
	m.x = r.U8();
	m.y = r.U8();
	return m;
}

Welcome HostAnswerHello(const Hello& hello, std::uint64_t ownHash, std::string_view ownVersion) {
	Welcome w;
	w.protocol = kProtocol;
	w.tableHash = ownHash;
	w.version = std::string(ownVersion.substr(0, kVersionBytes - 1));
	if (hello.protocol != kProtocol) w.verdict = WelcomeVerdict::ProtocolMismatch;
	else if (hello.tableHash != ownHash) w.verdict = WelcomeVerdict::TableMismatch;
	else w.verdict = WelcomeVerdict::Accepted;
	return w;
}

void JoinerLink::OnWelcome(const Welcome& w, bool hostIsThisProcess) noexcept {
	if (hostIsThisProcess) { mode_ = JoinMode::Local; why_ = "this game hosts"; return; }
	switch (w.verdict) {
	case WelcomeVerdict::Accepted: mode_ = JoinMode::Full; why_ = "linked"; break;
	case WelcomeVerdict::ProtocolMismatch: mode_ = JoinMode::ViewOnly; why_ = "the hosting game runs another invtabs protocol"; break;
	case WelcomeVerdict::TableMismatch: mode_ = JoinMode::ViewOnly; why_ = "the hosting game has other tabs (invtabs.toml grid or tab list differs)"; break;
	}
}

int TabOf(std::span<const Tab> tabs, int x, int y, int w, int h) noexcept {
	for (std::size_t i = 0; i < tabs.size(); ++i)
		if (tabs[i].rect.Contains(x, y, w, h)) return static_cast<int>(i);
	return -1;
}

bool TabAccepts(const Tab& tab, std::span<const std::string> itemTypes) noexcept {
	for (const std::string& t : itemTypes)
		if (std::find(tab.types.begin(), tab.types.end(), t) != tab.types.end()) return true;
	return false;
}

bool AnyTabAccepts(std::span<const Tab> tabs, std::span<const std::string> itemTypes) noexcept {
	return std::any_of(tabs.begin(), tabs.end(), [&](const Tab& t) { return TabAccepts(t, itemTypes); });
}

std::optional<Cell> FirstFreeCell(const Rect& rect, std::span<const PageItem> page, int w, int h, std::uint32_t skipId) noexcept {
	if (!rect.Valid() || w <= 0 || h <= 0 || w > rect.w || h > rect.h) return std::nullopt;
	for (int x = rect.x; x + w <= rect.x + rect.w; ++x)
		for (int y = rect.y; y + h <= rect.y + rect.h; ++y) {
			const bool taken = std::any_of(page.begin(), page.end(), [&](const PageItem& p) {
				return p.runtimeId != skipId && Overlaps(x, y, w, h, p.x, p.y, p.w, p.h);
			});
			if (!taken) return Cell{ x, y };
		}
	return std::nullopt;
}

Plan PlanMove(std::span<const Tab> tabs, const Move& move, std::span<const std::string> itemTypes, int w, int h, bool onPage,
              std::span<const PageItem> page) noexcept {
	Plan p;
	if (move.kind == MoveKind::OutOfPage) {
		p.result = onPage ? MoveResult::Moved : MoveResult::NotOnPage;
		return p;
	}
	if (move.tab >= tabs.size()) { p.result = MoveResult::UnknownTab; return p; }
	const Tab& tab = tabs[move.tab];
	if (!TabAccepts(tab, itemTypes)) { p.result = MoveResult::TypeRefused; return p; }
	auto cell = FirstFreeCell(tab.rect, page, w, h, move.runtimeId);
	if (!cell) { p.result = MoveResult::NoRoom; return p; }
	p.result = MoveResult::Moved;
	p.cell = cell;
	return p;
}

CharmGate CharmGateFor(std::span<const Tab> tabs, bool onPage6, int x, int y, int w, int h) noexcept {
	if (!onPage6) return CharmGate::Delegate;
	const int t = TabOf(tabs, x, y, w, h);
	if (t < 0 || !tabs[static_cast<std::size_t>(t)].countsCharms) return CharmGate::Never;
	return CharmGate::Delegate;
}

Verdict Reconcile(std::span<const Tab> tabs, const PageItem& item, std::span<const std::string> itemTypes) noexcept {
	const int t = TabOf(tabs, item.x, item.y, item.w, item.h);
	if (t >= 0) return TabAccepts(tabs[static_cast<std::size_t>(t)], itemTypes) ? Verdict::Keep : Verdict::WrongType;
	// Not wholly inside one tab: does it touch any tab at all?
	for (const Tab& tab : tabs)
		if (Overlaps(item.x, item.y, item.w, item.h, tab.rect.x, tab.rect.y, tab.rect.w, tab.rect.h)) return Verdict::Straddles;
	return Verdict::OutsideTabs;
}

std::string_view VerdictName(Verdict v) noexcept {
	switch (v) {
	case Verdict::Keep: return "keep";
	case Verdict::Straddles: return "straddles tabs";
	case Verdict::OutsideTabs: return "outside every tab";
	case Verdict::WrongType: return "type not taken by its tab";
	}
	return "?";
}

bool RateLimiter::Allow(std::uint64_t nowMs) noexcept {
	if (!started_) { started_ = true; last_ = nowMs; }
	if (nowMs > last_) {
		tokens_ = std::min<double>(burst_, tokens_ + (nowMs - last_) * perSecond_ / 1000.0);
		last_ = nowMs;
	}
	if (tokens_ < 1.0) return false;
	tokens_ -= 1.0;
	return true;
}

} // namespace invtabs::mp
