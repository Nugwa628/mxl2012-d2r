// invtabs multiplayer (TCP/IP): the channel protocol and the rules the hosting game applies for every player.
//
// Pure code: no Windows or D2RLoader headers, unit-tested by invtabs/tests/mp/mp_protocol_test.cpp. The design and the
// reasons are in docs/invtabs-mp.md; wild-healer's protocol it replaces is described there with file/line references.
//
// Trust model: the hosting game decides everything from its OWN tab table (built from its own invtabs.toml and type
// tables, charm tab pinned at 0,0). A joiner only ever asks "move item <runtime id> into tab <n>" or "out of the page";
// the host checks that the item is that peer's (D2RLoader getPeerPlayer, never an id from the message), that the tab
// accepts the item's types, and picks the cell itself over the item's whole footprint. No rectangles, verdicts, player ids
// or item bytes are taken from a message. There are no item create / save / destroy requests (upstream host 1.0.2 had
// them: a duplication and forging primitive, see the doc).
//
// ---- What the core calls (invtabs.cpp owns the SDK calls; this module only encodes, decodes and decides) ----
//
//  Plugin load (after the page is registered; NetworkService present and NetworkServiceRequiredSize):
//    registerChannel{ localChannelId = kChannelId, compatibilityToken = kCompatTag, hostMessage, clientMessage, connectionState }.
//    No service / registration refused: log one line; joiners then have view-only tabs (JoinMode::ViewOnly).
//  Every process, after the tab table is known (load and every config reload): tableHash = TableHash(tabs).
//  LocalPlayerReady: JoinerLink::Reset(); connectToHost (retry on HostUnavailable, as upstream host.cpp:1540-1560).
//  Connected (client side): send EncodeHello({kProtocol, tableHash, version}).
//  hostMessage(peer, id, bytes):
//    kMsgHello -> DecodeHello; reply EncodeWelcome(HostAnswerHello(hello, own hash)); remember peer state (Welcome or not).
//    kMsgMove  -> DecodeMove; refuse unless the peer was welcomed and RateLimiter::Allow; else queue a game-thread job:
//                 player = getPeerPlayer(peer); item = that player's item with msg.runtimeId (else NotFound);
//                 PlanMove(tabs, msg, item footprint/types, that player's page items) -> cell or refusal;
//                 executeExistingItemTransaction (CustomPage Exact / Inventory Automatic); reply EncodeMoveDone.
//    anything else -> drop (logged a few times).
//  clientMessage(id, bytes): kMsgWelcome -> JoinerLink::OnWelcome; kMsgMoveDone -> log + item sound.
//  connectionState: Rejected (UnknownPlugin / UnknownChannel / Incompatible ...) -> JoinerLink::OnRefused.
//  Joiner UI: JoinerLink::Mode() == Full -> Ctrl+click sends EncodeMove; ViewOnly -> tabs open and show, nothing moves
//    from our side (the game's own drag and drop still goes to the hosting game, which validates it, see Reconcile).
//  Hosting game, game thread, every ~10 frames and after each page item event: for EVERY player in the game, for each item
//    on page 6: Reconcile(tabs, item) -> Evict(reason): move it to that player's inventory (Automatic), else leave it
//    (it gives nothing: CharmGate below). Log each eviction.
//  Charm slot wrapper (D2RCore thunk slot, patterns kCharmCallPatterns), every process, every unit (no local-player test):
//    CharmGateFor(tabs, onPage6, x, y, w, h) == Never -> return 0; else call the previous slot target (NextCharm).
//  Page item policy on the hosting game for a drop it can't tie to its own open tab (a joiner's drag and drop):
//    AnyTabAccepts(tabs, request types) -> Allow (Reconcile moves a wrong-tab or straddling item out), else Reject.
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace invtabs::mp {

// ---- channel ----
inline constexpr std::uint16_t kChannelId = 1;                      // D2RLoader combines it with our plugin id and scope
inline constexpr std::uint64_t kCompatTag = 0x494E565441425301ULL;  // "INVTABS" + major 01: only invtabs channels link up
inline constexpr std::uint16_t kProtocol  = 1;                      // minor protocol; a major change also changes kCompatTag
inline constexpr std::size_t   kMaxPayload = 224;                   // D2RLoader NetworkService MaxPayloadSize
inline constexpr int           kPageSize   = 16;
inline constexpr int           kMaxTabs    = 12;

enum MsgId : std::uint16_t {
	kMsgHello    = 1,   // joiner -> host: protocol, tab-table hash, plugin version
	kMsgMove     = 2,   // joiner -> host: move one of my items into tab n / out of the page
	kMsgWelcome  = 101, // host -> joiner: accepted or why not
	kMsgMoveDone = 102, // host -> joiner: result of a move
};

// ---- tab table (the host's own; the joiner's only for display and the hash) ----
struct Rect {
	std::uint8_t x = 0, y = 0, w = 0, h = 0;
	bool operator==(const Rect&) const = default;
	[[nodiscard]] bool Valid() const noexcept { return w > 0 && h > 0 && x + w <= kPageSize && y + h <= kPageSize; }
	[[nodiscard]] bool Contains(int cx, int cy, int cw, int ch) const noexcept {
		return cw > 0 && ch > 0 && cx >= x && cy >= y && cx + cw <= x + w && cy + ch <= y + h;
	}
};

struct Tab {
	std::string              name;   // e.g. "charms"
	Rect                     rect;
	bool                     countsCharms = false; // charms inside give their bonus (the charm tab)
	std::vector<std::string> types;  // accepted itemtypes codes (an item fits when one of its type + Equiv parents is listed)
};

// FNV-1a 64 over a canonical form: tab count, then per tab in order: name, rect, flags, types sorted. Equal hash = the
// same tabs at the same places accepting the same types (grid sizes in the two tomls included).
[[nodiscard]] std::uint64_t TableHash(std::span<const Tab> tabs);

// ---- messages (packed little-endian, exact sizes) ----
struct Hello {
	std::uint16_t protocol = kProtocol;
	std::uint64_t tableHash = 0;
	std::string   version; // plugin version text, at most 15 chars kept
};

enum class WelcomeVerdict : std::uint8_t {
	Accepted         = 0,
	ProtocolMismatch = 1, // same token, other minor protocol the host can't serve
	TableMismatch    = 2, // other tabs (toml grid size, tab list or type tables): the joiner's tabs are view-only
};

struct Welcome {
	std::uint16_t  protocol = kProtocol;
	WelcomeVerdict verdict  = WelcomeVerdict::Accepted;
	std::uint64_t  tableHash = 0; // the host's
	std::string    version;
};

enum class MoveKind : std::uint8_t {
	IntoTab   = 1, // from the joiner's inventory / cursor / stash into tab `tab`; the host picks the cell
	OutOfPage = 2, // from page 6 back to the inventory (Automatic)
};

struct Move {
	std::uint32_t seq = 0;
	std::uint32_t runtimeId = 0;
	MoveKind      kind = MoveKind::IntoTab;
	std::uint8_t  tab = 0;
};

enum class MoveResult : std::uint8_t {
	Moved        = 0,
	NotWelcome   = 1, // no accepted Hello from this peer
	BadMessage   = 2,
	UnknownTab   = 3,
	NotFound     = 4, // no item with that id among the peer's own items
	TypeRefused  = 5, // the tab does not take the item's types
	NoRoom       = 6,
	RateLimited  = 7,
	Failed       = 8, // D2RLoader refused the move (the host log has the item result)
	NotOnPage    = 9, // OutOfPage for an item that isn't on page 6
};

struct MoveDone {
	std::uint32_t seq = 0;
	std::uint32_t runtimeId = 0;
	MoveResult    result = MoveResult::Moved;
	std::uint8_t  x = 0xFF, y = 0xFF; // page cell when moved into a tab
};

inline constexpr std::size_t kHelloSize    = 2 + 8 + 16;
inline constexpr std::size_t kWelcomeSize  = 2 + 1 + 8 + 16;
inline constexpr std::size_t kMoveSize     = 4 + 4 + 1 + 1;
inline constexpr std::size_t kMoveDoneSize = 4 + 4 + 1 + 1 + 1;
static_assert(kHelloSize <= kMaxPayload && kWelcomeSize <= kMaxPayload);

using Bytes = std::vector<std::uint8_t>;
[[nodiscard]] Bytes EncodeHello(const Hello&);
[[nodiscard]] Bytes EncodeWelcome(const Welcome&);
[[nodiscard]] Bytes EncodeMove(const Move&);
[[nodiscard]] Bytes EncodeMoveDone(const MoveDone&);
// Decoders: nullopt for a wrong size or an out-of-range field (unknown kind / verdict / result). Never trust more than that.
[[nodiscard]] std::optional<Hello>    DecodeHello(std::span<const std::uint8_t>);
[[nodiscard]] std::optional<Welcome>  DecodeWelcome(std::span<const std::uint8_t>);
[[nodiscard]] std::optional<Move>     DecodeMove(std::span<const std::uint8_t>);
[[nodiscard]] std::optional<MoveDone> DecodeMoveDone(std::span<const std::uint8_t>);

// Host: the answer to a Hello.
[[nodiscard]] Welcome HostAnswerHello(const Hello& hello, std::uint64_t ownHash, std::string_view ownVersion);

// ---- joiner link state ----
enum class JoinMode : std::uint8_t {
	Unknown  = 0, // connecting (a few seconds after the game starts): tabs show, moves wait
	Local    = 1, // single player or this process hosts: everything is local
	Full     = 2, // joined, welcomed: Ctrl+click goes to the host as Move
	ViewOnly = 3, // joined, host without invtabs channel, other protocol or other tabs: tabs show, our moves are off
};

class JoinerLink {
public:
	void Reset() noexcept { *this = {}; }
	void OnWelcome(const Welcome& w, bool hostIsThisProcess) noexcept;
	void OnRefused() noexcept { mode_ = JoinMode::ViewOnly; why_ = "the hosting game has no invtabs channel (no invtabs, or another major version)"; }
	void OnNoNetwork() noexcept { mode_ = JoinMode::ViewOnly; why_ = "no D2RLoader network service"; }
	[[nodiscard]] JoinMode         Mode() const noexcept { return mode_; }
	[[nodiscard]] std::string_view Why() const noexcept { return why_; }

private:
	JoinMode         mode_ = JoinMode::Unknown;
	std::string_view why_ = "connecting";
};

// ---- page geometry (host side, every player) ----
struct PageItem {
	std::uint32_t runtimeId = 0;
	int           x = 0, y = 0, w = 1, h = 1; // size from the game's item data (ItemSize), never from the code
};

struct Cell {
	int  x = 0, y = 0;
	bool operator==(const Cell&) const = default;
};

// The tab whose rectangle holds the WHOLE footprint, or -1 (straddling two tabs, or outside every tab).
[[nodiscard]] int TabOf(std::span<const Tab> tabs, int x, int y, int w, int h) noexcept;
// One of `itemTypes` (the item's type and its Equiv parents) is in the tab's list.
[[nodiscard]] bool TabAccepts(const Tab& tab, std::span<const std::string> itemTypes) noexcept;
[[nodiscard]] bool AnyTabAccepts(std::span<const Tab> tabs, std::span<const std::string> itemTypes) noexcept;
// First free top-left cell for a w x h item inside `rect`, column by column like the game; `skipId` is the item itself.
[[nodiscard]] std::optional<Cell> FirstFreeCell(const Rect& rect, std::span<const PageItem> page, int w, int h, std::uint32_t skipId) noexcept;

struct Plan {
	MoveResult          result = MoveResult::Failed;
	std::optional<Cell> cell; // IntoTab: page cell to move to
};
// The host's decision for a joiner's Move, from its own table and that player's own page. `onPage` says whether the item
// is on page 6 now.
[[nodiscard]] Plan PlanMove(std::span<const Tab> tabs, const Move& move, std::span<const std::string> itemTypes, int w, int h, bool onPage,
                            std::span<const PageItem> page) noexcept;

// ---- charm rule and the hosting game's check of page 6 ----
enum class CharmGate : std::uint8_t {
	Delegate = 0, // not ours to decide: the previous target of the charm slot (D2RCore's IsCharmUsable chain) decides
	Never    = 1, // on page 6 outside every charm tab (or straddling): gives nothing
};
// Same answer for every player unit and on every process (server refresh 0x470d9a, use check 0x475102, client refresh
// 0x1c97e3): there is no local-player test.
[[nodiscard]] CharmGate CharmGateFor(std::span<const Tab> tabs, bool onPage6, int x, int y, int w, int h) noexcept;

enum class Verdict : std::uint8_t { Keep = 0, Straddles = 1, OutsideTabs = 2, WrongType = 3 };
[[nodiscard]] Verdict Reconcile(std::span<const Tab> tabs, const PageItem& item, std::span<const std::string> itemTypes) noexcept;
[[nodiscard]] std::string_view VerdictName(Verdict) noexcept;

// ---- per-peer rate limit (host) ----
class RateLimiter {
public:
	explicit RateLimiter(int burst = 8, int perSecond = 8) noexcept : burst_(burst), perSecond_(perSecond), tokens_(burst) {}
	[[nodiscard]] bool Allow(std::uint64_t nowMs) noexcept;

private:
	int           burst_, perSecond_;
	double        tokens_;
	std::uint64_t last_ = 0;
	bool          started_ = false;
};

// ---- where the charm slot is (93847 verified unique in .text of the dump; '??' = any byte) ----
// Each pattern ends at a `call rel32` (E8 at `callOffset`) whose target is D2RCore's thunk `FF 25 disp32` -> slot. All three
// must reach the same thunk; else the charm gate stays off with a log line (target B).
struct CallPattern {
	std::string_view name;
	std::string_view bytes;
	int              callOffset;
	std::uint32_t    rva93847; // where it matched on 93847 (the call is at rva + callOffset)
};
inline constexpr std::array<CallPattern, 3> kCharmCallPatterns { {
	{ "server refresh charm loop", "83 F8 01 75 ?? 48 8B D7 48 8B CB E8 ?? ?? ?? ?? 85 C0 74 ?? 33 D2 48 8B CB E8", 11, 0x470D8F },
	{ "server can-use check", "48 8B D7 48 8B CB E8 ?? ?? ?? ?? 85 C0 74 18 0F B6 8E 06 01 00 00", 6, 0x4750FC },
	{ "client refresh charm loop", "83 F8 01 75 ?? 48 8B D3 48 8B CF E8 ?? ?? ?? ?? 85 C0 74 ?? 33 D2 48 8B CF E8", 11, 0x1C97D8 },
} };
inline constexpr std::uint32_t kCharmThunkRva93847 = 0x3E2B61C; // FF 25 7E F6 FF FF -> slot 0x3E2ACA0

} // namespace invtabs::mp
