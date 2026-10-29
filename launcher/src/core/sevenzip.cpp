#include "sevenzip.h"

#include "../../third_party/lzma/C/7z.h"
#include "../../third_party/lzma/C/7zAlloc.h"
#include "../../third_party/lzma/C/7zCrc.h"
#include "../../third_party/lzma/C/Lzma2Dec.h"
#include "../../third_party/lzma/C/LzmaDec.h"

#include <algorithm>
#include <cstdlib>
#include <mutex>

namespace mxl {

bool StdioSource::Read(void* buf, size_t& size) {
	size_t n = std::fread(buf, 1, size, f_);
	bool ok = n == size || !std::ferror(f_);
	size = n;
	return ok;
}

bool StdioSource::Seek(int64_t& pos, int origin) {
	int o = origin == 0 ? SEEK_SET : origin == 1 ? SEEK_CUR : SEEK_END;
#ifdef _WIN32
	if (_fseeki64(f_, pos, o) != 0)
		return false;
	pos = _ftelli64(f_);
#else
	if (fseeko(f_, off_t(pos), o) != 0)
		return false;
	pos = int64_t(ftello(f_));
#endif
	return pos >= 0;
}

namespace {

constexpr UInt32 MethodCopy = 0, MethodLzma2 = 0x21, MethodLzma = 0x30101;
constexpr size_t OutChunk = 1 << 20, LookBuffer = 1 << 20;

struct SeekStream {
	ISeekInStream vt;
	ByteSource* src;
};

SRes StreamRead(ISeekInStreamPtr p, void* buf, size_t* size) {
	auto* s = reinterpret_cast<const SeekStream*>(p);
	return s->src->Read(buf, *size) ? SZ_OK : SZ_ERROR_READ;
}

SRes StreamSeek(ISeekInStreamPtr p, Int64* pos, ESzSeek origin) {
	auto* s = reinterpret_cast<const SeekStream*>(p);
	int64_t v = *pos;
	if (!s->src->Seek(v, int(origin)))
		return SZ_ERROR_READ;
	*pos = v;
	return SZ_OK;
}

const ISzAlloc AllocMain = {SzAlloc, SzFree};
const ISzAlloc AllocTemp = {SzAllocTemp, SzFreeTemp};

std::string Utf8FromUtf16(const std::vector<UInt16>& w) {
	std::string out;
	for (size_t i = 0; i < w.size() && w[i]; ++i) {
		uint32_t c = w[i];
		if (c >= 0xD800 && c < 0xDC00 && i + 1 < w.size() && w[i + 1] >= 0xDC00 && w[i + 1] < 0xE000)
			c = 0x10000 + ((c - 0xD800) << 10) + (w[++i] - 0xDC00);
		if (c < 0x80) {
			out += char(c);
		} else if (c < 0x800) {
			out += char(0xC0 | (c >> 6));
			out += char(0x80 | (c & 63));
		} else if (c < 0x10000) {
			out += char(0xE0 | (c >> 12));
			out += char(0x80 | ((c >> 6) & 63));
			out += char(0x80 | (c & 63));
		} else {
			out += char(0xF0 | (c >> 18));
			out += char(0x80 | ((c >> 12) & 63));
			out += char(0x80 | ((c >> 6) & 63));
			out += char(0x80 | (c & 63));
		}
	}
	for (char& ch : out)
		if (ch == '\\')
			ch = '/';
	return out;
}

std::string SResText(SRes r) {
	switch (r) {
	case SZ_ERROR_DATA: return "damaged data";
	case SZ_ERROR_MEM: return "out of memory";
	case SZ_ERROR_CRC: return "CRC mismatch";
	case SZ_ERROR_UNSUPPORTED: return "unsupported compression method";
	case SZ_ERROR_INPUT_EOF: return "the archive ends early";
	case SZ_ERROR_READ: return "read error";
	case SZ_ERROR_ARCHIVE: return "not a valid 7z archive";
	case SZ_ERROR_NO_ARCHIVE: return "not a 7z archive";
	default: return "7z error " + std::to_string(int(r));
	}
}

}  // namespace

struct SevenZipArchive::Impl {
	SeekStream stream{};
	CLookToRead2 look{};
	CSzArEx db{};
	bool open = false;
	std::vector<SevenZipEntry> entries;
	uint64_t unpacked = 0;

