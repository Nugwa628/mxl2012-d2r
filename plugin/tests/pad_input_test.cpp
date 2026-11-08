// Standalone test of the scripted gamepad's pure part (pad_input_logic.h; not part of the plugin DLL).
#include "../src/pad_input_logic.h"

#include <cstdio>

namespace {
int failures = 0;
void Check(bool ok, const char* what) {
	if (!ok) {
		++failures;
		std::printf("FAIL: %s\n", what);
	}
}
}  // namespace

int main() {
	using namespace padin;

	Check(ButtonByName("A") == A && ButtonByName("lb") == LB && ButtonByName("RT") == RT, "button names");
	Check(ButtonByName("dleft") == Left && ButtonByName("menu") == Start && ButtonByName("l3") == LS, "aliases");
	Check(ButtonByName("z") == 0 && ButtonByName("") == 0, "unknown name");

	hcmd::Tokens t;
	uint32_t mask = 0;
	long long ms = 120;
	hcmd::Split("press a", &t);
	Check(ParseButtons(t, 1, &mask, &ms) && mask == A && ms == 120, "one button, default ms");
	hcmd::Split("press lb+a down 300", &t);
	Check(ParseButtons(t, 1, &mask, &ms) && mask == (LB | A | Down) && ms == 300, "joined and listed buttons, ms");
	hcmd::Split("press 300", &t);
	Check(!ParseButtons(t, 1, &mask, &ms), "a number alone is no button");
	hcmd::Split("press a+q", &t);
	Check(!ParseButtons(t, 1, &mask, &ms), "unknown joined name");
	hcmd::Split("press", &t);
	Check(!ParseButtons(t, 1, &mask, &ms), "no button");
	hcmd::Split("press a 99999", &t);
	Check(!ParseButtons(t, 1, &mask, &ms), "ms out of range");

	int16_t v = 0;
	Check(ParseAxis("100", &v) && v == 32767, "axis +100");
	Check(ParseAxis("-100", &v) && v == -32767, "axis -100");
	Check(ParseAxis("50", &v) && v == 16383, "axis 50");
	Check(!ParseAxis("101", &v) && !ParseAxis("x", &v), "axis range");

	State s;
	Pad p = Poll(&s, 1000);
	Check(p.buttons == 0 && s.packet == 0, "idle pad, no packet change");
	Press(&s, A | RT, 100);
	p = Poll(&s, 5000);  // first poll that returns it starts the clock
	Check(p.buttons == A && p.rt == 255 && s.packet == 1, "press down, RT full");
	p = Poll(&s, 5001);
	p = Poll(&s, 5002);
	Check(p.buttons == A, "down for TapPolls polls");
	p = Poll(&s, 5003);
	Check(p.buttons == A, "still down before tapMs");
	p = Poll(&s, 5100);
	Check(p.buttons == 0 && p.rt == 0 && s.packet == 2, "up after tapMs");

	Press(&s, B, 0);
	int downPolls = 0;
	for (int i = 0; i < 6; ++i) {
		downPolls += (Poll(&s, 6000 + i).buttons & B) != 0 ? 1 : 0;
	}
	Check(downPolls == TapPolls, "0 ms press: exactly TapPolls polls down");

	s.held = LB;
	s.lx = -32767;
	s.lt = 40;
	p = Poll(&s, 7000);
	Check(p.buttons == LB && p.lx == -32767 && p.lt == 40, "hold, stick, trigger");
	Release(&s, LB);
	p = Poll(&s, 7001);
	Check(p.buttons == 0 && p.lx == -32767, "release one button keeps the stick");
	const uint32_t packet = s.packet;
	Release(&s, 0);
	p = Poll(&s, 7002);
	Check(p.buttons == 0 && p.lx == 0 && p.lt == 0 && s.packet == packet + 1, "release all centres, packet keeps growing");

	if (failures == 0) {
		std::printf("pad_input_test: all passed\n");
	}
	return failures == 0 ? 0 : 1;
}
