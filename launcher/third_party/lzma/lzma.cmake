# The LZMA SDK's 7z decoder (README.md): MXL_LZMA_SOURCES and MXL_LZMA_INCLUDE for ../../CMakeLists.txt and
# ../../tests/CMakeLists.txt. Compiled into each target (not a library), so each keeps its own C runtime setting.
set(MXL_LZMA_INCLUDE ${CMAKE_CURRENT_LIST_DIR}/C)
set(MXL_LZMA_SOURCES)
foreach(f 7zAlloc 7zArcIn 7zBuf 7zCrc 7zCrcOpt 7zDec 7zStream Bcj2 Bra Bra86 BraIA64 CpuArch Delta Lzma2Dec LzmaDec)
	list(APPEND MXL_LZMA_SOURCES ${MXL_LZMA_INCLUDE}/${f}.c)
endforeach()
if(MSVC)
	set_source_files_properties(${MXL_LZMA_SOURCES} PROPERTIES COMPILE_OPTIONS "/W1")
else()
	set_source_files_properties(${MXL_LZMA_SOURCES} PROPERTIES COMPILE_OPTIONS "-w")
endif()
