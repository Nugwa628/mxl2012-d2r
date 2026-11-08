// Pure part of the test harness's scripted gamepad (`pad` verb in harness_cmds.cpp, dev builds only; unit test
// plugin/tests/pad_input_test.cpp): button names, stick / trigger values and the state one XInputGetState poll returns.
#pragma once

#include <cstdint>

#include "harness_cmds_logic.h"

namespace padin {

// XINPUT_GAMEPAD wButtons bits; LT / RT are not buttons in XInput, here they are bits 16 / 17 of a mask (trigger 255).
constexpr uint32_t Up = 0x0001, Down = 0x0002, Left = 0x0004, Right = 0x0008, Start = 0x0010, Back = 0x0020;
constexpr uint32_t LS = 0x0040, RS = 0x0080, LB = 0x0100, RB = 0x0200, A = 0x1000, B = 0x2000, X = 0x4000, Y = 0x8000;
constexpr uint32_t LT = 0x10000, RT = 0x20000;
constexpr uint32_t ButtonMask = 0xf3ff;

struct Name {
	const char* name;
	uint32_t bit;
};
constexpr Name Names[] = {{"a", A},         {"b", B},         {"x", X},         {"y", Y},          {"lb", LB},  {"rb", RB},
                          {"lt", LT},       {"rt", RT},       {"ls", LS},       {"rs", RS},        {"l3", LS},  {"r3", RS},
                          {"start", Start}, {"menu", Start},  {"back", Back},   {"view", Back},    {"up", Up},  {"down", Down},
                          {"left", Left},   {"right", Right}, {"dup", Up},      {"ddown", Down},   {"dleft", Left},
                          {"dright", Right}};

// One button's bit, or 0 for an unknown name.
inline auto ButtonByName(const char* s) noexcept -> uint32_t {
	for (const Name& n : Names) {
		if (hcmd::LowerEq(s, n.name)) {
			return n.bit;
		}
	}
	return 0;
}

// Buttons from tok[from..]; each token is a name or names joined by '+' ("lb+a"). A last plain number is a duration in
// ms (`*ms`, left alone without one). False on an unknown name or no button at all.
inline auto ParseButtons(const hcmd::Tokens& t, int from, uint32_t* mask, long long* ms) noexcept -> bool {
	*mask = 0;
	for (int i = from; i < t.n; ++i) {
		long long v = 0;
		if (i == t.n - 1 && i > from && hcmd::ParseInt(t.tok[i], &v)) {
			if (v < 0 || v > 60000) {
				return false;
			}
			*ms = v;
			break;
		}
		char word[32];
		const char* p = t.tok[i];
		while (*p != '\0') {
			size_t n = 0;
			while (*p != '\0' && *p != '+' && n + 1 < sizeof(word)) {
				word[n++] = *p++;
			}
			word[n] = '\0';
			if (*p == '+') {
				++p;
			}
			const uint32_t bit = ButtonByName(word);
			if (bit == 0) {
				return false;
			}
			*mask |= bit;
		}
	}
	return *mask != 0;
}

// A stick axis in percent, -100..100 (y up is positive, as XInput), to the XInput range.
inline auto ParseAxis(const char* s, int16_t* out) noexcept -> bool {
	long long v = 0;
	if (!hcmd::ParseInt(s, &v) || v < -100 || v > 100) {
		return false;
	}
	*out = static_cast<int16_t>(v * 32767 / 100);
	return true;
}

// What one poll returns (the XINPUT_GAMEPAD fields).
struct Pad {
	uint16_t buttons = 0;
	uint8_t lt = 0;
	uint8_t rt = 0;
	int16_t lx = 0, ly = 0, rx = 0, ry = 0;
};

inline auto SamePad(const Pad& a, const Pad& b) noexcept -> bool {
	return a.buttons == b.buttons && a.lt == b.lt && a.rt == b.rt && a.lx == b.lx && a.ly == b.ly && a.rx == b.rx && a.ry == b.ry;
}

constexpr int TapPolls = 3;  // a press is down for at least this many polls, so the game sees the edge both ways

struct State {
	uint32_t held = 0;     // `hold`: down until `release`
	uint32_t tapped = 0;   // `press`: down for tapMs after the first poll that returns it, and at least TapPolls polls
	uint64_t tapMs = 0;
	uint64_t tapStart = 0;  // 0 until a poll returned the press
	int tapPolls = 0;
	uint8_t lt = 0, rt = 0;  // `trigger`
	int16_t lx = 0, ly = 0, rx = 0, ry = 0;
	uint32_t packet = 0;  // dwPacketNumber: grows whenever the returned state changes
	Pad last;
};

inline void Press(State* s, uint32_t mask, uint64_t ms) noexcept {
	s->tapped |= mask;
	s->tapMs = ms;
	s->tapStart = 0;
	s->tapPolls = TapPolls;
}

// Releases `mask` (held and pressed); 0 = everything, sticks centred and triggers up as well.
inline void Release(State* s, uint32_t mask) noexcept {
	if (mask == 0) {
		const uint32_t packet = s->packet;
		const Pad last = s->last;
		*s = State{};
		s->packet = packet;
		s->last = last;
		return;
	}
	s->held &= ~mask;
	s->tapped &= ~mask;
}

// The state one poll at time `now` (ms) returns; ends a press that has run its course.
inline auto Poll(State* s, uint64_t now) noexcept -> Pad {
	if (s->tapped != 0) {
		if (s->tapStart == 0) {
			s->tapStart = now == 0 ? 1 : now;
		}
		if (s->tapPolls <= 0 && now - s->tapStart >= s->tapMs) {
			s->tapped = 0;
		} else {
			--s->tapPolls;
		}
	}
	const uint32_t down = s->held | s->tapped;
	Pad p;
	p.buttons = static_cast<uint16_t>(down & ButtonMask);
	p.lt = (down & LT) != 0 ? 255 : s->lt;
	p.rt = (down & RT) != 0 ? 255 : s->rt;
	p.lx = s->lx;
	p.ly = s->ly;
	p.rx = s->rx;
	p.ry = s->ry;
	if (!SamePad(p, s->last)) {
		++s->packet;
		s->last = p;
	}
	return p;
}

}  // namespace padin
