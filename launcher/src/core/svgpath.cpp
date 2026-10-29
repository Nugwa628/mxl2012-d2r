#include "svgpath.h"

#include <cctype>
#include <cstdint>
#include <cstdlib>

namespace mxl {

namespace {

struct Reader {
	const std::string& s;
	size_t i = 0;

	void SkipSeparators() {
		while (i < s.size() && (std::isspace(uint8_t(s[i])) || s[i] == ','))
			++i;
	}
	bool AtNumber() {
		SkipSeparators();
		return i < s.size() && (std::isdigit(uint8_t(s[i])) || s[i] == '-' || s[i] == '+' || s[i] == '.');
	}
	// SVG numbers run together: "1.5.5" is 1.5 and .5, "3-2" is 3 and -2.
	bool Number(float& v) {
		if (!AtNumber())
			return false;
		size_t start = i;
		if (s[i] == '-' || s[i] == '+')
			++i;
		bool dot = false, digits = false;
		while (i < s.size() && (std::isdigit(uint8_t(s[i])) || (s[i] == '.' && !dot))) {
			dot |= s[i] == '.';
			digits |= s[i] != '.';
			++i;
		}
		if (i < s.size() && (s[i] == 'e' || s[i] == 'E')) {
			size_t e = i + 1;
			if (e < s.size() && (s[e] == '-' || s[e] == '+'))
				++e;
			if (e < s.size() && std::isdigit(uint8_t(s[e]))) {
				i = e;
				while (i < s.size() && std::isdigit(uint8_t(s[i])))
					++i;
			}
		}
		if (!digits)
			return false;
		v = std::strtof(s.substr(start, i - start).c_str(), nullptr);
		return true;
	}
};

}  // namespace

bool ParseSvgPath(const std::string& d, std::vector<PathCmd>& out, std::string& error) {
	Reader r{d};
	float cx = 0, cy = 0, sx = 0, sy = 0;  // current point, subpath start
	float lcx = 0, lcy = 0;                // last control point (for S / T)
	char prev = 0, op = 0;
	auto add = [&](char o, std::initializer_list<float> v) {
		PathCmd c;
		c.op = o;
		int k = 0;
		for (float f : v)
			c.p[k++] = f;
		out.push_back(c);
	};
	for (;;) {
		r.SkipSeparators();
		if (r.i >= d.size())
			return true;
		if (std::isalpha(uint8_t(d[r.i]))) {
			op = d[r.i++];
		} else if (!op || op == 'Z' || op == 'z') {
			error = "number without a command at " + std::to_string(r.i);
			return false;
		} else if (op == 'M') {
			op = 'L';  // extra pairs after a move are lines
		} else if (op == 'm') {
			op = 'l';
		}
		bool rel = std::islower(uint8_t(op));
		char up = char(std::toupper(uint8_t(op)));
		float ox = rel ? cx : 0, oy = rel ? cy : 0;
		float v[6];
		auto read = [&](int n) {
			for (int k = 0; k < n; ++k)
				if (!r.Number(v[k])) {
					error = std::string("bad numbers for '") + op + "' at " + std::to_string(r.i);
					return false;
				}
			return true;
		};
		switch (up) {
		case 'M':
			if (!read(2)) return false;
			cx = sx = ox + v[0];
			cy = sy = oy + v[1];
			add('M', {cx, cy});
			lcx = cx, lcy = cy;
			break;
		case 'L':
			if (!read(2)) return false;
			cx = ox + v[0], cy = oy + v[1];
			add('L', {cx, cy});
			lcx = cx, lcy = cy;
			break;
		case 'H':
			if (!read(1)) return false;
			cx = ox + v[0];
			add('L', {cx, cy});
			lcx = cx, lcy = cy;
			break;
		case 'V':
			if (!read(1)) return false;
			cy = (rel ? cy : 0) + v[0];
			add('L', {cx, cy});
			lcx = cx, lcy = cy;
			break;
		case 'C':
			if (!read(6)) return false;
			add('C', {ox + v[0], oy + v[1], ox + v[2], oy + v[3], ox + v[4], oy + v[5]});
			lcx = ox + v[2], lcy = oy + v[3];
			cx = ox + v[4], cy = oy + v[5];
			break;
		case 'S': {
			if (!read(4)) return false;
			char p = char(std::toupper(uint8_t(prev)));
			float x1 = (p == 'C' || p == 'S') ? 2 * cx - lcx : cx, y1 = (p == 'C' || p == 'S') ? 2 * cy - lcy : cy;
			add('C', {x1, y1, ox + v[0], oy + v[1], ox + v[2], oy + v[3]});
			lcx = ox + v[0], lcy = oy + v[1];
			cx = ox + v[2], cy = oy + v[3];
			break;
		}
		case 'Q':
		case 'T': {
			float qx, qy;
			if (up == 'Q') {
				if (!read(4)) return false;
				qx = ox + v[0], qy = oy + v[1];
				v[0] = v[2], v[1] = v[3];
			} else {
				if (!read(2)) return false;
				char p = char(std::toupper(uint8_t(prev)));
				qx = (p == 'Q' || p == 'T') ? 2 * cx - lcx : cx;
				qy = (p == 'Q' || p == 'T') ? 2 * cy - lcy : cy;
			}
			float ex = ox + v[0], ey = oy + v[1];
			add('C', {cx + 2.f / 3 * (qx - cx), cy + 2.f / 3 * (qy - cy), ex + 2.f / 3 * (qx - ex), ey + 2.f / 3 * (qy - ey), ex, ey});
			lcx = qx, lcy = qy;
			cx = ex, cy = ey;
			break;
		}
		case 'Z':
			add('Z', {});
			cx = sx, cy = sy;
			lcx = cx, lcy = cy;
			break;
		default:
			error = std::string("unsupported path command '") + op + "'";
			return false;
		}
		prev = op;
	}
}

namespace {

// The value of attribute `name` in the tag that starts at `tag`.
bool Attribute(const std::string& svg, size_t tag, const std::string& name, std::string& value) {
	size_t end = svg.find('>', tag);
	for (size_t p = svg.find(name, tag); p != std::string::npos && p < end; p = svg.find(name, p + 1)) {
		if (!std::isspace(uint8_t(svg[p - 1])))
			continue;
		size_t q = p + name.size();
		while (q < end && std::isspace(uint8_t(svg[q])))
			++q;
		if (q >= end || svg[q] != '=')
			continue;
		++q;
		while (q < end && std::isspace(uint8_t(svg[q])))
			++q;
		if (q >= end || (svg[q] != '"' && svg[q] != '\''))
			return false;
		size_t close = svg.find(svg[q], q + 1);
		if (close == std::string::npos || close > end)
			return false;
		value = svg.substr(q + 1, close - q - 1);
		return true;
	}
	return false;
}

}  // namespace

bool ParseSvgIcon(const std::string& svg, SvgIcon& out, std::string& error) {
	out = SvgIcon{};
	size_t root = svg.find("<svg");
	std::string vb;
	if (root == std::string::npos || !Attribute(svg, root, "viewBox", vb)) {
		error = "no <svg viewBox>";
		return false;
	}
	Reader r{vb};
	for (float& f : out.viewBox)
		if (!r.Number(f)) {
			error = "bad viewBox \"" + vb + "\"";
			return false;
		}
	if (out.viewBox[2] <= 0 || out.viewBox[3] <= 0) {
		error = "empty viewBox";
		return false;
	}
	for (size_t p = svg.find("<path", root); p != std::string::npos; p = svg.find("<path", p + 5)) {
		std::string d;
		if (!Attribute(svg, p, "d", d)) {
			error = "<path> without d";
			return false;
		}
		if (!ParseSvgPath(d, out.path, error))
			return false;
	}
	if (out.path.empty()) {
		error = "no <path>";
		return false;
	}
	return true;
}

}  // namespace mxl
