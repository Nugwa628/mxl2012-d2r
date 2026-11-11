// D2RLoader extended schema 0x44520005: retain every byte outside selected
// top-level player items.
#pragma once
#include "../../launcher/src/core/sha256.h"
#include "stash_retire_data.h"
#include <algorithm>
#include <cstdio>
#include <stdexcept>
#include <vector>
namespace stash_retire {
using Bytes = std::vector<uint8_t>;
inline unsigned U(const Bytes &b, size_t p, unsigned n = 4) {
  if (n > 4 || p + n > b.size())
    throw std::runtime_error("truncated save");
  unsigned v = 0;
  for (unsigned i = 0; i < n; i++)
    v |= unsigned(b[p + i]) << (8 * i);
  return v;
}
inline void Put(Bytes &b, size_t p, unsigned v, unsigned n = 4) {
  if (p + n > b.size())
    throw std::runtime_error("short output");
  for (unsigned i = 0; i < n; i++)
    b[p + i] = uint8_t(v >> (8 * i));
}
inline unsigned Checksum(const Bytes &b) {
  unsigned c = 0;
  for (size_t i = 0; i < b.size(); i++)
    c = ((c << 1) | (c >> 31)) + ((i >= 12 && i < 16) ? 0 : b[i]);
  return c;
}
inline std::string Hash(const Bytes &b, size_t p = 0) {
  return mxl::Sha256Hex(b.data() + p, b.size() - p);
}
inline std::string Digest(const Bytes &b, size_t p) {
  static const char *hex = "0123456789abcdef";
  if (p + 32 > b.size())
    throw std::runtime_error("short digest");
  std::string s;
  for (size_t i = p; i < p + 32; i++) {
    s += hex[b[i] >> 4];
    s += hex[b[i] & 15];
  }
  return s;
}
inline void SetDigest(Bytes &b, size_t p, const std::string &h) {
  for (size_t i = 0; i < 32; i++)
    b.at(p + i) = uint8_t(std::stoul(h.substr(i * 2, 2), nullptr, 16));
}
struct Reader {
  const Bytes &b;
  size_t pos;
  unsigned Read(unsigned n) {
    if (n > 32 || pos + n > b.size() * 8)
      throw std::runtime_error("invalid bit field");
    unsigned v = 0;
    for (unsigned i = 0; i < n; i++, pos++)
      v |= unsigned((b[pos / 8] >> (pos % 8)) & 1) << i;
    return v;
  }
  void Skip(unsigned n) {
    while (n > 32) {
      Read(32);
      n -= 32;
    }
    Read(n);
  }
  void Optional(unsigned n) {
    if (Read(1))
      Skip(n);
  }
  void String(unsigned n) {
    for (unsigned i = 0; i < 256; i++)
      if (!Read(n))
        return;
    throw std::runtime_error("unterminated item string");
  }
  std::string Code() {
    std::string s;
    for (int i = 0; i < 4; i++) {
      std::string p;
      bool found = false;
      for (int j = 0; j < 20; j++) {
        p += Read(1) ? '1' : '0';
        auto it = Codes.find(p);
        if (it != Codes.end()) {
          s += it->second;
          found = true;
          break;
        }
      }
      if (!found)
        throw std::runtime_error("unknown item code");
    }
    while (!s.empty() && s.back() == ' ')
      s.pop_back();
    return s;
  }
  void Props() {
    for (size_t i = 0; i < 4096; i++) {
      unsigned sid = Read(16);
      if (sid == 65535)
        return;
      unsigned count =
          (sid == 54 || sid == 57)
              ? 3
              : ((sid == 17 || sid == 48 || sid == 50 || sid == 52) ? 2 : 1);
      for (unsigned k = 0; k < count; k++) {
        auto it = Stats.find(sid + k);
        if (it == Stats.end() || !it->second.bits)
          throw std::runtime_error("unknown item stat");
        if (k == 0 && it->second.par)
          Skip(32);
        Skip(it->second.bits);
      }
    }
    throw std::runtime_error("unterminated item stats");
  }
};
struct Item {
  unsigned location, page, children;
  size_t begin, end;
};
inline Item ReadItem(Reader &r) {
  Item it{};
  it.begin = r.pos / 8;
  unsigned flags = r.Read(32);
  r.Skip(11);
  it.location = r.Read(3);
  r.Skip(12);
  it.page = r.Read(3);
  if (flags & 0x10000) {
    r.Skip(10);
    r.String(7);
  } else {
    auto code = r.Code();
    if (flags & 0x200000) {
      if (QuestDiff.count(code))
        r.Skip(Stats.at(356).bits);
      r.Optional(128);
      if (r.Read(1))
        r.Skip(8);
    } else {
      it.children = r.Read(3);
      r.Skip(39);
      unsigned q = r.Read(4);
      r.Optional(3);
      r.Optional(16);
      if (q == 2 && Charms.count(code))
        r.Skip(17);
      else if (q == 2 && BodyParts.count(code))
        r.Skip(10);
      else if (q == 1 || q == 3)
        r.Skip(3);
      else if (q == 4)
        r.Skip(32);
      else if (q == 5 || q == 7)
        r.Skip(16);
      else if (q == 6 || q == 8) {
        r.Skip(32);
        for (int i = 0; i < 8; i++)
          r.Optional(16);
      } else if (q != 2)
        throw std::runtime_error("unknown quality");
      if (flags & 0x4000000)
        r.Skip(16);
      if (flags & 0x1000000)
        r.String(8);
      if (Tomes.count(code))
        r.Skip(5);
      r.Optional(128);
      if (Armor.count(code))
        r.Skip(Stats.at(31).bits);
      if (Armor.count(code) || Weapons.count(code)) {
        int dur = int(r.Read(Stats.at(73).bits)) - Stats.at(73).add;
        if (dur > 0)
          r.Skip(Stats.at(72).bits);
      }
      r.Skip(1);
      if (Stackable.count(code))
        r.Skip(9);
      if (flags & 0x800)
        r.Skip(4);
      unsigned mask = q == 5 ? r.Read(5) : 0;
      r.Props();
      for (int i = 0; i < 5; i++)
        if (mask & (1 << i))
          r.Props();
      if (flags & 0x4000000)
        r.Props();
      if (flags & 0x10000000) {
        r.Skip(16);
        unsigned count = 1;
        if (!(flags & 0x20000000)) {
          r.Skip(32);
          count = std::min(r.Read(4), 8u);
        }
        r.Skip(count * 64);
      }
      if (r.Read(1))
        r.Skip(8);
    }
  }
  r.pos = ((r.pos + 7) / 8) * 8;
  if (r.pos > r.b.size() * 8)
    throw std::runtime_error("truncated item padding");
  it.end = r.pos / 8;
  return it;
}
inline bool HasField(const Bytes &b, const std::string &s) {
  Bytes pattern(4);
  Put(pattern, 0, unsigned(s.size()));
  pattern.insert(pattern.end(), s.begin(), s.end());
  return std::search(b.begin() + 0x154, b.end(), pattern.begin(),
                     pattern.end()) != b.end();
}
// Plugins that own D2RLoader's one custom player page (native page 6):
// Dimentio's CharmInv 1.0.1 and invtabs (docs/invtabs.md), which replaces it
// and adopts CharmInv's page-6 items. A sidecar recording one of them belongs
// to a character whose page 6 is that plugin's, not the retired stash page 2.
inline constexpr const char *PageOwners[] = {"d2rl-charm-inv.dll",
                                             "invtabs.dll"};
inline bool PageOwnerRecorded(const Bytes &side) {
  for (const char *file : PageOwners)
    if (HasField(side, file))
      return true;
  return false;
}
// The first cleanup release is also a persistent origin marker in D2RLoader's
// existing per-plugin version field. A refused load without its page owner can
// rewrite the provider list, but this core version remains. Never reclaim its
// page again.
inline bool RetiredCore(const Bytes &side) {
  const std::string file = "mxl2012-core.dll";
  Bytes pattern(4);
  Put(pattern, 0, unsigned(file.size()));
  pattern.insert(pattern.end(), file.begin(), file.end());
  auto found = std::search(side.begin() + 0x154, side.end(), pattern.begin(),
                           pattern.end());
  if (found == side.end())
    return false;
  size_t pos = size_t(found - side.begin()) + pattern.size();
  unsigned len = U(side, pos);
  pos += 4;
  if (len > 32 || pos + len > side.size())
    throw std::runtime_error("invalid core origin version");
  std::string version(side.begin() + pos, side.begin() + pos + len);
  unsigned major = 0, minor = 0, patch = 0;
  char tail = 0;
  if (std::sscanf(version.c_str(), "%u.%u.%u%c", &major, &minor, &patch,
                  &tail) != 3)
    throw std::runtime_error("unknown core origin version");
  return major > 0 || minor > 1 || (minor == 1 && patch >= 19);
}
struct Plan {
  Bytes save, sidecar;
  unsigned removed = 0;
  bool charmOrigin = false;
};
inline Plan MakePlan(const Bytes &save, const Bytes &side,
                     bool inspect = false) {
  if (save.size() < 0x340 || U(save, 0) != 0xaa55aa55 ||
      U(save, 4) != 0x44520005 || U(save, 8) != save.size() ||
      U(save, 12) != Checksum(save))
    throw std::runtime_error("unsupported or damaged extended save");
  if (side.size() < 0x154 || U(side, 0) != 0x4c523244 || U(side, 4, 2) != 2 ||
      U(side, 6, 2) != 0x2c || U(side, 8) != side.size() - 0x2c ||
      Digest(side, 12) != Hash(side, 0x2c) || U(side, 0x34) != U(save, 12) ||
      U(side, 0x38) != save.size() || Digest(side, 0x3c) != Hash(save))
    throw std::runtime_error("invalid or mismatched sidecar");
  Plan p{save, side};
  // Conservative: a recorded page-6 owner DLL (CharmInv or invtabs) always
  // wins, regardless of page contents or coordinates.
  if (!inspect && (PageOwnerRecorded(side) || RetiredCore(side))) {
    p.charmOrigin = true;
    return p;
  }
  if (!HasField(side, "mxl2012-core.dll"))
    throw std::runtime_error("unknown save origin");
  size_t gf = 0;
  for (size_t i = 0x300; i + 2 < save.size(); i++)
    if (save[i] == 'g' && save[i + 1] == 'f') {
      gf = i;
      break;
    }
  if (!gf)
    throw std::runtime_error("missing character stats");
  Reader r{save, (gf + 2) * 8};
  for (unsigned i = 0; i < 1024; i++) {
    unsigned id = r.Read(16);
    if (id == 65535)
      break;
    auto s = Stats.find(id);
    if (s == Stats.end() || !s->second.csv)
      throw std::runtime_error("unknown character stat");
    r.Skip(s->second.csvpar + s->second.csv);
    if (i == 1023)
      throw std::runtime_error("unterminated character stats");
  }
  size_t skill = (r.pos + 7) / 8;
  if (U(save, skill, 2) != 0x6669)
    throw std::runtime_error("missing skills");
  size_t jm = skill + 2;
  while (jm + 2 < save.size() && U(save, jm, 2) != 0x4d4a)
    jm++;
  unsigned count = U(save, jm + 2, 2);
  r.pos = (jm + 4) * 8;
  Bytes kept;
  for (unsigned i = 0; i < count; i++) {
    auto it = ReadItem(r);
    for (unsigned k = 0; k < it.children; k++) {
      auto child = ReadItem(r);
      if (child.children)
        throw std::runtime_error("nested socket children");
    }
    if (it.location == 0 && it.page == 7)
      p.removed++;
    else
      kept.insert(kept.end(), save.begin() + it.begin,
                  save.begin() + r.pos / 8);
  }
  size_t end = r.pos / 8;
  if (U(save, end, 2) != 0x4d4a)
    throw std::runtime_error("invalid player item boundary");
  if (!p.removed)
    return p;
  p.save.assign(save.begin(), save.begin() + jm + 4);
  Put(p.save, jm + 2, count - p.removed, 2);
  p.save.insert(p.save.end(), kept.begin(), kept.end());
  p.save.insert(p.save.end(), save.begin() + end, save.end());
  Put(p.save, 8, unsigned(p.save.size()));
  Put(p.save, 12, Checksum(p.save));
  Put(p.sidecar, 0x34, U(p.save, 12));
  Put(p.sidecar, 0x38, unsigned(p.save.size()));
  SetDigest(p.sidecar, 0x3c, Hash(p.save));
  SetDigest(p.sidecar, 12, Hash(p.sidecar, 0x2c));
  return p;
}
// A stale journal must never roll back a newer, valid page-owner save. Recover
// only the two possible half-written pairs from this exact conversion.
inline bool NeedsRollback(const Bytes &original, const Bytes &originalSide,
                          const Bytes &current, const Bytes &currentSide) {
  auto converted = MakePlan(original, originalSide);
  try {
    MakePlan(current, currentSide);
    return false;
  } catch (const std::exception &) {
    if ((current == original || current == converted.save) &&
        (currentSide == originalSide || currentSide == converted.sidecar))
      return true;
    throw std::runtime_error(
        "pending retirement differs from both known save pairs");
  }
}
} // namespace stash_retire
