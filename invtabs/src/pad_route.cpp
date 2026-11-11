// invtabs: the controller tab's registration with D2RLoader (panel, layout, grid binding, controller route). See pad_route.h.

#include "pad_route.h"

#include <cstdarg>
#include <cstdio>
#include <cstring>
#include <string>

namespace invtabs::pad {
namespace {

namespace Panels    = D2RL::Panels;
namespace Resources = D2RL::Resources;

void Say(const Hooks& hooks, bool warn, const char* format, ...) noexcept {
	if (!hooks.log) return;
	char    line[512] {};
	va_list args;
	va_start(args, format);
	std::vsnprintf(line, sizeof(line), format, args);
	va_end(args);
	hooks.log(warn, line);
}

Resources::RegistrationHandle AddResource(const D2RL::PluginContext* context, const D2RL::ResourceService* resources, const std::string& path,
                                          const std::string& bytes) noexcept {
	const Resources::ResourceRegistration registration {
		.structSize = Resources::ResourceRegistrationSize,
		.flags      = 0,
		.path       = path.c_str(),
		.bytes      = bytes.data(),
		.byteCount  = bytes.size(),
	};
	Resources::RegistrationHandle handle = Resources::InvalidHandle;
	if (resources->registerResource(context, &registration, &handle) != Resources::Result::Success) return Resources::InvalidHandle;
	return handle;
}

std::string JsonText(const char* text) {
	std::string out = "\"";
	for (const char* c = text; *c; ++c) {
		if (*c == '"' || *c == '\\') out += '\\';
		if (static_cast<unsigned char>(*c) >= 0x20) out += *c;
	}
	return out + '"';
}

} // namespace

std::string StringsJson(const char* labelKey, const char* labelText) {
	// "@invtabs:PadRouteLabel" -> key "PadRouteLabel" (the file's namespace is the plugin's)
	const char* colon = std::strchr(labelKey, ':');
	const char* key   = colon ? colon + 1 : labelKey + (labelKey[0] == '@' ? 1 : 0);
	return "[{\"Key\":" + JsonText(key) + ",\"enUS\":" + JsonText(labelText) + "}]";
}

Status Register(const D2RL::PluginContext* context, const D2RL::PanelService* panels, const D2RL::ResourceService* resources,
                D2RL::Inventory::PageRegistrationHandle page, const Options& options, const Hooks& hooks, Handles* out) noexcept {
	if (!out || !ValidSpec(options.cols, options.rows, options.slot) || !options.labelKey || options.labelKey[0] != '@') {
		Say(hooks, true, "invtabs: pad tab: bad options (%d x %d, slot %d)", options.cols, options.rows, options.slot);
		return Status::BadOptions;
	}
	*out = Handles {};
	if (!context || !D2RL::HasPanelServiceField(panels, D2RL::PanelServiceUnregisterControllerRouteFieldEnd)
	    || !D2RL::HasResourceServiceField(resources, D2RL::ResourceServiceRequiredSize)) {
		Say(hooks, true, "invtabs: pad tab: D2RLoader has no controller routes (panel service too old): no gamepad tab");
		return Status::NoService;
	}
	try {
		if (hooks.registerSprite) {
			const std::string name = BackgroundName(options.cols, options.rows);
			if (!hooks.registerSprite(name.c_str(), PanelW, PanelH, Background(options.cols, options.rows).data()))
				Say(hooks, true, "invtabs: pad tab: art %s not registered (the panel shows without it)", name.c_str());
		}
		if (options.labelText) {
			const std::string path = std::string("data/local/lng/strings/d2rloader/") + Plugin + "/pad.json";
			out->strings           = AddResource(context, resources, path, StringsJson(options.labelKey, options.labelText));
			if (out->strings == Resources::InvalidHandle) Say(hooks, true, "invtabs: pad tab: %s not registered (the menu label may show the key)", path.c_str());
		}
		const std::string path = LayoutPath(options.slot);
		out->layout            = AddResource(context, resources, path, LayoutJson(options.cols, options.rows, options.slot, options.summary ? options.summary : ""));
		if (out->layout == Resources::InvalidHandle) {
			Say(hooks, true, "invtabs: pad tab: layout %s not registered", path.c_str());
			Unregister(context, panels, resources, out);
			return Status::LayoutRefused;
		}
		const std::string                localId = LocalId(options.slot);
		const Panels::PanelRegistration registration {
			.structSize = Panels::PanelRegistrationSize,
			.flags      = Panels::PanelFlags::CloseOnEscape | Panels::PanelFlags::GameplayLeftSlot,
			.localId    = localId.c_str(),
		};
		if (const auto r = panels->registerPanel(context, &registration, &out->panel); r != Panels::Result::Success) {
			Say(hooks, true, "invtabs: pad tab: panel %s refused (result %u)", localId.c_str(), static_cast<unsigned>(r));
			out->panel = Panels::InvalidHandle;
			Unregister(context, panels, resources, out);
			return Status::PanelRefused;
		}
		const Panels::PlayerPageGridBinding binding {
			.structSize = Panels::PlayerPageGridBindingSize,
			.flags      = 0,
			.panel      = out->panel,
			.page       = page,
			.childName  = "invtabs/Grid",
		};
		if (const auto r = panels->bindPlayerPageGrid(context, &binding); r != Panels::Result::Success) {
			Say(hooks, true, "invtabs: pad tab: grid binding of %s refused (result %u)", localId.c_str(), static_cast<unsigned>(r));
			Unregister(context, panels, resources, out);
			return Status::PanelRefused;
		}
		const Panels::ControllerRouteRegistration route {
			.structSize        = Panels::ControllerRouteRegistrationSize,
			.flags             = Panels::ControllerRouteFlags::PairWithPlayerInventory,
			.panel             = out->panel,
			.placement         = Panels::ControllerRoutePlacement::AfterPlayerInventory,
			.reserved          = 0,
			.localizedLabelKey = options.labelKey,
		};
		if (const auto r = panels->registerControllerRoute(context, &route, &out->route); r != Panels::Result::Success) {
			Say(hooks, true, "invtabs: pad tab: controller route refused (result %u%s): no gamepad charm tab", static_cast<unsigned>(r),
			    r == Panels::Result::Conflict ? ", another plugin holds the only route (CharmInv?)" : "");
			out->route = Panels::InvalidControllerRouteHandle;
			Unregister(context, panels, resources, out);
			return Status::RouteTaken;
		}
		Say(hooks, false, "invtabs: pad tab: menu entry %s after Inventory, %s, grid %d x %d at scale %s", options.labelKey, PanelName(options.slot).c_str(),
		    options.cols, options.rows, ScaleText(Layout(options.cols, options.rows).scaleMilli).c_str());
		return Status::Ok;
	} catch (...) { // std::bad_alloc from the strings / art
		Say(hooks, true, "invtabs: pad tab: out of memory");
		Unregister(context, panels, resources, out);
		return Status::LayoutRefused;
	}
}

void Unregister(const D2RL::PluginContext* context, const D2RL::PanelService* panels, const D2RL::ResourceService* resources, Handles* handles) noexcept {
	if (!handles) return;
	if (panels && handles->route != Panels::InvalidControllerRouteHandle) (void)panels->unregisterControllerRoute(context, handles->route);
	if (panels && handles->panel != Panels::InvalidHandle) (void)panels->unregisterPanel(context, handles->panel);
	if (resources && handles->layout != Resources::InvalidHandle) (void)resources->unregisterResource(context, handles->layout);
	if (resources && handles->strings != Resources::InvalidHandle) (void)resources->unregisterResource(context, handles->strings);
	*handles = Handles {};
}

} // namespace invtabs::pad
