// Dodge / avoid / evade state list guard (docs/bugs.md #53, off word dodgelist).
//
// Median XL 2012 gives the dodge / avoid / evade chances (stats 338-340) without D2R's dodge / avoid / evade states; when one
// succeeds, D2R's damage code asks for that state's stat list, finds none, logs "BC_ASSERT: hList" (SUnitDmg.cpp) and leaves
// the function. The dodge itself has happened by then (the hit is already resolved); 1.13c skipped the list without a word.
// The patch (dodge_list_logic.h) jumps over the assert to the same exit, verified byte for byte before it is written.
#include "dodge_list.h"

#include "dodge_list_logic.h"

#include <cstdio>
#include <cstring>

auto InstallDodgeListGuard(const D2RL::PluginContext* context, char* report, size_t reportSize) noexcept -> int {
	const dodge_list::Jump jump = dodge_list::JumpBytes();
	// the whole block must be D2R's (the patch check below only covers the 5 bytes written)
	const bool same = std::memcmp(reinterpret_cast<const void*>(context->exeBase + dodge_list::RvaAssertBlock), dodge_list::Expected,
	                              sizeof(dodge_list::Expected)) == 0;
	const bool ok = same && context->PatchBytes(dodge_list::RvaAssertBlock, dodge_list::Expected, dodge_list::PatchSize, jump.bytes,
	                                            sizeof(jump.bytes));
	std::snprintf(report, reportSize, "dodge / avoid / evade without the state list: assert skipped (0x44b152 -> jmp 0x44b27d)%s",
	              ok ? "" : " FAILED");
	return ok ? 1 : 0;
}
