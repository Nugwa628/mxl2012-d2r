// Unit tests for invtabs/src/mp_protocol.*: message encoding and validation, handshake, host placement, charm gate.
#include "mp_protocol.h"

#include <cstdio>
#include <string>
#include <vector>

using namespace invtabs::mp;

static int g_failed = 0;
static int g_checks = 0;
#define CHECK(cond) do { ++g_checks; if (!(cond)) { ++g_failed; std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #cond); } } while (0)

static std::vector<Tab> Tabs(int charmCols = 10, int charmRows = 6) {
	std::vector<Tab> t;
	t.push_back({ "charms", { 0, 0, static_cast<std::uint8_t>(charmCols), static_cast<std::uint8_t>(charmRows) }, true, { "char" } });
	t.push_back({ "gems", { 0, static_cast<std::uint8_t>(charmRows), 10, 4 }, false, { "gem", "rune" } });
	t.push_back({ "misc", { 10, 0, 6, 10 }, false, { "misc", "char" } });
	return t;
}

static const std::vector<std::string> kCharm = { "scha", "char", "misc" };
static const std::vector<std::string> kGem = { "gema", "gem" };
static const std::vector<std::string> kSword = { "swor", "mele", "weap" };

static void TestRoundTrips() {
	Hello h{ kProtocol, 0x1122334455667788ULL, "1.0.0" };
	auto hb = EncodeHello(h);
	CHECK(hb.size() == kHelloSize);
	auto hd = DecodeHello(hb);
	CHECK(hd && hd->protocol == kProtocol && hd->tableHash == h.tableHash && hd->version == "1.0.0");

	Hello longV{ kProtocol, 1, "0123456789abcdefXYZ" };
	auto ld = DecodeHello(EncodeHello(longV));
	CHECK(ld && ld->version == "0123456789abcde"); // cut to 15 chars

	Welcome w{ kProtocol, WelcomeVerdict::TableMismatch, 42, "1.2.3" };
	auto wd = DecodeWelcome(EncodeWelcome(w));
	CHECK(wd && wd->verdict == WelcomeVerdict::TableMismatch && wd->tableHash == 42 && wd->version == "1.2.3");

	Move m{ 7, 0xABCDEF01, MoveKind::IntoTab, 2 };
	auto mb = EncodeMove(m);
	CHECK(mb.size() == kMoveSize);
	auto md = DecodeMove(mb);
	CHECK(md && md->seq == 7 && md->runtimeId == 0xABCDEF01 && md->kind == MoveKind::IntoTab && md->tab == 2);

	MoveDone d{ 7, 0xABCDEF01, MoveResult::NoRoom, 0xFF, 0xFF };
	auto dd = DecodeMoveDone(EncodeMoveDone(d));
	CHECK(dd && dd->result == MoveResult::NoRoom && dd->x == 0xFF);

	// little-endian layout, fixed
	CHECK(mb[0] == 7 && mb[1] == 0 && mb[4] == 0x01 && mb[7] == 0xAB && mb[8] == 1 && mb[9] == 2);
}

static void TestRejectsBadMessages() {
	auto hb = EncodeHello({ kProtocol, 5, "v" });
	CHECK(!DecodeHello(std::span(hb).first(hb.size() - 1)));         // short
	auto longer = hb; longer.push_back(0);
	CHECK(!DecodeHello(longer));                                      // long
	auto noNul = hb; for (std::size_t i = 10; i < hb.size(); ++i) noNul[i] = 'a';
	CHECK(!DecodeHello(noNul));                                       // unterminated text
	auto ctrl = hb; ctrl[10] = 0x07;
	CHECK(!DecodeHello(ctrl));                                        // not printable
	auto zero = hb; zero[0] = 0; zero[1] = 0;
	CHECK(!DecodeHello(zero));                                        // protocol 0

	auto mb = EncodeMove({ 1, 2, MoveKind::IntoTab, 0 });
	auto badKind = mb; badKind[8] = 9;
	CHECK(!DecodeMove(badKind));
	auto badTab = mb; badTab[9] = kMaxTabs;
	CHECK(!DecodeMove(badTab));
	auto outWithTab = EncodeMove({ 1, 2, MoveKind::OutOfPage, 0 }); outWithTab[9] = 1;
	CHECK(!DecodeMove(outWithTab));
	CHECK(!DecodeMove({}));

	auto wb = EncodeWelcome({});
	wb[2] = 3;
	CHECK(!DecodeWelcome(wb));
	auto db = EncodeMoveDone({});
	db[8] = 10;
	CHECK(!DecodeMoveDone(db));

	// Every message fits D2RLoader's payload limit.
	CHECK(kHelloSize <= kMaxPayload && kWelcomeSize <= kMaxPayload && kMoveSize <= kMaxPayload && kMoveDoneSize <= kMaxPayload);
}

