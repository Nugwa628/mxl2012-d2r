// The shared parts of the plugin's native panels (panel_shared.h). Moved here from devmenu.cpp when the wiki panel became the second panel;
// the developer menu behaves as before.
#include "panel_shared.h"

#include "panel_logic.h"
#include "rotw_stash_logic.h"

#include <D2RLPlugin/panels.h>
#include <D2RLPlugin/resources.h>
#include <D2RLPlugin/shared_events.h>

#include <windows.h>

#include <cstdint>
#include <cstdio>
#include <cstring>

namespace panel_shared {
namespace {

using namespace panel_logic;

// game functions and data (image 0x6ab3782c; the plugin's image check guards all of them; docs/d2r-addresses.md "Setting a native text box",
// "Text boxes and key bindings")
constexpr uint64_t RvaUiRoot = 0x3440170;         // data: the root widget
constexpr uint64_t RvaUiFindPanel = 0x89f760;     // (root, char name[128]) -> panel widget
constexpr uint64_t RvaUiFindChild = 0x855c90;     // (widget, name) -> child widget, searching below it
constexpr uint64_t RvaTextBoxSetText = 0x86dd50;  // (TextBoxWidget, const string view*)
constexpr uint64_t RvaHasUiFocus = 0x876160;      // (widget) -> the UI root's focus is this widget
constexpr uint64_t RvaMarkHandled = 0x843fc0;     // (): the UI handled this input (root byte +0xb8): the key binding does not run
constexpr unsigned char HasUiFocusEntry[] = {0x40, 0x53, 0x48, 0x83, 0xec, 0x20, 0x48, 0x8b, 0xd9, 0xe8};
constexpr unsigned char MarkHandledEntry[] = {0x48, 0x8b, 0x05, 0xa9, 0xc1, 0xbf, 0x02, 0x48, 0x85, 0xc0, 0x74, 0x07, 0xc6, 0x80, 0xb8, 0x00};

struct NativeStringView {
	const char* data;
	size_t size;
};
using NativeFindPanelFn = void* (*)(void* root, const char* name128);
using NativeFindChildFn = void* (*)(void* parent, const char* name);
using NativeSetTextFn = void (*)(void* widget, const NativeStringView* text);
using HasUiFocusFn = bool (*)(void* widget);
using MarkHandledFn = void (*)();
using HdFn = bool (*)() noexcept;

const D2RL::PluginContext* g_context = nullptr;
const D2RL::PanelService* g_panels = nullptr;
const D2RL::ResourceService* g_resources = nullptr;
uint64_t g_base = 0;
bool g_ready = false;
bool g_typingOk = false;  // the functions' entry bytes matched at Init
Client* g_clients[MaxClients] = {};
std::atomic<int> g_clientCount{0};

template <class F>
auto Fn(uint64_t rva) noexcept -> F {
	return reinterpret_cast<F>(g_base + rva);
}

// --- typing into a panel's text box ----------------------------------------------------------------------------------------------------------
// How D2R routes a key (docs/d2r-addresses.md "Text boxes and key bindings"): WM_KEYDOWN becomes InputMessage:KeyDown for the UI; a key with a
// binding then becomes InputMessage:BindingDown and runs its command unless a UI handler marked the input as handled (`0x843fc0`, root byte
// +0xb8); the key's WM_CHAR becomes InputMessage:CharacterTyped, which the focused text box takes, only for a key without a binding. Nothing
// marks a bound key while a layout text box has the focus (the game's own "edited box" belongs to the controller's TextInputModal), so in 0.1.18
// a bound key ("A", the digits) ran its command and never reached the box.
//
// While a panel is open and its box has the UI focus (a click on the box), two things, both scoped to that state:
// - a printable key without Ctrl or Alt (letters, digits, space, punctuation, numpad digits) reaches D2R as an unbound key (`StandInKey`, F24):
//   the subclass of the game's own window (not a system hook) changes the key of its WM_KEYDOWN / WM_KEYUP, so no binding matches, D2R takes the
//   press as an unbound key and its WM_CHAR types (D2R types a character only after a key press that matched no binding, so holding the
//   press back loses all but the first character);
// - an editing key (Backspace, Enter, arrows, Home, End, Delete) still goes to D2R, so the box edits with it, and the UI listener marks its
//   BindingDown / BindingUp as handled (Enter would otherwise open the chat line).
// Esc and keys with Ctrl or Alt (Ctrl+F12) are untouched: Esc closes the panel, its hotkey toggles it. "Has the keyboard" follows the player's
// last left click while the panel is open: on the box (`OnBox`, from the click's own window message) it does, anywhere else (a button, the
// rows, the game) it does not, and the keys are the game's as before. D2R keeps the UI focus on the box after such clicks, so the focus alone
// cannot say.
HWND g_window = nullptr;  // the subclassed game window
WNDPROC g_gameProc = nullptr;
std::atomic<bool> g_ctrl{false}, g_alt{false};  // as the window's own key messages say (posted test keys included)
std::atomic<unsigned> g_lastKey{0};              // the virtual key of the last key down
unsigned g_takenKey = 0;                         // a key down a panel took (`onKey`): its key up is not D2R's either
std::atomic<int> g_clickX{0}, g_clickY{0}, g_clickW{0}, g_clickH{0};  // the last left button down or up (LastClick)

auto Typing(const Client& c) noexcept -> bool {
	return c.open.load() && c.boxClicked.load() && c.boxFocus.load() && !g_ctrl.load() && !g_alt.load();
}

void NotePointer(HWND window, LPARAM lParam) noexcept {
	RECT r{};
	GetClientRect(window, &r);
	g_clickX.store(static_cast<int>(static_cast<short>(LOWORD(lParam))));
	g_clickY.store(static_cast<int>(static_cast<short>(HIWORD(lParam))));
	g_clickW.store(r.right - r.left);
	g_clickH.store(r.bottom - r.top);
}

void NoteClick(HWND window, LPARAM lParam) noexcept {
	NotePointer(window, lParam);
	const int count = g_clientCount.load();
	for (int i = 0; i < count; ++i) {
		Client& c = *g_clients[i];
		if (!c.open.load() || c.inputBox == nullptr) {
			continue;
		}
		RECT r{};
		GetClientRect(window, &r);
		BoxRect b;
		const bool on = c.inputBox(&b) && OnBox(b.hd, r.right - r.left, r.bottom - r.top, b.panelX, b.panelY, b.x, b.y, b.w, b.h,
		                                        static_cast<int>(static_cast<short>(LOWORD(lParam))), static_cast<int>(static_cast<short>(HIWORD(lParam))));
		c.boxClicked.store(on);
	}
}

LRESULT CALLBACK PanelWindowProc(HWND window, UINT message, WPARAM wParam, LPARAM lParam) {
	const int count = g_clientCount.load();
	if (message == WM_KEYDOWN || message == WM_KEYUP || message == WM_SYSKEYDOWN || message == WM_SYSKEYUP) {
		const auto key = static_cast<unsigned>(wParam);
		const bool down = message == WM_KEYDOWN || message == WM_SYSKEYDOWN;
		if (key == VK_CONTROL || key == VK_LCONTROL || key == VK_RCONTROL) {
			g_ctrl.store(down);
		} else if (key == VK_MENU || key == VK_LMENU || key == VK_RMENU) {
			g_alt.store(down);
		}
		if (down) {
			g_lastKey.store(key);
		}
		if (message == WM_KEYDOWN || message == WM_KEYUP) {
			if (TypedKey(key)) {
				for (int i = 0; i < count; ++i) {
					if (Typing(*g_clients[i])) {
						g_clients[i]->keysHeld.fetch_add(1);
						return CallWindowProcW(g_gameProc, window, message, StandInKey, lParam);
					}
				}
			}
			if (!down && key == g_takenKey && key != 0) {
				g_takenKey = 0;
				return 0;
			}
			if (down && !g_ctrl.load() && !g_alt.load()) {
				for (int i = 0; i < count; ++i) {
					Client& c = *g_clients[i];
					if (c.open.load() && c.onKey != nullptr && !Typing(c) && c.onKey(key)) {
						g_takenKey = key;
						return 0;
					}
				}
			}
		}
	} else if (message == WM_LBUTTONDOWN) {
		NoteClick(window, lParam);
	} else if (message == WM_LBUTTONUP) {
		NotePointer(window, lParam);
	} else if (message == WM_MOUSEWHEEL) {
		POINT p{static_cast<int>(static_cast<short>(LOWORD(lParam))), static_cast<int>(static_cast<short>(HIWORD(lParam)))};  // screen
		RECT r{};
		if (ScreenToClient(window, &p) && GetClientRect(window, &r)) {
			const int notches = static_cast<int>(static_cast<short>(HIWORD(wParam))) / WHEEL_DELTA;
			for (int i = 0; i < count; ++i) {
				Client& c = *g_clients[i];
				if (c.open.load() && c.onWheel != nullptr && notches != 0 && c.onWheel(notches, p.x, p.y, r.right - r.left, r.bottom - r.top)) {
					c.wheels.fetch_add(1);
					return 0;
				}
			}
		}
	} else if (message == WM_KILLFOCUS || message == WM_ACTIVATEAPP) {
		g_ctrl.store(false);
		g_alt.store(false);
	}
	return CallWindowProcW(g_gameProc, window, message, wParam, lParam);
}

auto CALLBACK PickGameWindow(HWND window, LPARAM out) -> BOOL {
	RECT r{};
	if (GetWindow(window, GW_OWNER) == nullptr && GetClientRect(window, &r) && r.right > 320 && r.bottom > 200) {
		*reinterpret_cast<HWND*>(out) = window;
		return FALSE;
	}
	return TRUE;
}

// UI listener: true when this binding message belongs to an editing key of a panel's focused box.
auto TakeBindingForBox(const char* target, const char* command) noexcept -> bool {
	if (target == nullptr || command == nullptr || std::strcmp(target, "InputMessage") != 0 ||
	    (std::strcmp(command, "BindingDown") != 0 && std::strcmp(command, "BindingUp") != 0) || !EditingKey(g_lastKey.load())) {
		return false;
	}
	const int count = g_clientCount.load();
	for (int i = 0; i < count; ++i) {
		Client& c = *g_clients[i];
		if (Typing(c) && BoxFocused(c)) {
			Fn<MarkHandledFn>(RvaMarkHandled)();
			c.keysTaken.fetch_add(1);
			return true;
		}
	}
	return false;
}

auto __cdecl OnUiMessage(const D2RL::PluginContext*, const D2RL::SharedEvents::UiMessageEvent* event, void*) noexcept -> D2RL::SharedEvents::UiMessageAction {
	if (event != nullptr && TakeBindingForBox(event->target, event->command)) {
		return D2RL::SharedEvents::UiMessageAction::Consume;
	}
	if (event == nullptr || event->target == nullptr || event->command == nullptr || event->text == nullptr || std::strcmp(event->target, "PanelManager") != 0 ||
	    std::strcmp(event->command, "OpenPanel") != 0) {
		return D2RL::SharedEvents::UiMessageAction::Continue;
	}
	const int count = g_clientCount.load();
	for (int i = 0; i < count; ++i) {
		Client& c = *g_clients[i];
		const size_t n = std::strlen(c.buttonPrefix);
		if (n == 0 || std::strncmp(event->text, c.buttonPrefix, n) != 0) {
			continue;
		}
		const int button = std::atoi(event->text + n);
		if (button >= 0 && button < c.buttonCount && c.onPress != nullptr) {
			c.onPress(button);
		}
		return D2RL::SharedEvents::UiMessageAction::Consume;
	}
	return D2RL::SharedEvents::UiMessageAction::Continue;
}

}  // namespace

auto Init(const D2RL::PluginContext* context) noexcept -> bool {
	if (g_ready) {
		return true;
	}
	g_context = context;
	g_base = context->exeBase;
	g_typingOk = std::memcmp(reinterpret_cast<const void*>(g_base + RvaHasUiFocus), HasUiFocusEntry, sizeof(HasUiFocusEntry)) == 0 &&
	             std::memcmp(reinterpret_cast<const void*>(g_base + RvaMarkHandled), MarkHandledEntry, sizeof(MarkHandledEntry)) == 0;
	const D2RL::SharedEventService* events = nullptr;
	if (context->QueryService(&g_panels) != D2RL::ServiceQueryResult::Success || !D2RL::HasPanelServiceField(g_panels, D2RL::PanelServiceRequiredSize) ||
	    context->QueryService(&events) != D2RL::ServiceQueryResult::Success || !D2RL::HasSharedEventServiceField(events, D2RL::SharedEventServiceRequiredSize) ||
	    context->QueryService(&g_resources) != D2RL::ServiceQueryResult::Success) {
		return false;
	}
	D2RL::SharedEvents::UiMessageListener listener{};
	listener.structSize = D2RL::SharedEvents::UiMessageListenerSize;
	listener.callback = &OnUiMessage;
	D2RL::SharedEvents::ListenerHandle handle = 0;
	if (events->registerUiMessageListener(context, &listener, &handle) != D2RL::SharedEvents::Result::Success) {
		return false;
	}
	g_ready = true;
	return true;
}

auto TypingOk() noexcept -> bool {
	return g_typingOk;
}

auto IsHd() noexcept -> bool {
	return g_base == 0 || reinterpret_cast<HdFn>(g_base + rotw_stash::HdModeRva)();
}

auto AddClient(Client* client) noexcept -> bool {
	const int count = g_clientCount.load();
	if (client == nullptr || count >= MaxClients) {
		return false;
	}
	g_clients[count] = client;
	g_clientCount.store(count + 1);
	return true;
}

auto RegisterLayout(const D2RL::PluginContext* context, const char* file, const char* json, size_t size) noexcept -> bool {
	char path[96];
	std::snprintf(path, sizeof(path), "data/global/ui/layouts/mxl2012-core/%s.json", file);
	D2RL::Resources::ResourceRegistration resource{};
	resource.structSize = D2RL::Resources::ResourceRegistrationSize;
	resource.path = path;
	resource.bytes = json;
	resource.byteCount = size;
	D2RL::Resources::RegistrationHandle handle = D2RL::Resources::InvalidHandle;
	return g_resources != nullptr && g_resources->registerResource(context, &resource, &handle) == D2RL::Resources::Result::Success;
}

auto RegisterButtons(const D2RL::PluginContext* context, const char* localPrefix, int count) noexcept -> int {
	for (int i = 0; i < count; ++i) {
		char local[48];
		std::snprintf(local, sizeof(local), "%s%d", localPrefix, i);
		D2RL::Panels::PanelRegistration button{};
		button.structSize = D2RL::Panels::PanelRegistrationSize;
		button.flags = D2RL::Panels::PanelFlags::None;
		button.localId = local;
		D2RL::Panels::RegistrationHandle h = 0;
		if (g_panels == nullptr || g_panels->registerPanel(context, &button, &h) != D2RL::Panels::Result::Success) {
			return i;
		}
	}
	return -1;
}

auto NativePanel(const Client& client) noexcept -> void* {
	void* root = *reinterpret_cast<void**>(g_base + RvaUiRoot);
	if (root == nullptr) {
		return nullptr;
	}
	char name[128] = {};
	std::strncpy(name, client.panelName, sizeof(name) - 1);
	return Fn<NativeFindPanelFn>(RvaUiFindPanel)(root, name);
}

auto NativeChild(void* panel, const char* name) noexcept -> void* {
	return panel != nullptr ? Fn<NativeFindChildFn>(RvaUiFindChild)(panel, name) : nullptr;
}

void SetLine(Client& client, void* panel, const char* name, std::string& shown, const std::string& want, bool force) {
	if (!force && shown == want) {
		return;
	}
	void* widget = Fn<NativeFindChildFn>(RvaUiFindChild)(panel, name);
	if (widget == nullptr) {
		client.textFails.fetch_add(1);
		return;
	}
	const NativeStringView view{want.c_str(), want.size()};
	Fn<NativeSetTextFn>(RvaTextBoxSetText)(widget, &view);
	shown = want;
	client.textsSet.fetch_add(1);
}

void HookGameWindow() noexcept {
	if (g_window != nullptr || !g_typingOk) {
		return;
	}
	HWND found = nullptr;
	EnumThreadWindows(GetCurrentThreadId(), &PickGameWindow, reinterpret_cast<LPARAM>(&found));
	if (found == nullptr) {
		return;
	}
	const auto previous = reinterpret_cast<WNDPROC>(SetWindowLongPtrW(found, GWLP_WNDPROC, reinterpret_cast<LONG_PTR>(&PanelWindowProc)));
	if (previous != nullptr) {
		g_gameProc = previous;
		g_window = found;
		if (g_context != nullptr) {
			g_context->LogInfo("panels: the game window is subclassed (typing, wheel)");
		}
	}
}

auto LastClick(int* x, int* y, int* clientW, int* clientH) noexcept -> bool {
	*x = g_clickX.load();
	*y = g_clickY.load();
	*clientW = g_clickW.load();
	*clientH = g_clickH.load();
	return *clientW > 0 && *clientH > 0;
}

auto BoxFocused(const Client& client) noexcept -> bool {
	if (!g_typingOk || client.inputName == nullptr) {
		return false;
	}
	void* panel = NativePanel(client);
	void* box = panel != nullptr ? Fn<NativeFindChildFn>(RvaUiFindChild)(panel, client.inputName) : nullptr;
	return box != nullptr && Fn<HasUiFocusFn>(RvaHasUiFocus)(box);
}

auto ReadModFile(const D2RL::PluginContext* context, const char* selfPath, const wchar_t* relative, size_t maxBytes, std::string* out) -> FileResult {
	const char* mod = context->activeMod != nullptr && context->activeMod[0] != '\0' ? context->activeMod : "mxl2012";
	wchar_t wide[1024];
	if (MultiByteToWideChar(CP_UTF8, 0, selfPath, -1, wide, 1024) == 0) {
		return FileResult::NoPath;
	}
	std::wstring path = wide;
	const size_t slash = path.find_last_of(L"\\/");
	path = path.substr(0, slash == std::wstring::npos ? 0 : slash);
	wchar_t modw[128];
	(void)MultiByteToWideChar(CP_UTF8, 0, mod, -1, modw, 128);
	path += L"\\..\\..\\";
	path += modw;
	path += L".mpq\\";
	path += relative;
	HANDLE file = CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
	if (file == INVALID_HANDLE_VALUE) {
		return FileResult::NotFound;
	}
	LARGE_INTEGER size{};
	GetFileSizeEx(file, &size);
	if (size.QuadPart <= 0 || static_cast<unsigned long long>(size.QuadPart) > maxBytes) {
		CloseHandle(file);
		return FileResult::BadSize;
	}
	std::string text(static_cast<size_t>(size.QuadPart), '\0');
	DWORD read = 0;
	const BOOL ok = ReadFile(file, text.data(), static_cast<DWORD>(text.size()), &read, nullptr);
	CloseHandle(file);
	if (!ok || read != text.size()) {
		return FileResult::ReadFailed;
	}
	*out = std::move(text);
	return FileResult::Ok;
}

}  // namespace panel_shared
