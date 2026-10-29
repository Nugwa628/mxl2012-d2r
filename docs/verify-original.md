# Verify the original v005 archive

Run from this checkout after the owner supplies the ModDB zip:

```powershell
py -3 -I tools/verify_original.py <runs>\download\Median_XL_2012_v005.zip
```

The script uses 7-Zip to extract the archive and supported nested archives or installers; it never executes them. It creates `mxl2012-runs/src-original` and refuses to overwrite it. It writes `mxl2012-runs/original-vs-repack.md`, recording the archive size, MD5 and SHA-256, distribution MPQ/DLL/INI sizes and hashes, and the patch MPQ verdict. A wrong MD5 produces a report and a nonzero exit code. Distribution files are matched case-insensitively by basename across wrapper directories; duplicate names are rejected as ambiguous.

If the MPQ hashes differ, extract each MPQ separately using an appropriate external tool, then rerun against the existing original extraction:

```powershell
py -3 -I tools/verify_original.py <runs>\download\Median_XL_2012_v005.zip --reuse-original --original-mpq-extract C:\path\to\original-extract --repack-mpq-extract <runs>\extract-mpq
```

Supply both extraction directories together. Replace `<runs>` with the runs directory. `MXL2012_RUNS` overrides the default runs directory adjacent to the main checkout (or its worktree directory). MPQ content paths are compared case-insensitively, with sizes and hashes. The script does not extract MPQs or require StormLib. The report marks content comparison as pending when directories are missing. `--original`, `--repack`, `--report`, and `--7zip` override the defaults; see `--help`. Only use extraction directories known to represent the respective MPQs completely.

Run synthetic tests with `py -3 -I -m unittest discover -s tools/tests -p test_verify_original.py`.

## Result (2026-10-28)

`mxl2012-runs/original-vs-repack.md`: the zip matches (md5 `53ae96c95e76062ef67a73845abe41f6`, 168,387,701 bytes);
`patch_d2.mpq` is identical to the repack's (sha256 `5a9da6ea9aa0cf229a011407a1ece89f56652fb7079c4328ffb4e6b7696b1f9b`).
The original holds nothing else but three documentation files; the repack's 11 extra files (PlugY, D2GL, SGD2FreeRes,
D2SE) are not Median's and are not used.

Next step, the asset pack from the original (docs/setup.md step 4, provenance in [source-inventory.md](source-inventory.md)
section 0):

```powershell
py -3 -I tools/mpq_extract.py --src <runs>\src-original --out <runs>\assetpack\assets\median
py -3 -I tools/asset_pack.py build --version 1 --src <runs>\assetpack\assets --out <runs>\assetpack\pack --write-lock
```

`mpq_extract.py` checks the MPQ's sha256 against the value above before it extracts anything.
