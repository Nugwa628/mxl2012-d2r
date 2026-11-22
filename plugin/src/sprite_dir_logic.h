// Pure part of the sprite-card direction hooks (sprite_dir.cpp): which animation binding a facing picks, which state
// machines are ours, and the list of card units being watched. No game calls: tested standalone (tests/sprite_dir_test.cpp).
#pragma once

#include <cstddef>
#include <cstdint>

namespace sprite_dir {

// D2R's functions (image offsets) and the bytes each hook expects at its entry; a part of the game that reads differently
// is left alone (the part then reports itself off).
inline constexpr uint64_t RvaTransition = 0xf61ae0;  // (machine, entity, &model, &state, weaponClass, speed, start, force)
inline constexpr uint64_t RvaModeChange = 0x773f30;  // (system, &model, unit, registry, unitType, mode, f): unit mode -> state;
                                                     // run for every monster every frame, where the registry may be changed
// PUSH RBP / PUSH RBX / PUSH RSI / PUSH RDI / PUSH R12 / PUSH R13 / PUSH R14 / PUSH R15 / LEA RBP,[RSP-0x118]
inline constexpr uint8_t TransitionEntry[] = {0x40, 0x55, 0x53, 0x56, 0x57, 0x41, 0x54, 0x41, 0x55, 0x41, 0x56,
                                              0x41, 0x57, 0x48, 0x8d, 0xac, 0x24, 0xe8, 0xfe, 0xff, 0xff};
// MOV R11,RSP / PUSH RBP / PUSH RBX / PUSH RDI / LEA RBP,[R11-0x318] / SUB RSP,0x400
inline constexpr uint8_t ModeChangeEntry[] = {0x4c, 0x8b, 0xdc, 0x55, 0x53, 0x57, 0x49, 0x8d, 0xab, 0xe8,
                                              0xfc, 0xff, 0xff, 0x48, 0x81, 0xec, 0x00, 0x04, 0x00, 0x00};
inline constexpr uint64_t RvaUnitLayer = 0x77a3b0;  // (layer): the unit translation layer's update, once a frame on the
                                                    // registry's thread (reads the registry, drains the unit event queue)
// MOV R11,RSP / PUSH RBP / PUSH RBX / PUSH RSI / PUSH RDI / LEA RBP,[R11-0x308] / SUB RSP,0x3e8
inline constexpr uint8_t UnitLayerEntry[] = {0x4c, 0x8b, 0xdc, 0x55, 0x53, 0x56, 0x57, 0x49, 0x8d, 0xab, 0xf8,
                                             0xfc, 0xff, 0xff, 0x48, 0x81, 0xec, 0xe8, 0x03, 0x00, 0x00};
// Functions the hooks call and never change; their entry bytes are compared before the part installs.
inline constexpr uint64_t RvaRefresh = 0xf62330;     // (machine, entity, &model, weaponClass, machine2, controller2):
                                                     // the state of machine2 again with another weapon class, time kept
// MOV RAX,RSP / MOV [RAX+8],RBX / MOV [RAX+0x10],RBP / MOV [RAX+0x18],RSI / MOV [RAX+0x20],RDI
inline constexpr uint8_t RefreshEntry[] = {0x48, 0x8b, 0xc4, 0x48, 0x89, 0x58, 0x08, 0x48, 0x89, 0x68,
                                           0x10, 0x48, 0x89, 0x70, 0x18, 0x48, 0x89, 0x78, 0x20};
inline constexpr uint64_t RvaMachineOf = 0x670a20;   // (registry, entity) -> state machine instance or null
// MOV [RSP+8],RBX / MOV [RSP+0x18],RSI / PUSH RDI / SUB RSP,0x20 / MOV RAX,[RCX+0x38]
inline constexpr uint8_t MachineOfEntry[] = {0x48, 0x89, 0x5c, 0x24, 0x08, 0x48, 0x89, 0x74, 0x24, 0x18,
                                             0x57, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0x41, 0x38};
inline constexpr uint64_t RvaClipLength = 0xef19c0;  // (controller) -> the length of one loop of the clip it plays
// MOV RCX,[RCX+8] / TEST RCX,RCX / JNZ 0x16159a0 / XORPS XMM0,XMM0 / RET
inline constexpr uint8_t ClipLengthEntry[] = {0x48, 0x8b, 0x49, 0x08, 0x48, 0x85, 0xc9, 0x0f, 0x85,
                                              0xd3, 0x3f, 0x72, 0x00, 0x0f, 0x57, 0xc0, 0xc3};
inline constexpr uint64_t RvaSetClock = 0x1616b80;   // (Granny control, seconds): the control's time within its loop
// PUSH RBX / SUB RSP,0x50 / MOVAPS [RSP+0x40],XMM6 / MOV RBX,RCX / MOVAPS XMM6,XMM1
inline constexpr uint8_t SetClockEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x50, 0x0f, 0x29, 0x74,
                                            0x24, 0x40, 0x48, 0x8b, 0xd9, 0x0f, 0x28, 0xf1};
