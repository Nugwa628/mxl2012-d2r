// SHA-256 (FIPS 180-4). Portable so the unit tests run on the Linux CI runner; the downloader hashes every file it
// downloads, installs or verifies with it.
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>

namespace mxl {

class Sha256 {
public:
	Sha256();
	void Update(const void* data, size_t size);
	// Lower-case hex digest. The object is spent afterwards.
	std::string HexDigest();

private:
	void Block(const uint8_t* p);
	uint32_t h_[8];
	uint8_t buf_[64];
	size_t used_ = 0;
	uint64_t total_ = 0;
};

std::string Sha256Hex(const void* data, size_t size);

}  // namespace mxl
