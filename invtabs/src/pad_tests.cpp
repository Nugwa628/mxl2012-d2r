// invtabs pad tab: the layout against tools/invtabs_pad.py (pad_golden.inc) and the registration against fake services.
// Exit code 0 when every check passes. Build: an executable from this file and pad_route.cpp (D2RLPlugin include path).

#include <cstdio>
#include <string>
#include <vector>

#include "pad_layout.h"
#include "pad_route.h"

#include "pad_golden.inc"

namespace {

namespace Panels    = D2RL::Panels;
namespace Resources = D2RL::Resources;
using namespace invtabs::pad;

int Failures = 0;

void Check(bool ok, const char* what, const std::string& detail = {}) {
	if (ok) return;
	++Failures;
	std::printf("FAIL %s %s\n", what, detail.c_str());
}

// ---- fake D2RLoader services: record what the module registers ----

struct Fake {
	std::vector<std::string>          resources;   // registered paths, in order
	std::vector<std::string>          bodies;
	int                               liveResources = 0, panelsLive = 0, routesLive = 0, sprites = 0;
	std::string                       panelId, boundChild, routeLabel;
	Panels::ControllerRouteFlags      routeFlags {};
	Panels::ControllerRoutePlacement  routePlacement {};
	Panels::Result                    routeResult = Panels::Result::Success;
	D2RL::Inventory::PageRegistrationHandle boundPage = 0;
} F;

Resources::Result __cdecl RegisterResource(const D2RL::PluginContext*, const Resources::ResourceRegistration* r, Resources::RegistrationHandle* h) noexcept {
	F.resources.emplace_back(r->path);
	F.bodies.emplace_back(static_cast<const char*>(r->bytes), static_cast<std::size_t>(r->byteCount));
	++F.liveResources;
	*h = F.resources.size();
	return Resources::Result::Success;
}
Resources::Result __cdecl UnregisterResource(const D2RL::PluginContext*, Resources::RegistrationHandle) noexcept {
	--F.liveResources;
	return Resources::Result::Success;
}
Panels::Result __cdecl RegisterPanel(const D2RL::PluginContext*, const Panels::PanelRegistration* r, Panels::RegistrationHandle* h) noexcept {
	F.panelId = r->localId;
	++F.panelsLive;
	*h = 77;
	return Panels::Result::Success;
}
Panels::Result __cdecl UnregisterPanel(const D2RL::PluginContext*, Panels::RegistrationHandle) noexcept {
	--F.panelsLive;
	return Panels::Result::Success;
}
Panels::Result __cdecl BindGrid(const D2RL::PluginContext*, const Panels::PlayerPageGridBinding* b) noexcept {
	F.boundChild = b->childName;
	F.boundPage  = b->page;
	return b->panel == 77 ? Panels::Result::Success : Panels::Result::NotFound;
}
Panels::Result __cdecl RegisterRoute(const D2RL::PluginContext*, const Panels::ControllerRouteRegistration* r, Panels::ControllerRouteHandle* h) noexcept {
	if (F.routeResult != Panels::Result::Success) return F.routeResult;
	F.routeLabel     = r->localizedLabelKey;
	F.routeFlags     = r->flags;
	F.routePlacement = r->placement;
	++F.routesLive;
	*h = 5;
	return r->structSize == Panels::ControllerRouteRegistrationSize && r->panel == 77 && r->reserved == 0 ? Panels::Result::Success : Panels::Result::InvalidArgument;
}
Panels::Result __cdecl UnregisterRoute(const D2RL::PluginContext*, Panels::ControllerRouteHandle) noexcept {
	--F.routesLive;
	return Panels::Result::Success;
}
bool Sprite(const char* name, int w, int h, const std::uint8_t* rgba) noexcept {
	++F.sprites;
	return std::string(name) == "pad_10x6" && w == PanelW && h == PanelH && rgba && rgba[3] == 255;
}

D2RL::PanelService PanelFake() {
	D2RL::PanelService s {};
	s.serviceSize = D2RL::PanelServiceSize, s.serviceVersion = D2RL::PanelService::AbiVersion;
	s.registerPanel = RegisterPanel, s.unregisterPanel = UnregisterPanel, s.bindPlayerPageGrid = BindGrid;
	s.registerControllerRoute = RegisterRoute, s.unregisterControllerRoute = UnregisterRoute;
	return s;
}

D2RL::ResourceService ResourceFake() {
	D2RL::ResourceService s {};
	s.serviceSize = D2RL::ResourceServiceSize, s.serviceVersion = D2RL::ResourceService::AbiVersion;
	s.registerResource = RegisterResource, s.unregisterResource = UnregisterResource;
	return s;
}

void Golden() {
	for (const auto& g : kPadGolden) {
		const std::string made = LayoutJson(g.cols, g.rows, g.slot);
		Check(made == g.json, "golden layout", std::to_string(g.cols) + "x" + std::to_string(g.rows) + " slot " + std::to_string(g.slot) + ":\n  " + made + "\n  " + g.json);
	}
}

void GeometryChecks() {
	for (int c = 1; c <= MaxCells; ++c)
		for (int r = 1; r <= MaxCells; ++r) {
			const auto g = Layout(c, r);
			Check(g.summary.h >= SummaryMin && g.summary.y + g.summary.h + Gap == g.grid.y && g.grid.y + g.grid.h == GridBottom, "summary above grid",
			      std::to_string(c) + "x" + std::to_string(r));
			Check(g.grid.x >= Margin && g.grid.x + g.grid.w <= PanelW - Margin && g.scaleMilli <= 1000, "grid inside the panel", std::to_string(c) + "x" + std::to_string(r));
		}
	Check(Layout(10, 6).scaleMilli == 1000 && Layout(10, 6).grid.x == 163 && Layout(10, 6).grid.y == 783, "10x6 at full size, x 163");
	Check(Layout(16, 16).scaleMilli == 663, "16x16 scale", std::to_string(Layout(16, 16).scaleMilli));
	Check(ScaleText(663) == "0.663" && ScaleText(700) == "0.7" && ScaleText(50) == "0.05", "scale text");
	Check(!ValidSpec(0, 6, 0) && !ValidSpec(17, 6, 0) && !ValidSpec(10, 6, 64) && ValidSpec(16, 16, 63), "spec bounds");
	Check(Background(10, 6).size() == static_cast<std::size_t>(PanelW) * PanelH * 4, "art size");
}

void Registration() {
	const auto  panels = PanelFake();
	const auto  res    = ResourceFake();
	const int   token  = 0;
	const auto* ctx    = reinterpret_cast<const D2RL::PluginContext*>(&token);
	Handles     h;
	Options     o;
	Hooks       hooks;
	hooks.registerSprite = Sprite;
	Check(Register(ctx, &panels, &res, 42, o, hooks, &h) == Status::Ok, "register ok");
	Check(F.panelId == "Pad0" && F.boundChild == "invtabs/Grid" && F.boundPage == 42, "panel Pad0 bound to the page", F.panelId + " " + F.boundChild);
	Check(F.routeLabel == "@invtabs:PadRouteLabel" && F.routeFlags == Panels::ControllerRouteFlags::PairWithPlayerInventory
	          && F.routePlacement == Panels::ControllerRoutePlacement::AfterPlayerInventory,
	      "route after the inventory, paired");
	Check(F.sprites == 1, "art registered once");
	Check(F.resources.size() == 2 && F.resources[0] == "data/local/lng/strings/d2rloader/invtabs/pad.json" && F.resources[1] == "data/global/ui/layouts/invtabs/Pad0hd.json",
	      "resources", F.resources.empty() ? "" : F.resources.back());
	Check(F.bodies.size() == 2 && F.bodies[0] == R"([{"Key":"PadRouteLabel","enUS":"Charm Inventory"}])" && F.bodies[1] == LayoutJson(10, 6, 0), "resource bodies");
	Unregister(ctx, &panels, &res, &h);
	Check(F.liveResources == 0 && F.panelsLive == 0 && F.routesLive == 0, "unregister withdraws everything");

	F.routeResult = Panels::Result::Conflict; // CharmInv holds the route
	Check(Register(ctx, &panels, &res, 42, o, {}, &h) == Status::RouteTaken, "route taken");
	Check(F.liveResources == 0 && F.panelsLive == 0 && h.panel == Panels::InvalidHandle, "route taken: nothing left behind");
	F.routeResult = Panels::Result::Success;

	o.cols = 17;
	Check(Register(ctx, &panels, &res, 42, o, {}, &h) == Status::BadOptions, "bad size refused");
	o.cols = 10;
	auto old = panels;
	old.serviceSize = D2RL::PanelServiceUnregisterChildLayoutFieldEnd; // an SDK without routes
	Check(Register(ctx, &old, &res, 42, o, {}, &h) == Status::NoService, "old panel service");
}

} // namespace

int main() {
	Golden();
	GeometryChecks();
	Registration();
	std::printf("pad_tests: %s (%d failure(s))\n", Failures ? "FAIL" : "OK", Failures);
	return Failures ? 1 : 0;
}
