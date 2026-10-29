# Writes <EXE>.sha256 ("<hash>  <name>", the sha256sum format) next to the built launcher.
file(SHA256 "${EXE}" hash)
get_filename_component(name "${EXE}" NAME)
file(WRITE "${EXE}.sha256" "${hash}  ${name}\n")
message(STATUS "${name} sha256 ${hash}")