static void TestHashAndHandshake() {
	const auto a = Tabs();
	CHECK(TableHash(a) == TableHash(Tabs()));
	CHECK(TableHash(a) != TableHash(Tabs(10, 4)));            // other charm grid size in the toml
	auto reordered = a; std::swap(reordered[1].types[0], reordered[1].types[1]);
	CHECK(TableHash(a) == TableHash(reordered));               // type order does not matter
	auto renamed = a; renamed[2].name = "other";
	CHECK(TableHash(a) != TableHash(renamed));
	auto noCount = a; noCount[0].countsCharms = false;
	CHECK(TableHash(a) != TableHash(noCount));
	CHECK(TableHash({}) != TableHash(a));

	const auto own = TableHash(a);
	CHECK(HostAnswerHello({ kProtocol, own, "x" }, own, "1.0").verdict == WelcomeVerdict::Accepted);
	CHECK(HostAnswerHello({ kProtocol, own + 1, "x" }, own, "1.0").verdict == WelcomeVerdict::TableMismatch);
	CHECK(HostAnswerHello({ kProtocol + 1, own, "x" }, own, "1.0").verdict == WelcomeVerdict::ProtocolMismatch);

	JoinerLink link;
	CHECK(link.Mode() == JoinMode::Unknown);
	link.OnWelcome({ kProtocol, WelcomeVerdict::Accepted, own, "1" }, false);
	CHECK(link.Mode() == JoinMode::Full);
	link.OnWelcome({ kProtocol, WelcomeVerdict::TableMismatch, own, "1" }, false);
	CHECK(link.Mode() == JoinMode::ViewOnly);
	link.Reset();
	link.OnWelcome({ kProtocol, WelcomeVerdict::Accepted, own, "1" }, true);
	CHECK(link.Mode() == JoinMode::Local);
	link.Reset();
	link.OnRefused();
	CHECK(link.Mode() == JoinMode::ViewOnly && !link.Why().empty());
}

static void TestGeometry() {
	const auto t = Tabs();
	CHECK(TabOf(t, 0, 0, 1, 1) == 0);
	CHECK(TabOf(t, 9, 5, 1, 1) == 0);
	CHECK(TabOf(t, 9, 4, 1, 3) == -1);  // grand charm whose top-left is in charms but reaches the gems tab
	CHECK(TabOf(t, 9, 0, 2, 1) == -1);  // straddles charms and misc
	CHECK(TabOf(t, 0, 6, 1, 1) == 1);
	CHECK(TabOf(t, 15, 9, 1, 1) == 2);
	CHECK(TabOf(t, 15, 15, 1, 1) == -1);
	CHECK(TabOf(t, 0, 0, 0, 1) == -1);

	CHECK(TabAccepts(t[0], kCharm) && !TabAccepts(t[0], kGem) && !AnyTabAccepts(t, kSword));

	std::vector<PageItem> page = { { 1, 0, 0, 1, 3 }, { 2, 1, 0, 1, 1 } };
	auto c = FirstFreeCell(t[0].rect, page, 1, 2, 99);
	CHECK(c && *c == (Cell{ 0, 3 }));  // column by column: below the 1x3 item in column 0
	c = FirstFreeCell(t[0].rect, page, 1, 3, 1);  // the item itself does not block
	CHECK(c && *c == (Cell{ 0, 0 }));
	CHECK(!FirstFreeCell(t[0].rect, page, 11, 1, 0));
	std::vector<PageItem> full;
	for (std::uint32_t i = 0; i < 60; ++i) full.push_back({ i + 10, static_cast<int>(i / 6), static_cast<int>(i % 6), 1, 1 });
	CHECK(!FirstFreeCell(t[0].rect, full, 1, 1, 0));
}

