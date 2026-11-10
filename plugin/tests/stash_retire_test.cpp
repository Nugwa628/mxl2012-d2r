#include "../src/stash_retire_logic.h"
#include <fstream>
#include <iostream>
#include <iterator>
#ifdef STASH_RETIRE_RUNTIME_TEST
#include "../src/stash_retire.h"
#include <filesystem>
#endif
using stash_retire::Bytes;
Bytes Read(const char *p) {
  std::ifstream f(p, std::ios::binary);
  if (!f)
    throw std::runtime_error("input");
  return Bytes(std::istreambuf_iterator<char>(f), {});
}
int main(int argc, char **argv) {
  try {
#ifdef STASH_RETIRE_RUNTIME_TEST
    if (argc == 3 && std::string(argv[1]) == "--folder") {
      D2RL::PluginContext ctx{};
      RetireStashFolder(&ctx, std::filesystem::u8path(argv[2]).c_str());
      return 0;
    }
#endif
    if (argc == 6 && std::string(argv[1]) == "--recover") {
      std::cout << "rollback="
                << stash_retire::NeedsRollback(Read(argv[2]), Read(argv[3]),
                                               Read(argv[4]), Read(argv[5]))
                << "\n";
      return 0;
    }
    if (argc == 4 && std::string(argv[1]) == "--inspect") {
      auto p = stash_retire::MakePlan(Read(argv[2]), Read(argv[3]), true);
      std::cout << "parsed removed=" << p.removed << "\n";
      return 0;
    }
    if (argc != 5)
      return 2;
    auto p = stash_retire::MakePlan(Read(argv[1]), Read(argv[2]));
    for (auto pair : {std::make_pair(argv[3], p.save),
                      std::make_pair(argv[4], p.sidecar)}) {
      std::ofstream f(pair.first, std::ios::binary);
      f.write(reinterpret_cast<const char *>(pair.second.data()),
              pair.second.size());
    }
    std::cout << "removed=" << p.removed << " charmOrigin=" << p.charmOrigin
              << "\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << "\n";
    return 1;
  }
}
