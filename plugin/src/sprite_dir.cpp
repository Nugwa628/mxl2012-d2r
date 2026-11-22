// Sprite-card monsters turn (lane hdtools-monster; on word spritedir, off unless mxl2012-core-on.txt names it).
//
// A card unit (tools/monster_flipbook.py) is a camera-facing card that plays a monster's classic frames in HD graphics. The
// engine picks a state's clip by the unit's weapon class (0xf61ae0: the state's bindings, searched by weapon class); a card
// unit's machine binds one clip per facing under the first eight weapon class keys, so the key picks the facing. Three
// hooks, all of which leave every state machine that is not under the card folder (sprite_dir_logic.h Marker) exactly as
// it was:
//   0xf61ae0  state transition: for a card machine the weapon class becomes the key of the unit's facing, and a start
//             fraction becomes a time set on the new clip (sprite_dir_logic.h StartTime);
//   0x773f30  unit mode -> state (for a live monster only when its mode changes): tells the transitions inside it which
//             unit they belong to;
//   0x77a3b0  the unit translation layer's update, once a frame on the registry's thread: afterwards every watched card
//             unit whose facing left the key its machine plays gets the engine's own "same state, other weapon class"
//             call (0xf62330), which keeps the animation's time. (The same check also runs after a monster's mode call:
//             a turn then shows in the frame it happens.)
// Nothing is written into the game's objects except through the game's own calls (0xf62330, the clip time setter
// 0x1616b80); whatever does not look as expected (a null, a stale entity, another thread than the registry's own, a moment
// in which the registry may not be changed, an unreadable name) ends the hook's own work and the game's function runs as
// it always does.
#include "sprite_dir.h"

#include "d2r.h"
#include "sprite_dir_logic.h"

#include <windows.h>

#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstring>