inline constexpr uint64_t RvaControllerOf = 0x670540;  // (registry, entity) -> animation controller component or null
inline constexpr uint64_t RvaWorld = 0x9124e0;         // () -> the object that owns the entity registry
// The two getters a facing is read with. 0x34ae80 (unit) -> its path:
// PUSH RBX / SUB RSP,0x20 / MOV RBX,RCX / TEST RCX,RCX / JNZ +0x13, and at +0x3a MOV RAX,[RBX+0x38] / ADD RSP,0x20 / POP RBX / RET
inline constexpr uint8_t UnitPathEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0x48, 0x85, 0xc9, 0x75, 0x13};
inline constexpr int UnitPathTailAt = 0x3a;
inline constexpr uint8_t UnitPathTail[] = {0x48, 0x8b, 0x43, 0x38, 0x48, 0x83, 0xc4, 0x20, 0x5b, 0xc3};
// 0x341950 (path) -> its direction, 0-63 (the float at path + 0x80):
// TEST RCX,RCX / JNZ +8 / XORPS XMM0,XMM0 / CVTTSS2SI EAX,XMM0 / RET / CVTTSS2SI EAX,[RCX+0x80] / RET
inline constexpr uint8_t PathFacingEntry[] = {0x48, 0x85, 0xc9, 0x75, 0x08, 0x0f, 0x57, 0xc0, 0xf3, 0x0f, 0x2c,
                                              0xc0, 0xc3, 0xf3, 0x0f, 0x2c, 0x81, 0x80, 0x00, 0x00, 0x00, 0xc3};
inline constexpr uint64_t RvaRegistry = 0x9125c0;      // (world) -> registry; asserts off the world's own thread (world +
                                                       // 0xa0) and while the registry may not be changed (world + 0x110)
// PUSH RBX / SUB RSP,0x20 / MOV RBX,RCX / CALL 0x122b140 / CMP RAX,[RBX+0xa0] / JZ +0x14 / LEA RCX,[RSP+0x30] /
// MOV BYTE [RSP+0x30],0 / CALL 0x9118b0 / TEST AL,AL / JZ +1 / INT3 / CMP BYTE [RBX+0x110],0
inline constexpr uint8_t RegistryEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0xe8, 0x72, 0x8b, 0x91, 0x00,
                                            0x48, 0x3b, 0x83, 0xa0, 0x00, 0x00, 0x00, 0x74, 0x14, 0x48, 0x8d, 0x4c, 0x24, 0x30,
                                            0xc6, 0x44, 0x24, 0x30, 0x00, 0xe8, 0xca, 0xf2, 0xff, 0xff, 0x84, 0xc0, 0x74, 0x01,
                                            0xcc, 0x80, 0xbb, 0x10, 0x01, 0x00, 0x00, 0x00};
inline constexpr uint64_t RvaThreadId = 0x122b140;     // () -> the id 0x9125c0 compares with world + 0xa0
inline constexpr uint64_t RvaUnitPath = 0x34ae80;      // (unit) -> path
inline constexpr uint64_t RvaPathFacing = 0x341950;    // (path) -> direction 0-63 (0x349fd0 makes the model's yaw of it)

// Offsets.
inline constexpr int MachineAsset = 0x08;        // state machine instance -> its asset
inline constexpr int MachineState = 0x20;        // -> the current state
inline constexpr int StateId = 0x04;             // state -> its stateId
inline constexpr int AssetFileName = 0x08;       // asset -> file name: pointer to the characters,
inline constexpr int AssetFileNameLength = 0x10; // and their count
inline constexpr int ModelEntity = 0xa8;         // unit model -> entity id
inline constexpr int WorldThread = 0xa0;         // world -> the id of the thread that may use the registry
inline constexpr int WorldMutable = 0x110;       // world -> a byte: the registry may be changed now (0x9125c0 asserts on 0)
inline constexpr int RegistryIdsBegin = 0x30;    // registry -> entity ids (uint32), begin and end
inline constexpr int RegistryIdsEnd = 0x38;
inline constexpr int ControllerInComponent = 8;  // controller component -> the controller the engine's calls take
inline constexpr int ControllerControl = 8;      // controller -> the Granny control of the clip it plays

// A card unit's state machine lives under this folder (tools/monster_flipbook.py FOLDER): the only thing the hooks act on.
inline constexpr char Marker[] = "/mxl/flip/";

