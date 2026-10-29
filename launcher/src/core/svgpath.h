// The window's link icons are Font Awesome SVGs (launcher/res): one viewBox and one or more <path d="..."> elements.
// This reads that much SVG into absolute moves, lines and cubic curves; the window fills them with GDI+.
#pragma once

#include <string>
#include <vector>

namespace mxl {

struct PathCmd {
	char op = 'M';     // 'M' move, 'L' line, 'C' cubic (3 points), 'Z' close
	float p[6] = {};   // M / L: p[0..1]; C: p[0..5]
};

struct SvgIcon {
	float viewBox[4] = {0, 0, 0, 0};  // x, y, width, height
	std::vector<PathCmd> path;        // all <path> elements, filled with the nonzero rule
};

// Path data: M L H V C S Q T Z, absolute and relative. Arcs (A) are refused (none of our icons use them).
bool ParseSvgPath(const std::string& d, std::vector<PathCmd>& out, std::string& error);
bool ParseSvgIcon(const std::string& svg, SvgIcon& out, std::string& error);

}  // namespace mxl