namespace {

using d2r::Unit;

constexpr int UnitId = 0x08;
constexpr int UnitMode = 0x0c;

// Stack arguments pass through as the 8-byte slots they are (of 0xf61ae0 the fifth is the weapon class, the seventh the
// start fraction, a float; one spare slot each).
using TransitionFn = uint64_t (*)(void* machine, uint64_t entity, void** model, void** state, uint64_t weaponClass, uint64_t speed,
                                  uint64_t start, uint64_t force, uint64_t spare);
using ModeChangeFn = uint64_t (*)(void* system, void** model, Unit* unit, void* registry, uint64_t unitType, uint64_t mode,
                                  uint64_t f, uint64_t spare);
using LayerFn = void (*)(void* layer);
using RefreshFn = void (*)(void* machine, uint32_t entity, void** model, int32_t weaponClass, void* machine2, void* controller2);

TransitionFn g_transition = nullptr;
ModeChangeFn g_modeChange = nullptr;
LayerFn g_layer = nullptr;
uint64_t g_base = 0;
const D2RL::PluginContext* g_context = nullptr;
bool g_verbose = false;
bool g_tickOnly = false;  // test switch: turns only after the layer update (what a card with no other monster gets)

CRITICAL_SECTION g_lock;
sprite_dir::Watch g_watch;
volatile LONG g_watched = 0;  // entries in g_watch: the hooks' quick way out

volatile LONG g_keyed = 0;      // transitions of card machines that got a facing's key
volatile LONG g_unkeyed = 0;    // transitions of card machines with no unit known (weapon class left as it was)
volatile LONG g_turns = 0;      // refresh calls after a facing change
volatile LONG g_skipped = 0;    // facing changes not applied (stale entity, no machine or controller)
volatile LONG g_logLines = 0;
volatile LONG g_turnsTick = 0;  // turns applied after the layer update,
volatile LONG g_turnsMode = 0;  // and after a monster's mode call

// The unit whose mode change is running on this thread (0x773f30), for the transitions inside it.
thread_local Unit* t_unit = nullptr;
thread_local uint32_t t_entity = 0;

// A model with no child entities for 0xf61ae0's walk over them (model + 0x10 list, + 0x18 count; nothing else is read).
alignas(16) uint8_t g_noModel[0x100] = {};

template <typename F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

void Log(const char* format, ...) noexcept {
	if (!g_verbose || g_context == nullptr || InterlockedIncrement(&g_logLines) > 600) {
		return;
	}
	char line[320];
	va_list args;
	va_start(args, format);
	std::vsnprintf(line, sizeof(line), format, args);
	va_end(args);
	g_context->LogInfo(line);
}

// The file name of a state machine instance's asset, copied out; false when anything on the way cannot be read.
auto MachineName(const void* machine, char* out, size_t size) noexcept -> bool {
	__try {
		const void* asset = d2r::At<const void*>(machine, sprite_dir::MachineAsset);
		if (asset == nullptr) {
			return false;
		}
		const char* name = d2r::At<const char*>(asset, sprite_dir::AssetFileName);
		const uint64_t length = d2r::At<uint64_t>(asset, sprite_dir::AssetFileNameLength);
		if (name == nullptr || length == 0 || length >= size) {
			return false;
		}
		std::memcpy(out, name, length);
		out[length] = '\0';
		return true;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return false;
	}
}

auto IsCardMachine(const void* machine) noexcept -> bool {
	char name[200];
	return machine != nullptr && MachineName(machine, name, sizeof(name)) && sprite_dir::IsCardMachine(name, sizeof(name));
}

// The key of a monster's facing, or -1 when the unit has no path to read it from.
auto FacingKey(Unit* unit) noexcept -> int32_t {
	if (unit == nullptr || d2r::At<int32_t>(unit, d2r::UnitType) != 1) {
		return -1;
	}
	void* path = Fn<void* (*)(Unit*)>(sprite_dir::RvaUnitPath)(unit);
	if (path == nullptr) {
		return -1;
	}
	return sprite_dir::KeyOf(Fn<int32_t (*)(void*)>(sprite_dir::RvaPathFacing)(path));
}

// The registry when this thread may change it now (its own thread, outside the engine's read-only stretches of a frame:
// 0x9125c0 asserts otherwise) and `entity` is alive in it, else null.
auto RegistryFor(uint32_t entity) noexcept -> void* {
	void* world = Fn<void* (*)()>(sprite_dir::RvaWorld)();
	if (world == nullptr || d2r::At<uint64_t>(world, sprite_dir::WorldThread) != GetCurrentThreadId() ||
	    d2r::At<uint8_t>(world, sprite_dir::WorldMutable) == 0) {
		return nullptr;
	}
	void* registry = Fn<void* (*)(void*)>(sprite_dir::RvaRegistry)(world);
	if (registry == nullptr) {
		return nullptr;
	}
	const uint32_t* begin = d2r::At<const uint32_t*>(registry, sprite_dir::RegistryIdsBegin);
	const uint32_t* end = d2r::At<const uint32_t*>(registry, sprite_dir::RegistryIdsEnd);
	const uint32_t index = entity & 0xfffff;
	if (begin == nullptr || end < begin || index >= static_cast<uint64_t>(end - begin) || begin[index] != entity) {
		return nullptr;
	}
	return registry;
}

// The animation controller of an entity, or null (see RegistryFor).
auto ControllerFor(uint32_t entity) noexcept -> void* {
	void* registry = RegistryFor(entity);
	void* component = registry != nullptr ? Fn<void* (*)(void*, uint32_t)>(sprite_dir::RvaControllerOf)(registry, entity) : nullptr;
	return component != nullptr ? static_cast<uint8_t*>(component) + sprite_dir::ControllerInComponent : nullptr;
}

// Verbose: the animation controller's clock after a card transition (the time of its last event pass, controller + 0x1dc;
// the Granny control's local clock + 0x8c, speed + 0x90, one loop's length + 0x94, loop index + 0x98 and count + 0x9c).
void LogClock(uint32_t entity) noexcept {
	__try {
		const void* controller = ControllerFor(entity);
		const void* control = controller != nullptr ? d2r::At<const void*>(controller, sprite_dir::ControllerControl) : nullptr;
		if (control != nullptr) {
			Log("spritedir:   clock: last pass %.4f; local %.4f speed %.3f length %.4f loop %d of %d", d2r::At<float>(controller, 0x1dc),
			    d2r::At<float>(control, 0x8c), d2r::At<float>(control, 0x90), d2r::At<float>(control, 0x94),
			    d2r::At<int32_t>(control, 0x98), d2r::At<int32_t>(control, 0x9c));
		}
	} __except (EXCEPTION_EXECUTE_HANDLER) {
	}
}

auto TransitionHook(void* machine, uint64_t entity, void** model, void** state, uint64_t weaponClass, uint64_t speed, uint64_t start,
                    uint64_t force, uint64_t spare) noexcept -> uint64_t {
	if (machine == nullptr || (g_watched == 0 && t_unit == nullptr) || !IsCardMachine(machine)) {
		return g_transition(machine, entity, model, state, weaponClass, speed, start, force, spare);
	}
	const uint32_t id = static_cast<uint32_t>(entity);
	// The start fraction: the state starts at 0, its time is set below (sprite_dir_logic.h StartTime).
	float fraction = 0.0f;
	std::memcpy(&fraction, &start, sizeof(fraction));
	start &= 0xffffffff00000000ull;
	void* controller = fraction > 0.0f ? ControllerFor(id) : nullptr;
	void* const before = controller != nullptr ? d2r::At<void*>(controller, sprite_dir::ControllerControl) : nullptr;
	int32_t key = -1;
	EnterCriticalSection(&g_lock);
	if (t_unit != nullptr && t_entity == id) {
		key = FacingKey(t_unit);
		if (key >= 0) {
			g_watch.Set(t_unit, d2r::At<uint32_t>(t_unit, UnitId), id, key);
			InterlockedExchange(&g_watched, g_watch.Count());
		}
	} else if (const sprite_dir::Entry* e = g_watch.FindEntity(id)) {
		key = e->key;
	}
	LeaveCriticalSection(&g_lock);
	bool said = false;
	if (key >= 0) {
		if (InterlockedIncrement(&g_keyed) == 1 && g_verbose) {
			char name[200] = "";
			MachineName(machine, name, sizeof(name));
			Log("spritedir: first card machine %s", name);
		}
		// (a state asked for again without force changes nothing in the engine: the dead state is, every frame)
		if (g_verbose && state != nullptr && *state != nullptr &&
		    ((force & 0xff) != 0 || *state != d2r::At<void*>(machine, sprite_dir::MachineState))) {
			said = true;
			Log("spritedir: transition entity %08x state %d key %d (weapon class %d, force %d, start %.4f)", id,
			    d2r::At<int32_t>(*state, sprite_dir::StateId), key, static_cast<int32_t>(weaponClass), static_cast<int>(force & 0xff),
			    fraction);
		}
		weaponClass = (weaponClass & 0xffffffff00000000ull) | static_cast<uint32_t>(key);
	} else {
		InterlockedIncrement(&g_unkeyed);
		Log("spritedir: transition entity %08x of a card machine without a unit", id);
	}
	const uint64_t result = g_transition(machine, entity, model, state, weaponClass, speed, start, force, spare);
	if (controller != nullptr) {
		void* control = d2r::At<void*>(controller, sprite_dir::ControllerControl);
		if (control != nullptr && control != before) {  // (the same control: nothing was started)
			const float time = sprite_dir::StartTime(fraction, Fn<float (*)(void*)>(sprite_dir::RvaClipLength)(controller));
			if (time > 0.0f) {
				Fn<void (*)(void*, float)>(sprite_dir::RvaSetClock)(control, time);
			}
		}
	}
	if (said) {
		LogClock(id);
	}
	return result;
}

// A watched unit's facing left its key: the state again under the new key. False when the entry is of no use any more.
auto Turn(uint32_t entity, int32_t key) noexcept -> bool {
	void* registry = RegistryFor(entity);
	if (registry == nullptr) {
		return false;
	}
	void* machine = Fn<void* (*)(void*, uint32_t)>(sprite_dir::RvaMachineOf)(registry, entity);
	if (machine == nullptr || !IsCardMachine(machine) || d2r::At<void*>(machine, sprite_dir::MachineState) == nullptr) {
		return false;
	}
	void* component = Fn<void* (*)(void*, uint32_t)>(sprite_dir::RvaControllerOf)(registry, entity);
	if (component == nullptr) {
		return false;
	}
	void* noModel = g_noModel;
	Fn<RefreshFn>(sprite_dir::RvaRefresh)(machine, entity, &noModel, key, machine,
	                                      static_cast<uint8_t*>(component) + sprite_dir::ControllerInComponent);
	return true;
}

// The facing key of a watched unit, -1 when the address no longer holds that monster (or cannot be read), -2 when the
// key is unknown for now.
auto WatchedKey(const sprite_dir::Entry& e) noexcept -> int32_t {
	__try {
		Unit* unit = static_cast<Unit*>(const_cast<void*>(e.unit));
		if (d2r::At<int32_t>(unit, d2r::UnitType) != 1 || d2r::At<uint32_t>(unit, UnitId) != e.unitId) {
			return -1;
		}
		const int32_t key = FacingKey(unit);
		return key >= 0 ? key : -2;
	} __except (EXCEPTION_EXECUTE_HANDLER) {
		return -1;
	}
}

// After the layer update or a monster's mode call, on the registry's thread at a moment it may be changed: every watched
// card unit whose facing left the key its machine plays turns. (A live monster gets its own mode call only when its mode
// changes, so a turn inside one mode, walking or standing, is caught after the once-a-frame layer update.)
void FollowAll(bool tick) noexcept {
	struct Due {
		uint32_t unitId;
		uint32_t entity;
		int32_t key;
	};
	Due due[sprite_dir::Watch::Size];
	int count = 0;
	EnterCriticalSection(&g_lock);
	for (int i = g_watch.Count() - 1; i >= 0; --i) {
		sprite_dir::Entry* e = g_watch.At(i);
		const int32_t now = WatchedKey(*e);
		if (now == -1) {
			g_watch.Remove(e);  // the address is another unit's now
		} else if (now >= 0 && now != e->key) {
			e->key = now;
			due[count++] = Due{e->unitId, e->entity, now};
		}
	}
	InterlockedExchange(&g_watched, g_watch.Count());
	LeaveCriticalSection(&g_lock);
	for (int i = 0; i < count; ++i) {
		if (Turn(due[i].entity, due[i].key)) {
			InterlockedIncrement(&g_turns);
			InterlockedIncrement(tick ? &g_turnsTick : &g_turnsMode);
			Log("spritedir: unit %u entity %08x turns to key %d (after %s)", due[i].unitId, due[i].entity, due[i].key,
			    tick ? "the layer update" : "a monster's mode call");
			continue;
		}
		InterlockedIncrement(&g_skipped);
		Log("spritedir: unit %u entity %08x: turn to key %d not applied", due[i].unitId, due[i].entity, due[i].key);
		EnterCriticalSection(&g_lock);
		if (sprite_dir::Entry* e = g_watch.FindEntity(due[i].entity)) {
			g_watch.Remove(e);
			InterlockedExchange(&g_watched, g_watch.Count());
		}
		LeaveCriticalSection(&g_lock);
	}
}

// True when this thread may change the registry now (its own thread, outside the engine's read-only stretches of a frame).
auto Mutable() noexcept -> bool {
	const void* world = Fn<void* (*)()>(sprite_dir::RvaWorld)();
	return world != nullptr && d2r::At<uint64_t>(world, sprite_dir::WorldThread) == GetCurrentThreadId() &&
	       d2r::At<uint8_t>(world, sprite_dir::WorldMutable) != 0;
}

auto ModeChangeHook(void* system, void** model, Unit* unit, void* registry, uint64_t unitType, uint64_t mode, uint64_t f,
                    uint64_t spare) noexcept -> uint64_t {
	Unit* const outerUnit = t_unit;
	const uint32_t outerEntity = t_entity;
	const bool monster = unit != nullptr && model != nullptr && *model != nullptr && static_cast<uint32_t>(unitType) == 1;
	if (monster) {
		t_unit = unit;
		t_entity = d2r::At<uint32_t>(*model, sprite_dir::ModelEntity);
	} else {
		t_unit = nullptr;
	}
	const uint64_t result = g_modeChange(system, model, unit, registry, unitType, mode, f, spare);
	t_unit = outerUnit;
	t_entity = outerEntity;
	if (monster && outerUnit == nullptr && !g_tickOnly && g_watched != 0 && Mutable()) {
		FollowAll(false);
	}
	return result;
}

// Once a frame: the unit translation layer drains its queue of unit events (a live monster that only walks or stands
// posts none, so its turns are caught here).
void LayerHook(void* layer) noexcept {
	g_layer(layer);
	if (g_watched != 0 && Mutable()) {
		FollowAll(true);
	}
}

auto Same(uint64_t rva, const uint8_t* expected, size_t size) noexcept -> bool {
	return std::memcmp(reinterpret_cast<const void*>(g_base + rva), expected, size) == 0;
}

}  // namespace

