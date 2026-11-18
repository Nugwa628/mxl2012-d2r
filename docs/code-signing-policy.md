# Code signing policy

This page is the code signing policy of the **D2R-XL 2012 Downloader**, the installer of the mod **D2R-XL 2012**
(<https://github.com/Nugwa628/mxl2012-d2r>). It is meant for the project's site and wiki as it is.

The downloader is signed with **Azure Artifact Signing** (Microsoft's managed code signing service, formerly Trusted
Signing). The publisher Windows shows for a signed downloader is the project owner's identity as validated by
Microsoft for that signing account; the certificates are short-lived and issued by Microsoft, and every signature is
timestamped so it stays valid after the certificate expires.

## What is signed

Only the **D2R-XL 2012 Downloader** (`D2R-XL-2012-Downloader.exe`), built from this repository's `launcher/` folder.
Nothing else is signed with this certificate profile: not the D2RLoader plugin, not the mod files, not D2RLoader or other
third-party programs.

Every signed downloader is built from source in this repository (`cmake` + MSVC, docs/launcher.md "Command line and
build") and its unit tests pass before it is signed. `tools/sign_launcher.py` signs a copy of that build and refuses the
result unless it is the same program as the unsigned build (only the signature added) and Windows reports a valid,
timestamped signature. The version resource names the product **D2R-XL 2012**; its FileVersion and ProductVersion are the
same value, the downloader version in `launcher/src/win/app.h`.

Everything in the signed exe is open source: our own code and art (MIT), the LZMA SDK's 7z decoder (public domain),
Roboto Condensed (Apache License 2.0) and Cinzel Decorative (SIL Open Font License 1.1). See [NOTICE.md](../NOTICE.md).

## How a release is signed

1. **Build and test** the downloader from a clean checkout of `main` (the release PC, or the optional CI job below).
2. **Sign**: `tools/artifact_signing.py sign` runs `signtool` with Microsoft's Artifact Signing client (dlib) through
   `tools/sign_launcher.py`, which checks the signed exe as above. Signing needs an Azure sign-in that holds the role
   *Artifact Signing Certificate Profile Signer* on the downloader's certificate profile; nobody else can sign.
3. **Publish**: `tools/publish_release.py --launcher` puts the signed exe and its SHA-256 in the release; the downloader's
   self-update checks that SHA-256.

## Team roles

| Role | Members |
|-|-|
| Committers (authors) | [Nugwa628](https://github.com/Nugwa628) (project owner). Much of the code is written by AI coding agents that work for the owner; their changes are committed to the owner's repository under the owner's account and are the owner's responsibility |
| Reviewers | [Nugwa628](https://github.com/Nugwa628). Every change by anyone else (pull requests) is reviewed by the owner before it is merged |
| Signers | The project owner: only identities the owner gives the Certificate Profile Signer role can sign. Each release is signed on purpose, never by every push |

The owner's Azure account uses multi-factor authentication. No signing secret is stored in this repository.

## Privacy

This program will not transfer any information to other networked systems unless specifically requested by the user or
the person installing or operating it.

What the downloader does on the network, all of it for installing and updating the mod:

- It reads the release channel and manifest from the D2R-XL 2012 download site (`https://files.wyrd.games/mxl2012/`, or
  the site given with `--site`) and downloads the mod's files from there. These are plain HTTPS GET requests; like
  any web request they show the site your IP address and a user agent naming the downloader and its version
  (`D2R-XL-2012-Downloader/<version>`). The site is the project's own download host (served through Cloudflare) and is
  used only to serve the files; no account, no cookies.
- Only when you press **Install D2RLoader** and confirm, it downloads D2RLoader from D2RLoader's official site
  (<https://d2rloader.net>, D2RLoader's own privacy terms apply there).
- **Get D2RLoader**, **Report a problem** and links in messages open your web browser; the downloader sends nothing itself.

It sends no telemetry, no crash reports, no usage statistics and nothing about your PC, your game or your characters. Its
log and settings stay on your PC in `%LOCALAPPDATA%\mxl2012` (see [docs/launcher.md](launcher.md) "Uninstall and
cleanup" to remove them).

## System changes and uninstalling

The downloader runs without administrator rights and changes nothing outside the folders named in
[docs/launcher.md](launcher.md) "Where it writes": the mod folder `<D2R>\mods\mxl2012`, its own data folder, and, only
after you confirm each one, D2RLoader's files (Install D2RLoader), one setting in D2RLoader's config (Default mod) and
moving old copies of our plugin aside (Move plugin). It writes no registry keys, services or scheduled tasks.

**Uninstall** removes the mod folder and offers to remove the downloader's own data folder too
(`--cli uninstall`, then `--cli cleanup`). Your characters and the save copies are kept. The downloader is a single exe:
delete it to finish. The full list is in [docs/launcher.md](launcher.md) "Uninstall and cleanup".

## Reporting a problem

Report a signed file that you think breaks this policy, or a signed file you did not get from this project's releases or
download site, to the project: <https://github.com/Nugwa628/mxl2012-d2r/issues>.

## SignPath Foundation (on hold)

An application to SignPath Foundation's free signing for open-source projects is on hold (owner, 2026-11-17). Its
workflow, artifact configuration and the export into a separate downloader repository stay in this repository, unused:
`downloader-repo/`, `launcher/signpath-artifact-configuration.xml` and `tools/downloader_repo.py`.
