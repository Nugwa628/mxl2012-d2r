// Reading the release's .7z (docs/launcher.md "Installing from the 7z") with the LZMA SDK's C decoder
// (third_party/lzma, public domain). Portable (no Windows headers), so the unit tests run on the Linux CI runner.
//
// Memory: a solid block (a 7z "folder") made of one LZMA2 / LZMA / Copy coder is decoded as a stream through the
// coder's dictionary (the release's -mx7 LZMA2 block: 2^27 = 128 MB) and 1 MB buffers, whatever its size, so a 1.2 GB
// block never sits in memory. Other blocks (filters such as BCJ / BCJ2 in front of LZMA2: 7-Zip puts .dll / .exe files
// there) are decoded in one piece by the SDK, which is allowed up to InMemoryFolderMax.
#pragma once

#include <cstdint>
#include <cstdio>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace mxl {

// Random-access input: a file (StdioSource) or anything else that can read and seek.
class ByteSource {
public:
	virtual ~ByteSource() = default;
	virtual bool Read(void* buf, size_t& size) = 0;  // up to `size` bytes; size = 0 at the end
	virtual bool Seek(int64_t& pos, int origin) = 0;  // origin 0 set, 1 current, 2 end; pos gets the new position
};

// A ByteSource over an open FILE (not closed here).
class StdioSource : public ByteSource {
public:
	explicit StdioSource(std::FILE* f) : f_(f) {}
	bool Read(void* buf, size_t& size) override;
	bool Seek(int64_t& pos, int origin) override;

private:
	std::FILE* f_;
};

struct SevenZipEntry {
	std::string path;  // UTF-8, '/' separators, as stored ("mxl2012/mxl2012.mpq/modinfo.json")
	uint64_t size = 0;
	bool dir = false;
	bool hasCrc = false;
	uint32_t crc = 0;
};

struct SevenZipStats {
	uint64_t peakBuffer = 0;  // the largest decode buffer that was allocated (dictionary or in-memory block)
	size_t streamedBlocks = 0, memoryBlocks = 0;
};

constexpr uint64_t InMemoryFolderMax = 64ull << 20;

class SevenZipArchive {
public:
	SevenZipArchive();
	~SevenZipArchive();
	SevenZipArchive(const SevenZipArchive&) = delete;
	SevenZipArchive& operator=(const SevenZipArchive&) = delete;

	bool Open(ByteSource& src, std::string& error);  // `src` must outlive the archive
	const std::vector<SevenZipEntry>& entries() const;
	uint64_t UnpackedSize() const;  // all file bytes

	// Every entry once, in this order: folders and empty files first, then the files of each block in stream order.
	// begin(i) starts entry i (return false to skip its bytes: data is then not called for it), data() gets its bytes
	// in order, end(i) comes after its CRC was checked. progress(bytes decoded so far) about every MB. Any callback
	// returning false (except begin) stops the extraction with error "cancelled".
	struct Sink {
		std::function<bool(size_t)> begin;
		std::function<bool(const uint8_t*, size_t)> data;
		std::function<bool(size_t)> end;
		std::function<bool(uint64_t)> progress;
	};
	bool Extract(const Sink& sink, std::string& error, SevenZipStats* stats = nullptr);

private:
	struct Impl;
	std::unique_ptr<Impl> p_;
};

}  // namespace mxl
