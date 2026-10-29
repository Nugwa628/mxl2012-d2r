// Minimal JSON reader / writer for the release manifest and the downloader's own state file. UTF-8 in, UTF-8 out.
#pragma once

#include <cstdint>
#include <map>
#include <memory>
#include <string>
#include <vector>

namespace mxl {

class Json {
public:
	enum class Type { Null, Bool, Number, String, Array, Object };

	Json() = default;
	Json(bool b) : type_(Type::Bool), bool_(b) {}
	Json(double n) : type_(Type::Number), num_(n) {}
	Json(int n) : type_(Type::Number), num_(n) {}
	Json(int64_t n) : type_(Type::Number), num_(double(n)) {}
	Json(uint64_t n) : type_(Type::Number), num_(double(n)) {}
	Json(const char* s) : type_(Type::String), str_(s) {}
	Json(std::string s) : type_(Type::String), str_(std::move(s)) {}
	static Json Array() { Json j; j.type_ = Type::Array; return j; }
	static Json Object() { Json j; j.type_ = Type::Object; return j; }

	// Parse `text`; on failure returns false and sets `error` (with the byte offset).
	static bool Parse(const std::string& text, Json& out, std::string& error);
	std::string Dump(int indent = 1) const;

	Type type() const { return type_; }
	bool IsNull() const { return type_ == Type::Null; }
	bool IsObject() const { return type_ == Type::Object; }
	bool IsArray() const { return type_ == Type::Array; }
	bool IsString() const { return type_ == Type::String; }
	bool IsNumber() const { return type_ == Type::Number; }

	// Lenient accessors: a missing key or another type gives the fallback.
	const Json& operator[](const std::string& key) const;
	const Json& operator[](size_t i) const;
	std::string Str(const std::string& fallback = "") const { return type_ == Type::String ? str_ : fallback; }
	double Num(double fallback = 0) const { return type_ == Type::Number ? num_ : fallback; }
	int64_t Int(int64_t fallback = 0) const { return type_ == Type::Number ? int64_t(num_) : fallback; }
	bool Bool(bool fallback = false) const { return type_ == Type::Bool ? bool_ : fallback; }
	size_t size() const { return type_ == Type::Array ? arr_.size() : type_ == Type::Object ? obj_.size() : 0; }
	bool Has(const std::string& key) const { return type_ == Type::Object && obj_.count(key) != 0; }
	const std::vector<Json>& items() const { return arr_; }
	const std::map<std::string, Json>& members() const { return obj_; }

	Json& Set(const std::string& key, Json v);
	Json& Push(Json v);

private:
	void DumpTo(std::string& out, int indent, int depth) const;
	Type type_ = Type::Null;
	bool bool_ = false;
	double num_ = 0;
	std::string str_;
	std::vector<Json> arr_;
	std::map<std::string, Json> obj_;
};

}  // namespace mxl
