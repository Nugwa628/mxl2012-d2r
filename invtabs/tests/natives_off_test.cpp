// invtabs: a missing signature turns off only its own feature. A fake game image (PE headers and a .text section holding
// every core, optional and summary pattern once) is scanned the way the plugin scans the game:
//   - all patterns there: the core resolves all (tab areas on), the summary is ready;
//   - each of the summary's 13 patterns broken in turn: the summary is off (on, for its two optional ones) and every core
//     pattern still resolves (the tab areas stay on);
//   - each core pattern broken in turn: that one does not resolve, so Locate() turns the tab areas off (one log line, no
//     wrappers, no Ctrl+click, the page and its items untouched, docs/invtabs.md), while the summary module itself stays ready
//     (the plugin keeps it off then, because its items come from the area draw);
//   - the optional item type pattern broken: only it is missing.
#define NOMINMAX
#include <windows.h>

#include "../src/invtabs_logic.h"
#include "../src/invtabs_natives.h"
#include "../src/summary.h"
#include "../src/summary_natives.h"

#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

namespace {

int failures = 0;
#define CHECK(x) ((x) ? (void)0 : (void)(++failures, std::printf("FAIL line %d: %s\n", __LINE__, #x)))

constexpr std::size_t TextRva = 0x1000;

struct Image {
	std::vector<std::uint8_t> bytes;
	std::vector<std::size_t>  core, summary; // where each pattern's copy starts (RVA)
	std::size_t               type = 0;
};

void Put(std::vector<std::uint8_t>& out, const char* pattern, std::vector<std::size_t>* where) {
	if (where) where->push_back(out.size());
	for (const int b : invtabs::ParsePattern(pattern)) out.push_back(b < 0 ? 0x00 : static_cast<std::uint8_t>(b));
	out.insert(out.end(), 24, 0xCC);
}

Image Make() {
	Image img;
	img.bytes.assign(TextRva, 0);
	for (const auto& p : invtabs::NativePatterns) Put(img.bytes, p.pattern, &img.core);
	img.type = img.bytes.size();
	Put(img.bytes, invtabs::TypeCheckPattern.pattern, nullptr);
	for (const auto& p : invtabs::summary::SummaryPatterns) Put(img.bytes, p.pattern, &img.summary);
	img.bytes.resize((img.bytes.size() + 0xFFF) & ~std::size_t { 0xFFF }, 0xCC);
	auto* dos     = reinterpret_cast<IMAGE_DOS_HEADER*>(img.bytes.data());
	dos->e_magic  = IMAGE_DOS_SIGNATURE;
	dos->e_lfanew = 0x80;
	auto* nt                          = reinterpret_cast<IMAGE_NT_HEADERS64*>(img.bytes.data() + 0x80);
	nt->Signature                     = IMAGE_NT_SIGNATURE;
	nt->FileHeader.Machine            = IMAGE_FILE_MACHINE_AMD64;
	nt->FileHeader.NumberOfSections   = 1;
	nt->FileHeader.SizeOfOptionalHeader = sizeof(IMAGE_OPTIONAL_HEADER64);
	nt->OptionalHeader.Magic          = IMAGE_NT_OPTIONAL_HDR64_MAGIC;
	IMAGE_SECTION_HEADER* sec         = IMAGE_FIRST_SECTION(nt);
	std::memcpy(sec->Name, ".text", 5);
	sec->VirtualAddress   = static_cast<DWORD>(TextRva);
	sec->Misc.VirtualSize = static_cast<DWORD>(img.bytes.size() - TextRva);
	return img;
}

int CoreFound(const Image& img) {
	int n = 0;
	for (const auto& p : invtabs::NativePatterns) n += invtabs::ResolveNative(img.bytes.data(), TextRva, img.bytes.size() - TextRva, p) >= 0;
	return n;
}

bool TypeFound(const Image& img) { return invtabs::ResolveNative(img.bytes.data(), TextRva, img.bytes.size() - TextRva, invtabs::TypeCheckPattern) >= 0; }

bool SummaryReady(const Image& img) {
	invtabs::summary::Summary s;
	return s.Init(img.bytes.data(), [](const char*) {});
}

} // namespace

int main() {
	const Image all = Make();
	CHECK(CoreFound(all) == invtabs::NativeCount);
	CHECK(TypeFound(all));
	CHECK(SummaryReady(all));
	for (int n = 0; n < invtabs::summary::SummaryNativeCount; ++n) {
		Image broken = Make();
		broken.bytes[broken.summary[static_cast<std::size_t>(n)]] ^= 0x5A; // the first byte is never a wildcard
		CHECK(SummaryReady(broken) == invtabs::summary::SummaryNativeOptional(n));
		CHECK(CoreFound(broken) == invtabs::NativeCount); // the tab areas stay on
		CHECK(TypeFound(broken));
	}
	for (int n = 0; n < invtabs::NativeCount; ++n) {
		Image broken = Make();
		broken.bytes[broken.core[static_cast<std::size_t>(n)]] ^= 0x5A;
		CHECK(invtabs::ResolveNative(broken.bytes.data(), TextRva, broken.bytes.size() - TextRva, invtabs::NativePatterns[n]) < 0);
		CHECK(CoreFound(broken) == invtabs::NativeCount - 1); // Locate() needs all: the tab areas are off
		CHECK(SummaryReady(broken));
		CHECK(TypeFound(broken));
	}
	Image noType = Make();
	noType.bytes[noType.type] ^= 0x5A;
	CHECK(!TypeFound(noType) && CoreFound(noType) == invtabs::NativeCount && SummaryReady(noType));
	// a pattern found twice is as good as missing
	Image twice = Make();
	Put(twice.bytes, invtabs::NativePatterns[0].pattern, nullptr);
	reinterpret_cast<IMAGE_SECTION_HEADER*>(IMAGE_FIRST_SECTION(reinterpret_cast<IMAGE_NT_HEADERS64*>(twice.bytes.data() + 0x80)))->Misc.VirtualSize =
	    static_cast<DWORD>(twice.bytes.size() - TextRva);
	CHECK(CoreFound(twice) == invtabs::NativeCount - 1);
	if (failures) {
		std::printf("natives_off_tests: %d check(s) failed\n", failures);
		return 1;
	}
	std::printf("natives_off_tests: all checks passed (%d core, 1 optional, %d summary patterns)\n", invtabs::NativeCount, invtabs::summary::SummaryNativeCount);
	return 0;
}