// Directions: each state of a card unit's machine binds one clip per facing, under the weapon class keys in the engine's
// own order (0xf63186: hth 0, bow 1, 1hs 2, 1ht 3, stf 4, 2hs 5, 2ht 6, xbw 7); key k shows the k-th facing clockwise on
// screen from "down". A monster's own weapon class is hth: without the hook every state shows "down".
inline constexpr int Keys = 8;

// The facing of a path direction (0-63) as both games count eight of them (D2R 0x3aeb30's table at 0x237ff10, 1.14d
// 0x63e7a0): 60-63 and 0-3 -> 0, 4-11 -> 1, ... 52-59 -> 7. Direction 0 looks down the screen, higher ones turn clockwise.
constexpr auto KeyOf(int32_t direction) noexcept -> int32_t {
	return (((direction & 63) + 4) >> 3) & 7;
}

// A state's start fraction (the share of one loop the engine hands on: a monster's own phase when it appears, the running
// time when 0xf62330 plays a state again). The engine turns it into seconds while the new clip's loop count is still 0,
// for which Granny answers "for ever" (0xef10b0: fraction x 0x162dce0 = 1.9e38 s); a clip that loops for ever wraps that
// away, a card state's counted loops cannot (the clip would stand at its end, with the engine's assert
// "outAnimationTimeElapsed >= 0.0f"). So a card state starts at 0 and gets this time set afterwards.
constexpr auto StartTime(float fraction, float length) noexcept -> float {
	return fraction > 0.0f && fraction < 1.0f && length > 0.0f ? fraction * length : 0.0f;
}

// True when `name` (a state machine asset's file name, either slash, any case) is under the card folder. `size` bounds
// the read; a name without an end inside it is not ours.
constexpr auto IsCardMachine(const char* name, size_t size) noexcept -> bool {
	const size_t m = sizeof(Marker) - 1;
	size_t len = 0;
	while (len < size && name[len] != '\0') {
		++len;
	}
	if (len == size || len < m) {
		return false;
	}
	for (size_t i = 0; i + m <= len; ++i) {
		size_t k = 0;
		for (; k < m; ++k) {
			char c = name[i + k];
			c = c == '\\' ? '/' : (c >= 'A' && c <= 'Z') ? static_cast<char>(c - 'A' + 'a') : c;
			if (c != Marker[k]) {
				break;
			}
		}
		if (k == m) {
			return true;
		}
	}
	return false;
}

// The card units on screen: unit -> entity and the key its machine plays. A fixed, small list; when it is full the oldest
// entry goes (that unit then keeps the direction it shows until its next mode change).
struct Entry {
	const void* unit;
	uint32_t unitId;
	uint32_t entity;
	int32_t key;
	uint32_t age;
};

class Watch {
public:
	static constexpr int Size = 64;

	[[nodiscard]] auto Count() const noexcept -> int { return count_; }

	auto FindUnit(const void* unit) noexcept -> Entry* {
		for (int i = 0; i < count_; ++i) {
			if (entries_[i].unit == unit) {
				return &entries_[i];
			}
		}
		return nullptr;
	}

	auto FindEntity(uint32_t entity) noexcept -> Entry* {
		for (int i = 0; i < count_; ++i) {
			if (entries_[i].entity == entity) {
				return &entries_[i];
			}
		}
		return nullptr;
	}

	// The unit's entry with this entity and key; an older entry of the same unit or the same entity is replaced.
	auto Set(const void* unit, uint32_t unitId, uint32_t entity, int32_t key) noexcept -> Entry* {
		for (int i = count_ - 1; i >= 0; --i) {
			if (entries_[i].unit == unit || entries_[i].entity == entity) {
				RemoveAt(i);
			}
		}
		if (count_ == Size) {
			int oldest = 0;
			for (int i = 1; i < count_; ++i) {
				if (static_cast<int32_t>(entries_[i].age - entries_[oldest].age) < 0) {
					oldest = i;
				}
			}
			RemoveAt(oldest);
		}
		entries_[count_] = Entry{unit, unitId, entity, key, ++clock_};
		return &entries_[count_++];
	}

	void Remove(const Entry* entry) noexcept {
		if (entry >= entries_ && entry < entries_ + count_) {
			RemoveAt(static_cast<int>(entry - entries_));
		}
	}

	void Clear() noexcept { count_ = 0; }

	// The i-th entry, 0 <= i < Count() (Remove moves the last entry into the removed one's place: walk from the end).
	auto At(int i) noexcept -> Entry* { return &entries_[i]; }

private:
	void RemoveAt(int i) noexcept {
		entries_[i] = entries_[--count_];
	}

	Entry entries_[Size] = {};
	int count_ = 0;
	uint32_t clock_ = 0;
};

}  // namespace sprite_dir