	Impl() { SzArEx_Init(&db); }
	~Impl() {
		if (open)
			SzArEx_Free(&db, &AllocMain);
		std::free(look.buf);
	}
};

SevenZipArchive::SevenZipArchive() : p_(std::make_unique<Impl>()) {}
SevenZipArchive::~SevenZipArchive() = default;
const std::vector<SevenZipEntry>& SevenZipArchive::entries() const { return p_->entries; }
uint64_t SevenZipArchive::UnpackedSize() const { return p_->unpacked; }

bool SevenZipArchive::Open(ByteSource& src, std::string& error) {
	static std::once_flag crc;
	std::call_once(crc, [] { CrcGenerateTable(); });
	Impl& m = *p_;
	m.stream.vt.Read = StreamRead;
	m.stream.vt.Seek = StreamSeek;
	m.stream.src = &src;
	LookToRead2_CreateVTable(&m.look, False);
	m.look.buf = static_cast<Byte*>(std::malloc(LookBuffer));
	if (!m.look.buf) {
		error = "out of memory";
		return false;
	}
	m.look.bufSize = LookBuffer;
	m.look.realStream = &m.stream.vt;
	LookToRead2_INIT(&m.look)
	SRes r = SzArEx_Open(&m.db, &m.look.vt, &AllocMain, &AllocTemp);
	if (r != SZ_OK) {
		error = SResText(r);
		return false;
	}
	m.open = true;
	for (UInt32 i = 0; i < m.db.NumFiles; ++i) {
		SevenZipEntry e;
		std::vector<UInt16> name(SzArEx_GetFileNameUtf16(&m.db, i, nullptr));
		SzArEx_GetFileNameUtf16(&m.db, i, name.data());
		e.path = Utf8FromUtf16(name);
		e.dir = SzArEx_IsDir(&m.db, i);
		e.size = SzArEx_GetFileSize(&m.db, i);
		e.hasCrc = SzBitWithVals_Check(&m.db.CRCs, i);
		e.crc = e.hasCrc ? m.db.CRCs.Vals[i] : 0;
		m.unpacked += e.size;
		m.entries.push_back(std::move(e));
	}
	return true;
}

bool SevenZipArchive::Extract(const Sink& sink, std::string& error, SevenZipStats* stats) {
	Impl& m = *p_;
	CSzArEx& db = m.db;
	SevenZipStats st;
	uint64_t done = 0, lastShown = 0;
	auto cancelled = [&] {
		error = "cancelled";
		return false;
	};
	// entries without data (folders, empty files) first
	for (UInt32 i = 0; i < db.NumFiles; ++i)
		if (db.FileToFolder[i] == UInt32(-1)) {
			if (sink.begin(i) && !sink.end(i))
				return cancelled();
		}
	for (UInt32 f = 0; f < db.db.NumFolders; ++f) {
		std::vector<UInt32> files;  // the block's files in stream order
		for (UInt32 i = db.FolderToFile[f]; i < db.NumFiles && i < db.FolderToFile[f + 1]; ++i)
			if (db.FileToFolder[i] == f)
				files.push_back(i);
		size_t cur = 0;
		uint64_t left = files.empty() ? 0 : m.entries[files[0]].size;
		bool want = false, started = false;
		UInt32 crc = CRC_INIT_VAL, folderCrc = CRC_INIT_VAL;
		std::string bad;
		// The block's bytes, in order, are cut into its files.
		auto emit = [&](const Byte* p, size_t n) -> bool {
			folderCrc = CrcUpdate(folderCrc, p, n);
			while (cur < files.size()) {
				UInt32 idx = files[cur];
				if (!started) {
					want = sink.begin(idx);
					started = true;
					crc = CRC_INIT_VAL;
				}
				size_t take = size_t(std::min<uint64_t>(left, n));
				if (take) {
					crc = CrcUpdate(crc, p, take);
					if (want && !sink.data(p, take))
						return false;
					p += take;
					n -= take;
					left -= take;
				}
				if (left)
					break;  // more of this file in the next chunk
				const SevenZipEntry& e = m.entries[idx];
				if (e.hasCrc && CRC_GET_DIGEST(crc) != e.crc) {
					bad = "CRC mismatch in " + e.path;
					return false;
				}
				if (!sink.end(idx))
					return false;
				started = false;
				if (++cur < files.size())
					left = m.entries[files[cur]].size;
				if (!n && left)
					break;
			}
			if (n) {
				bad = "a 7z block holds more data than its files";
				return false;
			}
			return true;
		};
		auto progress = [&](size_t n) {
			done += n;
			if (sink.progress && done - lastShown >= (1u << 20)) {
				lastShown = done;
				return sink.progress(done);
			}
			return true;
		};

		CSzFolder folder;
		CSzData sd;
		const Byte* coders = db.db.CodersData + db.db.FoCodersOffsets[f];
		sd.Data = coders;
		sd.Size = db.db.FoCodersOffsets[f + 1] - db.db.FoCodersOffsets[f];
		if (SzGetNextFolderItem(&folder, &sd) != SZ_OK) {
			error = "damaged 7z header (block " + std::to_string(f) + ")";
			return false;
		}
		uint64_t unpack = SzAr_GetFolderUnpackSize(&db.db, f);
		UInt32 packIndex = db.db.FoStartPackStreamIndex[f];
		uint64_t packPos = db.dataPos + db.db.PackPositions[packIndex];
		uint64_t packSize = db.db.PackPositions[packIndex + 1] - db.db.PackPositions[packIndex];
		const CSzCoderInfo& c0 = folder.Coders[0];
		bool simple = folder.NumCoders == 1 && folder.NumPackStreams == 1 && folder.NumBonds == 0 && c0.NumStreams == 1 &&
		              (c0.MethodID == MethodLzma2 || c0.MethodID == MethodLzma || c0.MethodID == MethodCopy);

		if (!simple) {  // filters in front of the coder: the SDK decodes the block in one piece
			if (unpack > InMemoryFolderMax) {
				error = "a 7z block of " + std::to_string(unpack >> 20) + " MB with filters (more than " +
				        std::to_string(InMemoryFolderMax >> 20) + " MB) is not supported";
				return false;
			}
			std::vector<Byte> out(size_t(unpack) + 1);
			st.peakBuffer = std::max<uint64_t>(st.peakBuffer, unpack);
			++st.memoryBlocks;
			SRes r = SzAr_DecodeFolder(&db.db, f, &m.look.vt, db.dataPos, out.data(), size_t(unpack), &AllocMain);
			if (r != SZ_OK) {
				error = SResText(r) + " (block " + std::to_string(f) + ")";
				return false;
			}
			if (!emit(out.data(), size_t(unpack)))
				return bad.empty() ? cancelled() : (error = bad, false);
			if (!progress(size_t(unpack)))
				return cancelled();
			continue;
		}

		// one coder: decoded as a stream through its dictionary
		++st.streamedBlocks;
		const Byte* props = coders + c0.PropsOffset;
		CLzma2Dec l2;
		CLzmaDec l1;
		Lzma2Dec_CONSTRUCT(&l2)
		LzmaDec_CONSTRUCT(&l1)
		SRes r = SZ_OK;
		if (c0.MethodID == MethodLzma2) {
			if (c0.PropsSize != 1 || props[0] > 40) {
				error = "bad LZMA2 properties";
				return false;
			}
			r = Lzma2Dec_Allocate(&l2, props[0], &AllocMain);
			if (r == SZ_OK) {
				Lzma2Dec_Init(&l2);
				st.peakBuffer = std::max<uint64_t>(st.peakBuffer, l2.decoder.dicBufSize);
			}
		} else if (c0.MethodID == MethodLzma) {
			r = LzmaDec_Allocate(&l1, props, c0.PropsSize, &AllocMain);
			if (r == SZ_OK) {
				LzmaDec_Init(&l1);
				st.peakBuffer = std::max<uint64_t>(st.peakBuffer, l1.dicBufSize);
			}
		}
		auto freeDec = [&] {
			Lzma2Dec_Free(&l2, &AllocMain);
			LzmaDec_Free(&l1, &AllocMain);
		};
		if (r != SZ_OK) {
			freeDec();
			error = SResText(r);
			return false;
		}
		r = LookInStream_SeekTo(&m.look.vt, packPos);
		std::vector<Byte> out(OutChunk);
		uint64_t outLeft = unpack, inLeft = packSize;
		bool ok = r == SZ_OK;
		if (!ok)
			error = SResText(r);
		while (ok && outLeft) {
			const void* in = nullptr;
			size_t avail = size_t(std::min<uint64_t>(inLeft, LookBuffer));
			if (avail == 0 && c0.MethodID == MethodCopy) {
				error = "the archive ends early";
				ok = false;
				break;
			}
			r = ILookInStream_Look(&m.look.vt, &in, &avail);
			if (r != SZ_OK) {
				error = SResText(r);
				ok = false;
				break;
			}
			SizeT inLen = avail, outLen = SizeT(std::min<uint64_t>(outLeft, OutChunk));
			ELzmaStatus status = LZMA_STATUS_NOT_SPECIFIED;
			if (c0.MethodID == MethodCopy) {
				inLen = outLen = std::min<SizeT>(inLen, outLen);
				std::copy_n(static_cast<const Byte*>(in), outLen, out.data());
			} else if (c0.MethodID == MethodLzma2) {
				r = Lzma2Dec_DecodeToBuf(&l2, out.data(), &outLen, static_cast<const Byte*>(in), &inLen, LZMA_FINISH_ANY, &status);
			} else {
				r = LzmaDec_DecodeToBuf(&l1, out.data(), &outLen, static_cast<const Byte*>(in), &inLen, LZMA_FINISH_ANY, &status);
			}
			if (r != SZ_OK) {
				error = SResText(r) + " (block " + std::to_string(f) + ")";
				ok = false;
				break;
			}
			ILookInStream_Skip(&m.look.vt, inLen);
			inLeft -= inLen;
			outLeft -= outLen;
			if (inLen == 0 && outLen == 0) {
				error = "the archive ends early (block " + std::to_string(f) + ")";
				ok = false;
				break;
			}
			if (!emit(out.data(), outLen)) {
				if (bad.empty())
					cancelled();
				else
					error = bad;
				ok = false;
				break;
			}
			if (!progress(outLen)) {
				cancelled();
				ok = false;
			}
		}
		freeDec();
		if (!ok)
			return false;
		if (SzBitWithVals_Check(&db.db.FolderCRCs, f) && CRC_GET_DIGEST(folderCrc) != db.db.FolderCRCs.Vals[f]) {
			error = "CRC mismatch (block " + std::to_string(f) + ")";
			return false;
		}
		if (cur != files.size()) {
			error = "a 7z block ends before its files (block " + std::to_string(f) + ")";
			return false;
		}
	}
	if (sink.progress)
		sink.progress(done);
	if (stats)
		*stats = st;
	return true;
}

}  // namespace mxl
