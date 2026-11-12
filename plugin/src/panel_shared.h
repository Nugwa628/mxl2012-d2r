// What the plugin's native panels share (the developer menu devmenu.cpp and the wiki panel wiki.cpp; docs/dev-menu.md "How the panel is put
// together", docs/wiki-panel.md): layout resources, button clicks through registered panel names, D2R's own text setter with change
// tracking, the search box typing fix, the mouse wheel over a panel, and reading a table file from the mod. Pure rules: panel_logic.h.
//
// One panel is one `Client` (static storage, added once at install). The UI message listener and the subclass of the game window exist once
// for all clients. Everything here runs on the UI thread (the thread that owns the game window) unless a comment says otherwise.
#pragma once

#include <D2RLPlugin/api.h>

#include <atomic>
#include <cstddef>
#include <string>

namespace panel_shared {

// The search box of a panel in the current graphics mode: the panel's place from the screen centre and the box inside it, layout units.
struct BoxRect {
	bool hd = true;
	int panelX = 0, panelY = 0, x = 0, y = 0, w = 0, h = 0;
};

struct Client {
	const char* panelName = "";       // the layout's root name, "mxl2012-core/DevMenu"
	const char* inputName = nullptr;  // its InputTextBoxWidget (null: no text box)
	const char* buttonPrefix = "";    // a button's click names the panel <buttonPrefix><n>, "mxl2012-core/DevMenuB_"
	int buttonCount = 0;
	// UI listener: button n was clicked. Queue it; the work runs on the client's own tick.
	void (*onPress)(int button) noexcept = nullptr;
	// The search box's rectangle now (false: no box).
	bool (*inputBox)(BoxRect* box) noexcept = nullptr;
	// The mouse wheel turned while the panel is open: notches (positive: away from the user) at client pixel (x, y) of a client area
	// clientW x clientH. True: the panel took it and D2R does not get the message. Null: the wheel stays the game's.
	bool (*onWheel)(int notches, int x, int y, int clientW, int clientH) noexcept = nullptr;
	// A key went down while the panel is open and its box does not have the keyboard. True: taken (D2R gets neither the press nor the release).
	bool (*onKey)(unsigned virtualKey) noexcept = nullptr;

	std::atomic<bool> open{false};        // the panel is open (the client's tick sets it)
	std::atomic<bool> boxFocus{false};    // the box has the UI focus, as of the client's last tick
	std::atomic<bool> boxClicked{false};  // the last left click while the panel was open was on the box
	std::atomic<long> textsSet{0}, textFails{0}, keysHeld{0}, keysTaken{0}, wheels{0};
};

// Once per plugin (idempotent): the addresses, the entry-byte check of the typing functions and the UI message listener. False when a loader
// service is missing; the panels then stay off.
auto Init(const D2RL::PluginContext* context) noexcept -> bool;

// True when D2R's focus test and "input handled" functions have the expected entry bytes: only then is the game window subclassed and typing fixed.
auto TypingOk() noexcept -> bool;

// The game draws HD graphics now.
auto IsHd() noexcept -> bool;

// Adds a panel (at most MaxClients). The pointer must stay valid.
inline constexpr int MaxClients = 4;
auto AddClient(Client* client) noexcept -> bool;

// Registers `json` as data/global/ui/layouts/mxl2012-core/<file>.json (`file` is "DevMenuhd", "DevMenu", ...). The bytes must stay valid.
auto RegisterLayout(const D2RL::PluginContext* context, const char* file, const char* json, size_t size) noexcept -> bool;

// Registers the empty panels <localPrefix>0 .. <localPrefix><count - 1> ("DevMenuB_"): D2R hands a button's PanelManager message to UI
// listeners only when it names a known panel. Returns -1, or the index that could not be registered.
auto RegisterButtons(const D2RL::PluginContext* context, const char* localPrefix, int count) noexcept -> int;

// The panel's native widget (null while it is not loaded), and a child of it by name.
auto NativePanel(const Client& client) noexcept -> void*;
auto NativeChild(void* panel, const char* name) noexcept -> void*;

// Sets the TextBoxWidget `name` of `panel` to `want` through D2R's own setter when it differs from `shown` (what the box holds) or `force`
// is set (a new panel or graphics mode: every line is sent again).
void SetLine(Client& client, void* panel, const char* name, std::string& shown, const std::string& want, bool force);

// Subclasses the game window, once, the first time a panel is open (typing and the wheel need the window's own messages).
void HookGameWindow() noexcept;

// Where the left button last went down or up in the game window (client pixels) and the client area's size then. False before the first
// click. A panel whose buttons all send one message finds the button from this (D2R allows a plugin 64 registered panel names, and one
// name per button does not fit a panel with many buttons).
auto LastClick(int* x, int* y, int* clientW, int* clientH) noexcept -> bool;

// The panel's box has D2R's UI focus.
auto BoxFocused(const Client& client) noexcept -> bool;

// A file of the active mod's folder MPQ, read whole: <plugin folder>\..\..\<mod>.mpq\<relative>. `selfPath` is this DLL's path (UTF-8).
enum class FileResult : unsigned char { Ok, NoPath, NotFound, BadSize, ReadFailed };
auto ReadModFile(const D2RL::PluginContext* context, const char* selfPath, const wchar_t* relative, size_t maxBytes, std::string* out) -> FileResult;

}  // namespace panel_shared