static void TestPlanMove() {
	const auto t = Tabs();
	std::vector<PageItem> page;
	auto p = PlanMove(t, { 1, 5, MoveKind::IntoTab, 0 }, kCharm, 1, 3, false, page);
	CHECK(p.result == MoveResult::Moved && p.cell && *p.cell == (Cell{ 0, 0 }));
	CHECK(PlanMove(t, { 1, 5, MoveKind::IntoTab, 1 }, kCharm, 1, 1, false, page).result == MoveResult::TypeRefused);
	CHECK(PlanMove(t, { 1, 5, MoveKind::IntoTab, 0 }, kSword, 1, 3, false, page).result == MoveResult::TypeRefused);
	CHECK(PlanMove(t, { 1, 5, MoveKind::IntoTab, 7 }, kCharm, 1, 1, false, page).result == MoveResult::UnknownTab);
	CHECK(PlanMove(t, { 1, 5, MoveKind::OutOfPage, 0 }, kCharm, 1, 1, true, page).result == MoveResult::Moved);
	CHECK(PlanMove(t, { 1, 5, MoveKind::OutOfPage, 0 }, kCharm, 1, 1, false, page).result == MoveResult::NotOnPage);
	// a 1x3 grand charm never lands in a 10x2 tab
	std::vector<Tab> small = { { "charms", { 0, 0, 10, 2 }, true, { "char" } } };
	CHECK(PlanMove(small, { 1, 5, MoveKind::IntoTab, 0 }, kCharm, 1, 3, false, page).result == MoveResult::NoRoom);
}

static void TestCharmGateAndReconcile() {
	const auto t = Tabs();
	CHECK(CharmGateFor(t, false, 0, 0, 1, 1) == CharmGate::Delegate);  // inventory: the game / Median rule decides
	CHECK(CharmGateFor(t, true, 0, 0, 1, 3) == CharmGate::Delegate);
	CHECK(CharmGateFor(t, true, 9, 4, 1, 3) == CharmGate::Never);      // reaches out of the charm tab
	CHECK(CharmGateFor(t, true, 12, 0, 1, 1) == CharmGate::Never);     // misc tab takes charms but does not count them
	CHECK(CharmGateFor(t, true, 15, 15, 1, 1) == CharmGate::Never);    // orphan outside every tab
	CHECK(CharmGateFor({}, true, 0, 0, 1, 1) == CharmGate::Never);     // no tabs: nothing on page 6 counts

	CHECK(Reconcile(t, { 1, 0, 0, 1, 3 }, kCharm) == Verdict::Keep);
	CHECK(Reconcile(t, { 1, 0, 0, 1, 1 }, kGem) == Verdict::WrongType);
	CHECK(Reconcile(t, { 1, 9, 4, 1, 3 }, kCharm) == Verdict::Straddles);
	CHECK(Reconcile(t, { 1, 15, 15, 1, 1 }, kCharm) == Verdict::OutsideTabs);
	CHECK(VerdictName(Verdict::Straddles) == "straddles tabs");
}

static void TestRateLimiter() {
	RateLimiter r(3, 2);
	CHECK(r.Allow(0) && r.Allow(0) && r.Allow(0));
	CHECK(!r.Allow(0));
	CHECK(!r.Allow(400));   // 0.8 token
	CHECK(r.Allow(500));    // 1.0 token
	CHECK(r.Allow(10'000) && r.Allow(10'000) && r.Allow(10'000) && !r.Allow(10'000)); // capped at burst
}

static void TestPatterns() {
	for (const auto& p : kCharmCallPatterns) {
		// the byte at callOffset is E8 (call rel32), followed by four wildcards
		const std::string_view b = p.bytes;
		const std::size_t at = static_cast<std::size_t>(p.callOffset) * 3;
		CHECK(b.substr(at, 2) == "E8");
		CHECK(b.substr(at + 3, 11) == "?? ?? ?? ??");
	}
}

int main() {
	TestRoundTrips();
	TestRejectsBadMessages();
	TestHashAndHandshake();
	TestGeometry();
	TestPlanMove();
	TestCharmGateAndReconcile();
	TestRateLimiter();
	TestPatterns();
	std::printf("%d checks, %d failed\n", g_checks, g_failed);
	return g_failed == 0 ? 0 : 1;
}
