// The downloader window (docs/launcher.md "Window"): the official Median XL launcher's art, drawn with GDI+.
#pragma once

#include "app.h"

#include <windows.h>

#include <string>

namespace mxl {

// Runs the window until it is closed. With `snapshot`, the window stays hidden: after the start-up check it is drawn
// once into that PNG file and closed (docs, tests; nothing is shown and no focus is taken).
int RunWindow(HINSTANCE inst, const Options& opt, const std::wstring& snapshot);

}  // namespace mxl
