// The wrong-build notice (build_guard_logic.h): on a D2R other than build 93847 the plugin installs no hook and draws one
// line at the top of the screen through D2RLoader's overlay service, which needs no game address. The environment
// warning (env_guard_logic.h, docs/bugs.md #53) uses the same line.
#include "build_guard.h"

#include <D2RLPlugin/overlay.h>

#include <atomic>
#include <cstring>

namespace {

const D2RL::OverlayService* g_overlay = nullptr;
bool g_registered = false;
char g_notices[2][256] = {"", ""};  // the drawn one and the next: a later notice never changes the text being drawn
std::atomic<int> g_current{0};

void __cdecl DrawNotice(const D2RL::PluginContext* context, const D2RL::Overlay::Frame* frame, void*) noexcept {
	const char* notice = g_notices[g_current.load()];
	if (g_overlay == nullptr || frame == nullptr || notice[0] == '\0') {
		return;
	}
	const auto length = static_cast<uint32_t>(std::strlen(notice));
	const float size = frame->defaultTextSize * 1.2F;
	D2RL::Overlay::MeasureTextRequest measure{};
	measure.structSize = D2RL::Overlay::MeasureTextRequestSize;
	measure.canvas = frame->canvas;
	measure.textSize = size;
	measure.text = notice;
	measure.textLength = length;
	D2RL::Overlay::TextMetrics metrics{};
	metrics.structSize = D2RL::Overlay::TextMetricsSize;
	const float width = g_overlay->measureText(context, &measure, &metrics) == D2RL::Overlay::Result::Success ? metrics.width : 0.0F;
	const float x = (frame->screenWidth - width) / 2.0F;
	const float y = frame->screenHeight * 0.04F;
	D2RL::Overlay::FilledRectangleRequest back{};
	back.structSize = D2RL::Overlay::FilledRectangleRequestSize;
	back.canvas = frame->canvas;
	back.rect = {x - 12.0F, y - 6.0F, x + width + 12.0F, y + size * 1.3F + 6.0F};
	back.color = {0.0F, 0.0F, 0.0F, 0.85F};
	back.rounding = 4.0F;
	(void)g_overlay->drawFilledRectangle(context, &back);
	D2RL::Overlay::TextRequest req{};
	req.structSize = D2RL::Overlay::TextRequestSize;
	req.canvas = frame->canvas;
	req.position = {x, y};
	req.color = {1.0F, 0.35F, 0.25F, 1.0F};
	req.textSize = size;
	req.text = notice;
	req.textLength = length;
	(void)g_overlay->drawText(context, &req);
}

}  // namespace

auto ShowWrongBuildNotice(const D2RL::PluginContext* context, const char* text) noexcept -> bool {
	return ShowNotice(context, text);
}

auto ShowNotice(const D2RL::PluginContext* context, const char* text) noexcept -> bool {
	if (context == nullptr || text == nullptr) {
		return false;
	}
	const int next = 1 - g_current.load();
	strncpy_s(g_notices[next], sizeof(g_notices[next]), text, _TRUNCATE);
	g_current.store(next);
	return RegisterNotice(context);
}

auto NoticeShown() noexcept -> bool {
	return g_registered && g_notices[g_current.load()][0] != '\0';
}

auto RegisterNotice(const D2RL::PluginContext* context) noexcept -> bool {
	if (g_registered) {
		return true;
	}
	if (context == nullptr) {
		return false;
	}
	if (context->QueryService(&g_overlay) != D2RL::ServiceQueryResult::Success ||
	    !D2RL::HasOverlayServiceField(g_overlay, D2RL::OverlayServiceRequiredSize)) {
		g_overlay = nullptr;
		return false;
	}
	D2RL::Overlay::CallbackRegistration reg{};
	reg.structSize = D2RL::Overlay::CallbackRegistrationSize;
	reg.phase = D2RL::Overlay::Phase::AfterGameUi;
	reg.callback = &DrawNotice;
	D2RL::Overlay::CallbackHandle handle = D2RL::Overlay::InvalidCallbackHandle;
	g_registered = g_overlay->registerFrameCallback(context, &reg, &handle) == D2RL::Overlay::Result::Success;
	return g_registered;
}
