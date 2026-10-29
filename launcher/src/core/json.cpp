#include "json.h"

#include <cmath>
#include <cstdio>
#include <cstdlib>

namespace mxl {
namespace {

const Json& NullJson() {
	static const Json n;
	return n;
}

struct Parser {
	const std::string& s;
	size_t i = 0;
	std::string err;

	void Ws() {
		while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\n' || s[i] == '\r'))
			++i;
	}
	bool Fail(const char* what) {
		if (err.empty())
			err = std::string(what) + " at byte " + std::to_string(i);
		return false;
	}
	bool Lit(const char* w) {
		size_t n = 0;
		while (w[n]) ++n;
		if (s.compare(i, n, w) != 0)
			return Fail("bad literal");
		i += n;
		return true;
	}
	static void PutUtf8(std::string& o, uint32_t c) {
		if (c < 0x80) o += char(c);
		else if (c < 0x800) { o += char(0xc0 | (c >> 6)); o += char(0x80 | (c & 0x3f)); }
		else if (c < 0x10000) { o += char(0xe0 | (c >> 12)); o += char(0x80 | ((c >> 6) & 0x3f)); o += char(0x80 | (c & 0x3f)); }
		else { o += char(0xf0 | (c >> 18)); o += char(0x80 | ((c >> 12) & 0x3f)); o += char(0x80 | ((c >> 6) & 0x3f)); o += char(0x80 | (c & 0x3f)); }
	}
	bool Hex4(uint32_t& v) {
		if (i + 4 > s.size())
			return Fail("short \\u escape");
		v = 0;
		for (int k = 0; k < 4; ++k) {
			char c = s[i++];
			v <<= 4;
			if (c >= '0' && c <= '9') v |= uint32_t(c - '0');
			else if (c >= 'a' && c <= 'f') v |= uint32_t(c - 'a' + 10);
			else if (c >= 'A' && c <= 'F') v |= uint32_t(c - 'A' + 10);
			else return Fail("bad \\u escape");
		}
		return true;
	}
	bool String(std::string& o) {
		if (s[i] != '"')
			return Fail("expected string");
		++i;
		while (i < s.size()) {
			char c = s[i++];
			if (c == '"')
				return true;
			if (uint8_t(c) < 0x20)
				return Fail("control character in string");
			if (c != '\\') {
				o += c;
				continue;
			}
			if (i >= s.size())
				break;
			char e = s[i++];
			switch (e) {
			case '"': o += '"'; break;
			case '\\': o += '\\'; break;
			case '/': o += '/'; break;
			case 'b': o += '\b'; break;
			case 'f': o += '\f'; break;
			case 'n': o += '\n'; break;
			case 'r': o += '\r'; break;
			case 't': o += '\t'; break;
			case 'u': {
				uint32_t v;
				if (!Hex4(v))
					return false;
				if (v >= 0xd800 && v < 0xdc00 && i + 1 < s.size() && s[i] == '\\' && s[i + 1] == 'u') {
					i += 2;
					uint32_t lo;
					if (!Hex4(lo))
						return false;
					v = 0x10000 + ((v - 0xd800) << 10) + (lo - 0xdc00);
				}
				PutUtf8(o, v);
				break;
			}
			default: return Fail("bad escape");
			}
		}
		return Fail("unterminated string");
	}
	bool Value(Json& out, int depth) {
		if (depth > 64)
			return Fail("nested too deep");
		Ws();
		if (i >= s.size())
			return Fail("unexpected end");
		char c = s[i];
		if (c == '{') {
			++i;
			out = Json::Object();
			Ws();
			if (i < s.size() && s[i] == '}') { ++i; return true; }
			for (;;) {
				Ws();
				std::string k;
				if (i >= s.size() || !String(k))
					return Fail("expected key");
				Ws();
				if (i >= s.size() || s[i] != ':')
					return Fail("expected ':'");
				++i;
				Json v;
				if (!Value(v, depth + 1))
					return false;
				out.Set(k, std::move(v));
				Ws();
				if (i < s.size() && s[i] == ',') { ++i; continue; }
				if (i < s.size() && s[i] == '}') { ++i; return true; }
				return Fail("expected ',' or '}'");
			}
		}
		if (c == '[') {
			++i;
			out = Json::Array();
			Ws();
			if (i < s.size() && s[i] == ']') { ++i; return true; }
			for (;;) {
				Json v;
				if (!Value(v, depth + 1))
					return false;
				out.Push(std::move(v));
				Ws();
				if (i < s.size() && s[i] == ',') { ++i; continue; }
				if (i < s.size() && s[i] == ']') { ++i; return true; }
				return Fail("expected ',' or ']'");
			}
		}
		if (c == '"') {
			std::string str;
			if (!String(str))
				return false;
			out = Json(std::move(str));
			return true;
		}
		if (c == 't') { if (!Lit("true")) return false; out = Json(true); return true; }
		if (c == 'f') { if (!Lit("false")) return false; out = Json(false); return true; }
		if (c == 'n') { if (!Lit("null")) return false; out = Json(); return true; }
		size_t start = i;
		if (s[i] == '-') ++i;
		while (i < s.size() && ((s[i] >= '0' && s[i] <= '9') || s[i] == '.' || s[i] == 'e' || s[i] == 'E' || s[i] == '+' || s[i] == '-'))
			++i;
		if (start == i)
			return Fail("unexpected character");
		std::string num = s.substr(start, i - start);
		char* end = nullptr;
		double d = std::strtod(num.c_str(), &end);
		if (!end || *end)
			return Fail("bad number");
		out = Json(d);
		return true;
	}
};

void Escape(std::string& out, const std::string& s) {
	out += '"';
	for (char c : s) {
		switch (c) {
		case '"': out += "\\\""; break;
		case '\\': out += "\\\\"; break;
		case '\n': out += "\\n"; break;
		case '\r': out += "\\r"; break;
		case '\t': out += "\\t"; break;
		default:
			if (uint8_t(c) < 0x20) {
				char b[8];
				std::snprintf(b, sizeof(b), "\\u%04x", unsigned(uint8_t(c)));
				out += b;
			} else {
				out += c;
			}
		}
	}
	out += '"';
}

}  // namespace

bool Json::Parse(const std::string& text, Json& out, std::string& error) {
	Parser p{text};
	if (text.size() >= 3 && uint8_t(text[0]) == 0xef && uint8_t(text[1]) == 0xbb && uint8_t(text[2]) == 0xbf)
		p.i = 3;  // UTF-8 BOM
	Json v;
	if (!p.Value(v, 0)) {
		error = p.err;
		return false;
	}
	p.Ws();
	if (p.i != text.size()) {
		error = "trailing data at byte " + std::to_string(p.i);
		return false;
	}
	out = std::move(v);
	return true;
}

const Json& Json::operator[](const std::string& key) const {
	if (type_ != Type::Object)
		return NullJson();
	auto it = obj_.find(key);
	return it == obj_.end() ? NullJson() : it->second;
}

const Json& Json::operator[](size_t i) const {
	return type_ == Type::Array && i < arr_.size() ? arr_[i] : NullJson();
}

Json& Json::Set(const std::string& key, Json v) {
	if (type_ != Type::Object) {
		*this = Object();
	}
	obj_[key] = std::move(v);
	return *this;
}

Json& Json::Push(Json v) {
	if (type_ != Type::Array)
		*this = Array();
	arr_.push_back(std::move(v));
	return *this;
}

void Json::DumpTo(std::string& out, int indent, int depth) const {
	auto nl = [&](int d) {
		if (indent <= 0)
			return;
		out += '\n';
		out.append(size_t(d * indent), '\t');
	};
	switch (type_) {
	case Type::Null: out += "null"; break;
	case Type::Bool: out += bool_ ? "true" : "false"; break;
	case Type::Number: {
		char b[32];
		if (std::floor(num_) == num_ && std::fabs(num_) < 9.0e15)
			std::snprintf(b, sizeof(b), "%lld", static_cast<long long>(num_));
		else
			std::snprintf(b, sizeof(b), "%.17g", num_);
		out += b;
		break;
	}
	case Type::String: Escape(out, str_); break;
	case Type::Array:
		out += '[';
		for (size_t k = 0; k < arr_.size(); ++k) {
			if (k) out += ',';
			nl(depth + 1);
			arr_[k].DumpTo(out, indent, depth + 1);
		}
		if (!arr_.empty()) nl(depth);
		out += ']';
		break;
	case Type::Object: {
		out += '{';
		bool first = true;
		for (const auto& [k, v] : obj_) {
			if (!first) out += ',';
			first = false;
			nl(depth + 1);
			Escape(out, k);
			out += indent > 0 ? ": " : ":";
			v.DumpTo(out, indent, depth + 1);
		}
		if (!obj_.empty()) nl(depth);
		out += '}';
		break;
	}
	}
}

std::string Json::Dump(int indent) const {
	std::string out;
	DumpTo(out, indent, 0);
	return out;
}

}  // namespace mxl
