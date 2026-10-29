# LZMA SDK 25.01 (7z decoder only)

The C 7z decoder of Igor Pavlov's LZMA SDK, version 25.01 (2025-08-03), from https://www.7-zip.org/sdk.html
(`https://www.7-zip.org/a/lzma2501.7z`, sha256 `cbc3babd589d971e45971d787ff100be8aaa5eab15b2694497ec3e447009e1f2`).
The files in `C/` are copied unchanged from the SDK's `C/` folder; only the ones the decoder needs are here (7z
archive reader, LZMA / LZMA2, BCJ / BCJ2 / ARM / Delta filters, CRC). No PPMd, no encoder, no multithreading.

License: the LZMA SDK is placed in the public domain by Igor Pavlov (`lzma-sdk.txt`, "LICENSE" section). Used by
`launcher/src/core/sevenzip.cpp` (docs/launcher.md "Installing from the 7z").
