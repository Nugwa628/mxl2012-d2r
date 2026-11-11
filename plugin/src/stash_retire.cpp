#include "stash_retire.h"
#include "../../launcher/src/core/json.h"
#include "stash_retire_logic.h"
#include <filesystem>
#include <fstream>
#include <iterator>
#include <shlobj.h>
#include <windows.h>
namespace {
namespace fs = std::filesystem;
using stash_retire::Bytes;
Bytes Read(const fs::path &p) {
  std::ifstream f(p, std::ios::binary);
  if (!f)
    throw std::runtime_error("cannot read retirement input");
  Bytes b((std::istreambuf_iterator<char>(f)), {});
  if (b.size() > 16 * 1024 * 1024)
    throw std::runtime_error("oversized retirement input");
  return b;
}
void Write(const fs::path &p, const Bytes &b) {
  HANDLE file =
      CreateFileW(p.c_str(), GENERIC_WRITE, 0, nullptr, CREATE_ALWAYS,
                  FILE_ATTRIBUTE_NORMAL | FILE_FLAG_WRITE_THROUGH, nullptr);
  if (file == INVALID_HANDLE_VALUE)
    throw std::runtime_error("cannot open retirement output");
  DWORD written = 0;
  const bool ok = WriteFile(file, b.data(), static_cast<DWORD>(b.size()),
                            &written, nullptr) &&
                  written == b.size() && FlushFileBuffers(file);
  CloseHandle(file);
  if (!ok)
    throw std::runtime_error("cannot flush retirement output");
}
void Replace(const fs::path &p, const Bytes &b) {
  auto tmp = p;
  tmp += L".stash2-tmp";
  Write(tmp, b);
  if (!MoveFileExW(tmp.c_str(), p.c_str(),
                   MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
    throw std::runtime_error("cannot replace retirement output");
}
void Backup(const fs::path &p, const Bytes &b) {
  if (fs::exists(p)) {
    if (Read(p) != b)
      throw std::runtime_error("retirement backup differs");
  } else
    Write(p, b);
}
void Convert(const fs::path &save, const D2RL::PluginContext *ctx) {
  auto side = save;
  side.replace_extension(L".d2rl");
  auto journal = save;
  journal += L".stash2-pending";
  if (fs::exists(journal)) {
    auto token = Read(journal);
    std::string hash(token.begin(), token.end());
    if (hash.size() != 64 ||
        hash.find_first_not_of("0123456789abcdef") != std::string::npos)
      throw std::runtime_error("invalid retirement journal");
    auto backup = save;
    backup += L".stash2-" + fs::path(hash).wstring();
    auto meta = backup;
    meta += L".d2rl";
    auto a = Read(backup), b = Read(meta);
    stash_retire::MakePlan(a, b);
    if (stash_retire::Hash(a) != hash)
      throw std::runtime_error("retirement backup hash differs");
    if (stash_retire::NeedsRollback(a, b, Read(save), Read(side))) {
      Replace(save, a);
      Replace(side, b);
      ctx->LogInfo("D2R-XL 2012 stash retirement: recovered interrupted "
                   "save/sidecar conversion");
    }
    fs::remove(journal);
  }
  auto a = Read(save), b = Read(side);
  auto p = stash_retire::MakePlan(a, b);
  if (!p.removed)
    return;
  auto hash = stash_retire::Hash(a);
  auto backup = save;
  backup += L".stash2-" + fs::path(hash).wstring();
  auto meta = backup;
  meta += L".d2rl";
  Backup(backup, a);
  Backup(meta, b);
  Write(journal, Bytes(hash.begin(), hash.end()));
  try {
    Replace(save, p.save);
    Replace(side, p.sidecar);
    fs::remove(journal);
  } catch (...) {
    Replace(save, a);
    Replace(side, b);
    fs::remove(journal);
    throw;
  }
  const auto name = save.filename().u8string();
  auto text = "D2R-XL 2012 stash retirement: deleted " +
              std::to_string(p.removed) + " old personal-page-2 item(s) from " +
              std::string(name.begin(), name.end()) +
              "; all other item bytes retained";
  ctx->LogInfo(text.c_str());
}
} // namespace
auto RetireStashPage(const D2RL::PluginContext *ctx,
                     const char *selfPath) noexcept -> bool {
  try {
    fs::path mod =
        fs::u8path(selfPath).parent_path().parent_path().parent_path();
    auto info = Read(mod / (fs::path(ctx->activeMod).wstring() + L".mpq") /
                     L"modinfo.json");
    mxl::Json json;
    std::string error;
    if (!mxl::Json::Parse(std::string(info.begin(), info.end()), json, error) ||
        !json["savepath"].IsString())
      throw std::runtime_error("invalid mod savepath");
    auto relative = fs::u8path(json["savepath"].Str());
    if (relative.empty() || relative.is_absolute() || relative.has_root_name())
      throw std::runtime_error("unsafe mod savepath");
    for (const auto &component : relative)
      if (component == L"..")
        throw std::runtime_error("unsafe mod savepath component");
    PWSTR known = nullptr;
    if (FAILED(SHGetKnownFolderPath(FOLDERID_SavedGames, 0, nullptr, &known)))
      throw std::runtime_error("cannot resolve mod saves");
    fs::path base(known);
    CoTaskMemFree(known);
    auto saves = base / L"Diablo II Resurrected/mods" / relative;
    if (!fs::exists(saves))
      return true;
    RetireStashFolder(ctx, saves.c_str());
    return true;
  } catch (const std::exception &e) {
    ctx->LogWarn(
        (std::string(
             "D2R-XL 2012 stash retirement: scan skipped; saves untouched: ") +
         e.what())
            .c_str());
    return true;
  }
}
void RetireStashFolder(const D2RL::PluginContext *ctx,
                       const wchar_t *folder) noexcept {
  try {
    for (const auto &file : fs::directory_iterator(folder)) {
      if (file.path().extension() != L".d2s")
        continue;
      try {
        if (!file.is_regular_file())
          continue;
        auto side = file.path();
        side.replace_extension(L".d2rl");
        if (fs::exists(side))
          Convert(file.path(), ctx);
      } catch (const std::exception &e) {
        const auto name = file.path().filename().u8string();
        ctx->LogWarn(
            (std::string("D2R-XL 2012 stash retirement: skipped ") +
             std::string(name.begin(), name.end()) +
             "; pair unchanged; do not load this character until repaired "
             "(loader may refuse it, or old page-6 items may appear on the "
             "charm page): " +
             e.what())
                .c_str());
      }
    }
  } catch (const std::exception &e) {
    ctx->LogWarn(
        (std::string("D2R-XL 2012 stash retirement: scan incomplete: ") +
         e.what())
            .c_str());
  }
}
