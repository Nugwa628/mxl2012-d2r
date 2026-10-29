// Blaze / spider-lay state list guard (docs/bugs.md #50 #52, off word statelist).
//
// Median XL 2012 keeps its own states on vanilla ids 13 and 22 (shellshock, raptured), as 1.13c ran them. D2R's client and
// server functions for those ids read a skill from the state's stat list; Median's lists name none, so D2R logs an assert
// and leaves, where 1.14d leaves without a word. The patch (state_lists_logic.h) jumps over each assert to the instruction
// D2R runs after it, verified byte for byte before it is written.
#include "state_lists.h"

#include "state_lists_logic.h"

#include <cstdio>
#include <cstring>

auto InstallStateListGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	int done = 0;
	const char* failed = nullptr;
	for (const state_lists::Block& b : state_lists::Blocks) {
		const state_lists::Jump jump = state_lists::JumpBytes(b);
		// the whole block must be D2R's (the patch check below only covers the 5 bytes written)
		const bool same = std::memcmp(reinterpret_cast<const void*>(context->exeBase + b.rva), b.bytes, b.size) == 0;
		if (same && context->PatchBytes(b.rva, b.bytes, state_lists::PatchSize, jump.bytes, sizeof(jump.bytes))) {
			++done;
		} else if (failed == nullptr) {
			failed = b.what;
		}
	}
	std::snprintf(report, reportSize, "blaze / spider-lay state lists without a skill: %d of %zu asserts skipped (states 13, 22)%s%s", done,
	              state_lists::BlockCount, failed ? " FAILED at " : "", failed ? failed : "");
	return done;
}
