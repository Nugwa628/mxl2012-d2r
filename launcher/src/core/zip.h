// A small ZIP reader for the D2RLoader package (docs/launcher.md "Install D2RLoader"): the central directory, Stored and
// Deflate entries, CRC-32 checks. Portable (no Windows headers) so the unit tests run on the Linux CI runner. No ZIP64,
// no encryption, no other methods: such an archive is refused with a message.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace mxl {

struct ZipEntry {
	std::string name;  // as stored, '/' separators; a folder ends in '/'
	uint16_t method = 0;  // 0 Stored, 8 Deflate
	uint16_t flags = 0;
	uint32_t crc = 0;
	uint64_t packedSize = 0, size = 0;
	uint64_t localOffset = 0;  // of the local header
	bool IsDir() const { return !name.empty() && name.back() == '/'; }
};

uint32_t Crc32(const void* data, size_t size, uint32_t crc = 0);

// Raw DEFLATE (RFC 1951) into `out`; more than `limit` bytes of output is an error.
bool Inflate(const uint8_t* in, size_t size, std::string& out, size_t limit, std::string& error);

// The entries of a whole ZIP file held in memory.
bool ReadZipDirectory(const std::string& zip, std::vector<ZipEntry>& out, std::string& error);
// One entry's bytes, checked against its size and CRC-32.
bool ExtractZipEntry(const std::string& zip, const ZipEntry& e, std::string& out, std::string& error);

}  // namespace mxl
