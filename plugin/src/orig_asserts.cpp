// Guards of D2R asserts that 1.14d does not have (docs/bugs.md #74 #181, off words animseq, monequip, aurastate).
//
// Median XL 2012's data takes three paths that 1.14d (the stand-in for 1.13c) runs without a word and D2R runs the same way
// after logging an assert: a monster skill mode with no sequence (haunt_vasily, haunt_amazon), a monequip row without a body
// location (flyingscimitar), a timed buff without an aurastate (Mon Pain Spirit). The patch (orig_asserts_logic.h) jumps over
// each assert to the instruction D2R runs after it, verified byte for byte before it is written.
#include "orig_asserts.h"

#include "orig_asserts_logic.h"

#include <cstdio>
#include <cstring>

auto InstallOrigAssertGuard(const D2RL::PluginContext* context, size_t index, char* report, size_t reportSize) noexcept -> int {
	if (index >= orig_asserts::BlockCount) {
		return 0;
	}
	const orig_asserts::Block& b = orig_asserts::Blocks[index];
	const orig_asserts::Jump jump = orig_asserts::JumpBytes(b);
	// the whole block must be D2R's (the patch check below only covers the 5 bytes written)
	const bool same = std::memcmp(reinterpret_cast<const void*>(context->exeBase + b.rva), b.bytes, b.size) == 0;
	const bool ok = same && context->PatchBytes(b.rva, b.bytes, orig_asserts::PatchSize, jump.bytes, sizeof(jump.bytes));
	std::snprintf(report, reportSize, "%s: assert skipped as 1.14d (0x%llx -> jmp 0x%llx)%s", b.what, static_cast<unsigned long long>(b.rva),
	              static_cast<unsigned long long>(b.next), ok ? "" : " FAILED");
	return ok ? 1 : 0;
}