auto InstallSpriteDir(const D2RL::PluginContext* context, bool verbose, bool tickOnly, char* report, size_t reportSize) noexcept -> int {
	d2r::Bind(context->exeBase);
	g_base = context->exeBase;
	g_context = context;
	g_verbose = verbose;
	g_tickOnly = tickOnly;
	// Every function the hooks call or wrap must read as expected before anything goes in.
	if (!Same(sprite_dir::RvaTransition, sprite_dir::TransitionEntry, sizeof(sprite_dir::TransitionEntry)) ||
	    !Same(sprite_dir::RvaModeChange, sprite_dir::ModeChangeEntry, sizeof(sprite_dir::ModeChangeEntry)) ||
	    !Same(sprite_dir::RvaUnitLayer, sprite_dir::UnitLayerEntry, sizeof(sprite_dir::UnitLayerEntry)) ||
	    !Same(sprite_dir::RvaRefresh, sprite_dir::RefreshEntry, sizeof(sprite_dir::RefreshEntry)) ||
	    !Same(sprite_dir::RvaMachineOf, sprite_dir::MachineOfEntry, sizeof(sprite_dir::MachineOfEntry)) ||
	    !Same(sprite_dir::RvaUnitPath, sprite_dir::UnitPathEntry, sizeof(sprite_dir::UnitPathEntry)) ||
	    !Same(sprite_dir::RvaUnitPath + sprite_dir::UnitPathTailAt, sprite_dir::UnitPathTail, sizeof(sprite_dir::UnitPathTail)) ||
	    !Same(sprite_dir::RvaPathFacing, sprite_dir::PathFacingEntry, sizeof(sprite_dir::PathFacingEntry)) ||
	    !Same(sprite_dir::RvaClipLength, sprite_dir::ClipLengthEntry, sizeof(sprite_dir::ClipLengthEntry)) ||
	    !Same(sprite_dir::RvaSetClock, sprite_dir::SetClockEntry, sizeof(sprite_dir::SetClockEntry)) ||
	    !Same(sprite_dir::RvaRegistry, sprite_dir::RegistryEntry, sizeof(sprite_dir::RegistryEntry))) {
		std::snprintf(report, reportSize, "sprite cards keep one facing: the game's animation functions read differently here");
		return 0;
	}
	InitializeCriticalSection(&g_lock);
	// The transition hook goes in last: without the others it has no unit and changes nothing.
	const bool mode = context->InstallInlineHook(sprite_dir::RvaModeChange, sprite_dir::ModeChangeEntry, sizeof(sprite_dir::ModeChangeEntry),
	                                             reinterpret_cast<void*>(&ModeChangeHook), reinterpret_cast<void**>(&g_modeChange));
	const bool layer =
	    mode && context->InstallInlineHook(sprite_dir::RvaUnitLayer, sprite_dir::UnitLayerEntry, sizeof(sprite_dir::UnitLayerEntry),
	                                       reinterpret_cast<void*>(&LayerHook), reinterpret_cast<void**>(&g_layer));
	const bool transition =
	    layer && context->InstallInlineHook(sprite_dir::RvaTransition, sprite_dir::TransitionEntry, sizeof(sprite_dir::TransitionEntry),
	                                        reinterpret_cast<void*>(&TransitionHook), reinterpret_cast<void**>(&g_transition));
	std::snprintf(report, reportSize,
	              "sprite cards show the facing's clip (machines under %s): mode 0x773f30%s, layer 0x77a3b0%s, transition 0xf61ae0%s%s",
	              sprite_dir::Marker, mode ? "" : " FAILED", layer ? "" : (mode ? " FAILED" : " not tried"),
	              transition ? "" : (layer ? " FAILED" : " not tried"), tickOnly ? " (test: turns after the layer update only)" : "");
	return (mode ? 1 : 0) + (layer ? 1 : 0) + (transition ? 1 : 0);
}

void SpriteDirCounts(long* keyed, long* unkeyed, long* turns, long* skipped, long* watched) noexcept {
	*keyed = g_keyed;
	*unkeyed = g_unkeyed;
	*turns = g_turns;
	*skipped = g_skipped;
	*watched = g_watched;
}

void SpriteDirTurns(long* afterLayer, long* afterMode) noexcept {
	*afterLayer = g_turnsTick;
	*afterMode = g_turnsMode;
}
