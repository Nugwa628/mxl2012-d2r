# Download host for D2R-XL 2012 (files.werdegames.com/mxl2012)

Where players' downloaders get the mod from. Owner decision 2026-10-28: D2R-XL 2012 is served from
`https://files.werdegames.com/mxl2012/`, next to the host's existing site (`.../mxl/`), on the same server, the same
DigitalOcean Space and the same Cloudflare Worker, with the same pipeline. What is in the folder and how
the downloader uses it: [release.md](release.md) "Hosting layout".

```
Developer PC --sftp (key, chroot)--> /srv/dl/incoming-mxl2012/<v>/ --dl_ingest.py (systemd, as mxlup)--> /srv/dl/mxl2012/
    --> .sync/wanted --dl_sync.py (rclone)--> Space d2r-xl, prefix mxl2012/ --> Cloudflare Worker --> files.werdegames.com/mxl2012/
                                                     /srv/dl/mxl2012/ <--Caddy--HTTPS-- dl.werdegames.com/mxl2012/ (origin, backup)
```

The uploader's line is slow (about 160 KB/s up), so `tools/publish_release.py` sends only the objects the host lacks, packed
into one 7z; the server unpacks and checks them, builds the players' 7z itself and writes the channel file last. Why SFTP
and not HTTP, how the sync orders its uploads, the cache headers: sections 1 and 8.

**Everything below is for the server's owner. Nothing in this repository touches the server by itself:** the lane that
wrote this changed no server, Space or Cloudflare setting. Section 3 is the list of what to run, in order.

## 1. Design: a second product on an existing host

The existing installation (user `mxlup`, `/opt/mxl-dl/`, `/srv/dl/mxl`, `/srv/dl/incoming`, units `mxl-dl-ingest.*` and
`mxl-dl-sync.*`, Space `d2r-xl` prefix `mxl/`, Worker `d2r-xl-files`) is **not changed in behaviour**. Section 3 step 0
shows what the server really has.

| Piece | Existing site | D2R-XL 2012 (new) | Shared? |
|---|---|---|---|
| Public URL | `files.werdegames.com/mxl/` | `files.werdegames.com/mxl2012/` | host name, yes |
| Origin / backup | `dl.werdegames.com/mxl/` | `dl.werdegames.com/mxl2012/` | host name, yes |
| Site folder | `/srv/dl/mxl` | `/srv/dl/mxl2012` | no |
| Uploads folder | `/srv/dl/incoming` | `/srv/dl/incoming-mxl2012` | no |
| SFTP user, key, chroot | `mxlup`, `mxl_publish`, `/srv/dl` | the same | **yes** |
| `dl_ingest.py` | `/opt/mxl-dl/dl_ingest.py` | the same file, other flags | **yes** (one file, new version) |
| `dl_sync.py` | `/opt/mxl-dl/dl_sync.py` | the same file, other flags | **yes** (no change) |
| systemd units | `mxl-dl-ingest.{service,path,timer}`, `mxl-dl-sync.{...}` | `mxl2012-dl-ingest.{...}`, `mxl2012-dl-sync.{...}` | no |
| Sync state (lock, upload manifest) | `/var/lib/mxl-dl-sync` | `/var/lib/mxl2012-dl-sync` | no |
| rclone config | `/etc/mxl-dl/rclone.conf` (remote `spaces`) | the same file | **yes** |
| Space and its access key | `d2r-xl` (fra1), prefix `mxl/` | the same Space, prefix `mxl2012/` | **yes** |
| Cloudflare Worker | `d2r-xl-files`, serves `/mxl/` | the same Worker, serves `/mxl2012/` too | **yes** (one edit) |
| Caddy | `handle /mxl/*` | one more `handle /mxl2012/*` (optional, backup only) | same site block |

Decisions and why:

- **A separate uploads folder (`incoming-mxl2012`), not a shared `incoming`.** An ingest run takes every `<version>/` folder in
  its uploads folder and publishes it into *its one* site. With a shared folder, the existing site's unit could publish this
  product's upload into that site (both use versions like `0.2.0`; both produce a valid-looking upload). Two folders
  make that impossible; the path unit of each product only watches its own folder. Two further guards: the publisher refuses
  a `dist/` whose manifest is not `mxl2012` (`publish_release.py`, `MOD_FOLDER`), and the server's unit passes
  `--mod-folder mxl2012`, so the ingest refuses a manifest of another product.
- **The same SFTP user `mxlup` and the same key.** The same person publishes both from the same PC; the chroot `/srv/dl`
  already contains both site folders; no `sshd_config` edit, no reload, no new key. A second user (`mxl2012up`) would need its
  own `Match` block, key, a second owner for the new folders and for the ingest/sync units, and rclone.conf readable by both;
  the isolation it buys (a stolen key can't write into the other product) is small next to that, because the same
  person owns both keys. If you want it anyway: section 7, "Separate user".
- **One installed `dl_ingest.py` and `dl_sync.py`, the product chosen by flags.** `dl_sync.py` already takes `--site`,
  `--remote`, `--config` and `--state` (and reads `$STATE_DIRECTORY`): the installed copy is used unchanged for both. The
  earlier `dl_ingest.py` could not serve a second product: it hard-coded the downloader's file name, the
  name of the 7z it builds and the folder `incoming`. The version in this repository adds the flags
  `--incoming`, `--archive-prefix`, `--launcher-name` and `--mod-folder`; **their defaults are the existing site's values**, so
  the existing unit (which passes only `--root /srv/dl`) does exactly what it did. The earlier test suites
  (`test_dl_ingest.py`, `test_publish_release.py`, `test_dl_sync.py`) pass against this file (run 2026-10-28), plus the
  tests in this repository for two products side by side. Installing it replaces the installed copy, so keep a backup (step 2); if
  you would rather not touch that file at all, use a second copy (section 7, "A second copy of the script").
- **The Space and its key are shared.** The key is limited to the bucket, not to a prefix, and `dl_sync.py` only ever lists,
  uploads and deletes below its own `--remote` prefix (`spaces:d2r-xl/mxl2012` is the directory `mxl2012/`, which is not
  inside `mxl/`). The test suite checks that syncing one prefix leaves the other's files, state and deletions alone. The
  name `d2r-xl` is only a name.
- **Separate state folders.** `dl_sync.py` keeps `uploaded.json` (what it uploaded and its sha256) in its state folder and drops
  entries for files its site no longer has. Two sites in one state folder would make each run forget the other's files and
  upload them again (the 7z of a release, hundreds of MB). The mxl2012 unit gets `StateDirectory=mxl2012-dl-sync`, and the
  wrappers in step 6 pass `--state` so that a manual run never uses the existing site's folder by mistake.
- **No new DNS name, no new certificate, no new DigitalOcean key.**

## 2. Names

| What | Value |
|---|---|
| Site root (served) | `/srv/dl/mxl2012` (inside the SFTP chroot: `/mxl2012`) |
| Uploads (not served) | `/srv/dl/incoming-mxl2012` (chroot: `/incoming-mxl2012`; the publisher reaches it as `../incoming-mxl2012` from the site) |
| Publish target | `sftp://mxlup@HOST/mxl2012` (add `:port` when sshd is not on 22) |
| Player 7z | `releases/<v>/D2R-XL-2012-<v>.7z` (`-nodata` for a CI package) |
| Downloader | `launcher/<v>/D2R-XL-2012-Downloader.exe` (+ `.sha256`) |
| Mod folder in the manifest | `mxl2012` |
| Units | `mxl2012-dl-ingest.service/.path/.timer`, `mxl2012-dl-sync.service/.path/.timer` |
| Wrappers | `/usr/local/sbin/mxl2012-dl-ingest`, `/usr/local/sbin/mxl2012-dl-sync` |
| Space prefix | `spaces:d2r-xl/mxl2012` |
| State | `/var/lib/mxl2012-dl-sync` |

## 3. Owner steps

`HOST` is the server (the one behind git.werdegames.com). Run as root unless it says PC (PowerShell on the publishing PC).
Every step says what a good result looks like; stop at the first step that looks different and ask. Steps 0 to 8 and the
Worker (section 4) can be done in one sitting; none of them changes what the existing site's players or units see.

### Hashes of the script versions

| File in this repository | sha256 (the LF text, as committed) | What to do |
|---|---|---|
| `tools/dl_ingest.py` | `d523349d612fa8d7f4e9a4dcc52cef826e935edb7c87d0c20a537312c56f239b` | **install** (step 2) |
| `tools/dl_sync.py` | `50bdfdf9547f2fbd39ddfc8904615a0bffd36399ec677e9ed15ad9c667a470d0` | already installed if the server's copy has this hash (step 3); else install |

Earlier `dl_ingest.py` versions, so you can tell what is on the server now (step 0):
`3a5d3d902de0b1678e1690932f4206bc05448e538491e26feabd4c0ec5c08712` (2026-10-28, names built in),
`fcf4acffb79f9d746a83ff3419381954d6619bce4c2212014e9bf30c47b9ae20` (2026-10-27, before the product flags),
`5bcdd764a3f18e7b05e78ade1188bdbfbd5184e4352fa3977c5389b6f5b68fff` (before the downloader 0.2.0 rename),
`8af022042edd2a5677a6669579cd44df45164613252d85e891e7e17a713781cc` (the first, before the Space sync). All three are
replaced by the new file with no change for the existing site.

The hashes are of the file with Unix line ends; the commands strip `` first, because a copy installed with Windows line
ends (as on the host in October 2026: `7a1d9d99...` for `fcf4acff...`, `d76a723d...` for `50bdfdf9...`) runs the same but hashes differently. A checkout on the Windows PC has Windows line ends, so the steps below
strip the `\r` on the server before hashing. If the file changes later in this repository, take the hash from
`git show main:tools/dl_ingest.py | sha256sum` instead of from this table.

### Step 0. Look (changes nothing)

```sh
ls -ld /srv/dl /srv/dl/mxl /srv/dl/incoming /opt/mxl-dl /etc/mxl-dl /etc/mxl-dl/rclone.conf
for f in /opt/mxl-dl/dl_ingest.py /opt/mxl-dl/dl_sync.py; do printf '%s  ' "$f"; tr -d '' < "$f" | sha256sum | cut -d' ' -f1; done
systemctl list-units 'mxl-dl-*' --all --no-legend
id mxlup
rclone version | head -1
sudo -u mxlup rclone --config /etc/mxl-dl/rclone.conf --s3-no-check-bucket lsf spaces:d2r-xl
```

Good: `/srv/dl` is `root root drwxr-xr-x`; `/srv/dl/mxl` and `/srv/dl/incoming` are `mxlup mxlup`; `/etc/mxl-dl/rclone.conf` is
`-rw-r----- root mxlup`; the first hash is one of the four above; the units `mxl-dl-ingest.path`, `mxl-dl-ingest.timer`,
`mxl-dl-sync.path`, `mxl-dl-sync.timer` are `loaded active`; `id` shows `uid=...(mxlup)`; rclone is 1.59 or newer; the
last command prints `mxl/` (and nothing else yet). Write the hash of `dl_ingest.py` down. Also note the version the existing
site's channel shows now, for the check in step 8:

```sh
curl -s https://files.werdegames.com/mxl/channels/stable.json
```

If a name differs (another folder, other unit names), use the server's names in the rest of this document.

### Step 1. Folders for the new product

```sh
install -d -m 0755 -o mxlup -g mxlup /srv/dl/mxl2012 /srv/dl/mxl2012/.sync /srv/dl/incoming-mxl2012
install -d -m 0750 -o mxlup -g mxlup /var/lib/mxl2012-dl-sync
ls -ld /srv/dl/mxl2012 /srv/dl/incoming-mxl2012 /var/lib/mxl2012-dl-sync
```

Good: three lines, owner `mxlup mxlup`, modes `drwxr-xr-x`, `drwxr-xr-x`, `drwxr-x---`. (`/srv/dl` itself stays `root:root`; no
`sshd_config` change, no reload: the chroot already contains the new folders.)

### Step 2. Install the new `dl_ingest.py`

PC (PowerShell), from a checkout of this repository at the commit that has the file; any admin login:

```powershell
scp tools\dl_ingest.py root@HOST:/root/dl_ingest.py.new
```

Server:

```sh
tr -d '\r' < /root/dl_ingest.py.new > /root/dl_ingest.py.lf
sha256sum /root/dl_ingest.py.lf
```

Good: `d523349d612fa8d7f4e9a4dcc52cef826e935edb7c87d0c20a537312c56f239b  /root/dl_ingest.py.lf`. Anything else: stop.

The new file no longer has the existing product's names built in: it reads them from `dl_ingest.defaults.json` next to
it. Write that file **before** installing the script, with the names the existing site uses now (its site folder, uploads
folder, the archive prefix of its player 7z, its downloader's file name and the older launcher name it still accepts; the
coordinator gives you the values in chat, they are not kept in this repository):

```sh
cat > /opt/mxl-dl/dl_ingest.defaults.json <<'JSON'
{"site": "mxl", "incoming": "incoming", "archive_prefix": "<PREFIX>", "launcher_name": "<PREFIX>-Downloader.exe",
 "legacy_launcher_names": {"<PREFIX>-Downloader.exe": "<PREFIX>-Launcher.exe"}}
JSON
chmod 0644 /opt/mxl-dl/dl_ingest.defaults.json
python3 -I -m json.tool /opt/mxl-dl/dl_ingest.defaults.json
```

Good: the JSON printed back with your names. Without this file the existing units would stop at their next run (no
archive prefix, no downloader name).

```sh
cp -p /opt/mxl-dl/dl_ingest.py /opt/mxl-dl/dl_ingest.py.before-mxl2012
install -m 0755 -o root -g root /root/dl_ingest.py.lf /opt/mxl-dl/dl_ingest.py
sha256sum /opt/mxl-dl/dl_ingest.py
sudo -u mxlup python3 -I /opt/mxl-dl/dl_ingest.py --help | head -3
```

Good: the hash as above, then `usage: dl_ingest.py [-h] [--root ROOT] [--site SITE] [--incoming INCOMING]` as the first
line (the old file has no `--incoming`). Then check the defaults came from the file:

```sh
sudo -u mxlup python3 -I /opt/mxl-dl/dl_ingest.py --help | tr -s ' 
' ' ' | grep -o '(default [^)]*)'
```

Good: four lines, `(default /srv/dl)`, `(default mxl)`, `(default <PREFIX>)` and `(default <PREFIX>- Downloader.exe)` (the
help text wraps the name, hence the space) with your names, not `None`. Each run starts the script anew: the existing units use the new file from their next run,
with their defaults and therefore the same behaviour. To see that, run the existing unit once now:

```sh
systemctl start mxl-dl-ingest.service && journalctl -u mxl-dl-ingest -n 5 --no-pager
```

Good: `Finished ...` / `Deactivated successfully`, no error line (nothing is waiting, so it does nothing).

### Step 3. `dl_sync.py`: the same file, nothing to install if the hash matches

```sh
tr -d '' < /opt/mxl-dl/dl_sync.py | sha256sum
```

If it prints `50bdfdf9547f2fbd39ddfc8904615a0bffd36399ec677e9ed15ad9c667a470d0`, you are done with this step. If it prints
another hash, the server has an older version: install this repository's `tools/dl_sync.py` the same way as in step 2
(`scp`, `tr -d '\r'`, compare the hash, `cp -p` to `dl_sync.py.before-mxl2012`, `install -m 0755 -o root -g root`).
This repository's `dl_sync.py` is deliberately byte-identical to the installed one; **its built-in defaults are the existing
site, Space prefix and state folder**, which is why nothing below runs it without the flags (the wrapper in step 6, the unit in step 5).

### Step 4. The ingest units

```sh
cat > /etc/systemd/system/mxl2012-dl-ingest.service <<'EOF'
[Unit]
Description=D2R-XL 2012 downloads: check and publish uploads in /srv/dl/incoming-mxl2012 (dl_ingest.py)

[Service]
Type=oneshot
User=mxlup
Group=mxlup
UMask=0022
ExecStart=/usr/bin/python3 -I /opt/mxl-dl/dl_ingest.py --root /srv/dl --site mxl2012 --incoming incoming-mxl2012 --archive-prefix D2R-XL-2012 --launcher-name D2R-XL-2012-Downloader.exe --mod-folder mxl2012
Nice=10
IOSchedulingClass=idle
TimeoutStartSec=3h
ProtectSystem=strict
ReadWritePaths=/srv/dl
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
PrivateNetwork=yes
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
RestrictAddressFamilies=AF_UNIX
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallArchitectures=native
EOF

cat > /etc/systemd/system/mxl2012-dl-ingest.path <<'EOF'
[Unit]
Description=D2R-XL 2012 downloads: watch /srv/dl/incoming-mxl2012 for finished uploads

[Path]
PathChanged=/srv/dl/incoming-mxl2012
Unit=mxl2012-dl-ingest.service

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/mxl2012-dl-ingest.timer <<'EOF'
[Unit]
Description=D2R-XL 2012 downloads: look at /srv/dl/incoming-mxl2012 every 15 minutes too (an upload that finished during a run)

[Timer]
OnBootSec=5min
OnUnitInactiveSec=15min
Unit=mxl2012-dl-ingest.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/mxl2012-dl-ingest.service /etc/systemd/system/mxl2012-dl-ingest.path /etc/systemd/system/mxl2012-dl-ingest.timer
systemctl enable --now mxl2012-dl-ingest.path mxl2012-dl-ingest.timer
systemctl start mxl2012-dl-ingest.service && journalctl -u mxl2012-dl-ingest -n 5 --no-pager
```

Good: `systemd-analyze verify` prints nothing; `enable` prints two `Created symlink ...` lines; the journal shows
`Starting mxl2012-dl-ingest.service`, `Deactivated successfully`, `Finished ...` and no line with an error (an empty run
prints nothing itself).

### Step 5. The sync units (created now, switched on after the first release)

The sync refuses an empty site ("no channels/*.json: the site looks empty or unmounted") and would log that error every 30
minutes until something is published, so the units are created now and enabled in section 5.

```sh
cat > /etc/systemd/system/mxl2012-dl-sync.service <<'EOF'
[Unit]
Description=D2R-XL 2012 downloads: mirror /srv/dl/mxl2012 to the DigitalOcean Space, prefix mxl2012/ (dl_sync.py)
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=mxlup
Group=mxlup
UMask=0022
StateDirectory=mxl2012-dl-sync
StateDirectoryMode=0750
ExecStart=/usr/bin/python3 -I /opt/mxl-dl/dl_sync.py --site /srv/dl/mxl2012 --remote spaces:d2r-xl/mxl2012 --config /etc/mxl-dl/rclone.conf
Nice=5
IOSchedulingClass=idle
TimeoutStartSec=6h
ProtectSystem=strict
ReadOnlyPaths=/srv/dl/mxl2012
ReadWritePaths=/srv/dl/mxl2012/.sync
ProtectHome=yes
PrivateTmp=yes
PrivateDevices=yes
NoNewPrivileges=yes
CapabilityBoundingSet=
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectKernelLogs=yes
ProtectControlGroups=yes
ProtectClock=yes
ProtectHostname=yes
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
RestrictNamespaces=yes
RestrictRealtime=yes
RestrictSUIDSGID=yes
LockPersonality=yes
SystemCallArchitectures=native
EOF

cat > /etc/systemd/system/mxl2012-dl-sync.path <<'EOF'
[Unit]
Description=D2R-XL 2012 downloads: mirror to the Space when /srv/dl/mxl2012/.sync/wanted changes (ingest, promote, gc)

[Path]
PathChanged=/srv/dl/mxl2012/.sync/wanted
Unit=mxl2012-dl-sync.service

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/mxl2012-dl-sync.timer <<'EOF'
[Unit]
Description=D2R-XL 2012 downloads: mirror to the Space every 30 minutes too (safety net)

[Timer]
OnBootSec=10min
OnUnitInactiveSec=30min
Unit=mxl2012-dl-sync.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/mxl2012-dl-sync.service /etc/systemd/system/mxl2012-dl-sync.path /etc/systemd/system/mxl2012-dl-sync.timer
```

Good: no output. (`--state` is not on the command line: under systemd the script takes `$STATE_DIRECTORY`, which is
`/var/lib/mxl2012-dl-sync` through `StateDirectory=`.)

### Step 6. Wrappers for your own manual runs

Commands without flags (`dl_sync.py --check`) work on the existing site. For this product, always use these two, so
that nobody runs the script on the wrong site, prefix or state folder:

```sh
cat > /usr/local/sbin/mxl2012-dl-sync <<'EOF'
#!/bin/sh
# D2R-XL 2012 only: its site, Space prefix and state folder (the script's own defaults are the existing site's).
exec sudo -u mxlup /usr/bin/python3 -I /opt/mxl-dl/dl_sync.py --site /srv/dl/mxl2012 --remote spaces:d2r-xl/mxl2012 --config /etc/mxl-dl/rclone.conf --state /var/lib/mxl2012-dl-sync "$@"
EOF
cat > /usr/local/sbin/mxl2012-dl-ingest <<'EOF'
#!/bin/sh
# D2R-XL 2012 only: its site and uploads folder.
exec sudo -u mxlup /usr/bin/python3 -I /opt/mxl-dl/dl_ingest.py --root /srv/dl --site mxl2012 --incoming incoming-mxl2012 --archive-prefix D2R-XL-2012 --launcher-name D2R-XL-2012-Downloader.exe --mod-folder mxl2012 "$@"
EOF
chmod 0755 /usr/local/sbin/mxl2012-dl-sync /usr/local/sbin/mxl2012-dl-ingest
mxl2012-dl-ingest; echo "exit $?"
mxl2012-dl-sync --dry-run; echo "exit $?"
```

Good: the ingest prints nothing and `exit 0`; the dry run prints
`error: /srv/dl/mxl2012 has no channels/*.json: the site looks empty or unmounted; nothing done` and `exit 1` (right for an empty
site; it proves the script found its site and its rclone, and wrote nothing). If it prints a rclone error instead,
`/etc/mxl-dl/rclone.conf` is not readable by `mxlup` (step 0).

### Step 7. Caddy (the backup origin `dl.werdegames.com/mxl2012/`, optional)

Players read the Space, not this; `dl.werdegames.com` is the origin, the fallback (`--site https://dl.werdegames.com/mxl2012/`) and
what `publish_release.py verify` can check without the Space. Add these lines **inside the existing `dl.werdegames.com { ... }`
block**, next to the existing `header /mxl/...` and `handle /mxl/*` lines and before the final catch-all `handle { respond 404 }`:

```
	header /mxl2012/objects/* Cache-Control "public, max-age=31536000, immutable"
	header /mxl2012/channels/* Cache-Control "no-cache"
	header /mxl2012/releases/* Cache-Control "public, max-age=3600"
	header /mxl2012/launcher/* Cache-Control "public, max-age=3600"
	header /mxl2012/assets/* Cache-Control "public, max-age=3600"

	handle /mxl2012/* {
		@hidden path_regexp hidden (?:/\.|\.part-[0-9a-z]+$)
		respond @hidden 404
		file_server
	}
```

(The block's `root * /srv/dl` is already set; `/mxl2012/...` is the folder `/srv/dl/mxl2012`. `handle /mxl/*` does not match
`/mxl2012/...`, so the existing rules are unaffected. `/srv/dl/incoming-mxl2012` is not under any `handle`, so it answers 404.)

```sh
caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy
curl -sI https://dl.werdegames.com/mxl2012/channels/stable.json | head -1
curl -sI https://dl.werdegames.com/mxl/channels/stable.json | head -1
```

Good: `Valid configuration`; then `HTTP/2 404` for mxl2012 (nothing published yet) and `HTTP/2 200` for the existing site's channel.

### Step 8. The existing site is as before

```sh
systemctl is-active mxl-dl-ingest.path mxl-dl-ingest.timer mxl-dl-sync.path mxl-dl-sync.timer
curl -s https://files.werdegames.com/mxl/channels/stable.json
sudo -u mxlup python3 -I /opt/mxl-dl/dl_sync.py --check      # the existing site's check, with its defaults
```

Good: four times `active`; the same channel version as in step 0; the check ends with `the Space matches the site`.

## 4. Cloudflare Worker, DigitalOcean Space, DNS (owner, in the consoles)

**DNS: nothing.** `files.werdegames.com` and `dl.werdegames.com` exist; the Worker is attached to `files.werdegames.com` as a
custom domain, which covers every path.

**DigitalOcean Space: nothing to create or change.** The Space `d2r-xl` has no folders to make (the prefix `mxl2012/`
appears with the first upload); the access key in `/etc/mxl-dl/rclone.conf` is limited to the bucket, not to a prefix, so it
already covers `mxl2012/`. File listing stays Restricted. `dl_sync.py` sets the public-read ACL and the headers on every
file it uploads, as for the existing site.

**Cloudflare Worker `d2r-xl-files`: one edit.** The Worker serves GET and HEAD only, and only paths under
`/mxl/` without dot segments; it forwards them to `https://d2r-xl.fra1.digitaloceanspaces.com<path>`. Until it also accepts
`/mxl2012/`, `files.werdegames.com/mxl2012/...` answers 404 even after the sync. The Worker's source lives only in the
Cloudflare dashboard (it is not in this repository, and this lane could not read it), so this is the change to make there:

1. Workers & Pages, `d2r-xl-files`, **Edit code**. Find the place that tests the path prefix `/mxl/` (probably
   `pathname.startsWith("/mxl/")` or a regular expression such as `^/mxl/`).
2. Replace that test by one that accepts both prefixes, and leave everything else (methods, dot-segment rule,
   forwarded headers, 403-to-404, `cacheEverything`) alone:

   ```js
   const SITE_PREFIXES = ["/mxl/", "/mxl2012/"];                 // one entry per product folder in the Space
   const inSite = (p) => SITE_PREFIXES.some((prefix) => p.startsWith(prefix));
   // ... where the code had  p.startsWith("/mxl/")  use  inSite(p)
   ```

   Keep the match on the **trailing slash**: `/mxl2012x/...` must stay a 404 and `/mxl/` must not start matching
   `/mxl2012/...` by accident (it does not: `"/mxl2012/".startsWith("/mxl/")` is false).
3. **Save and deploy.** If the Worker is a Route (`files.werdegames.com/mxl/*`) instead of a custom domain, add the route
   `files.werdegames.com/mxl2012/*` for the same Worker.
4. Check from the PC, before anything is published (all four are about the Worker's own rules; the Space has no `mxl2012/` yet):

```powershell
curl.exe -sI https://files.werdegames.com/mxl/channels/stable.json | findstr /i "HTTP"      # 200, as before
curl.exe -sI https://files.werdegames.com/mxl2012/channels/stable.json | findstr /i "HTTP"  # 404 (no file yet) - not 403/1xxx
curl.exe -sI https://files.werdegames.com/mxl2012x/channels/stable.json | findstr /i "HTTP" # 404
curl.exe -sI https://files.werdegames.com/mxl2012/.sync/status.json | findstr /i "HTTP"     # 404
```

The first check that tells the Worker edit apart from "no file yet" comes in section 5, after the first sync. Cloudflare's cache
rules or configuration rules are scoped to the host name `files.werdegames.com`, not to `/mxl/`, so they apply to both
products (if you find a rule that names the path `/mxl/*`, add `/mxl2012/*` to it). The zone's Browser Cache TTL note in
section 8 applies to both.

## 5. First publish and switching the sync on

From the PC, with `dist/` made by `tools/package_release.py` (docs/release.md; 7-Zip installed), or the checked routine
`bash tools/release.sh <version> --channel test` which does all of this and the checks (docs/release.md "Making a release").
For the very first run a CI-style package (`package_release.py --no-data --plugin <dll>`) is enough to prove the host:

```powershell
$t = "sftp://mxlup@HOST/mxl2012"          # add :port when sshd is not on 22
$k = "$HOME\.ssh\mxl_publish"
sftp -i $k mxlup@HOST                      # sftp> ls /   shows  incoming  incoming-mxl2012  mxl  mxl2012      (then: bye)
py -3 tools/publish_release.py list --target $t --identity $k
py -3 tools/publish_release.py publish --version 0.1.0 --channel test --target $t --identity $k --allow-incomplete   # --allow-incomplete only for a --no-data package
```

Good: `list` prints `channel stable  (none)` and `channel test    (none)` (and `incoming ...` lines only if an upload waits);
`publish` ends with `uploaded in N s. The server checks it and publishes 0.1.0 on channel test (tools/dl_ingest.py, journalctl -u mxl2012-dl-ingest); `list` shows it once done`.

Server, a minute or a few later:

```sh
journalctl -u mxl2012-dl-ingest -n 20 --no-pager
ls /srv/dl/mxl2012 /srv/dl/mxl2012/channels /srv/dl/incoming-mxl2012
cat /srv/dl/mxl2012/channels/test.json
```

Good: lines `0.1.0: checking the upload in /srv/dl/incoming-mxl2012/0.1.0`, `... objects in objects-....7z, N new on the host`,
`0.1.0: D2R-XL-2012-0.1.0-nodata.7z built (...)`, `0.1.0: channel test -> 0.1.0`, `0.1.0: published (N files); incoming-mxl2012/0.1.0 removed`; the
site holds `channels  objects  releases  launcher` (launcher only if one was published); `incoming-mxl2012` is empty;
`test.json` names version 0.1.0. A refusal is an error line with the reason, and `/srv/dl/incoming-mxl2012/0.1.0/REFUSED`;
the upload stays for a look (`mxl2012-dl-ingest --retry 0.1.0` tries it again).

Now switch the sync on and run it once (this is the first upload to the Space, below the prefix `mxl2012/` only):

```sh
mxl2012-dl-sync --dry-run
systemctl enable --now mxl2012-dl-sync.path mxl2012-dl-sync.timer
systemctl start mxl2012-dl-sync.service
journalctl -u mxl2012-dl-sync -n 30 --no-pager
mxl2012-dl-sync --check
mxl2012-dl-sync --check --full
```

Good: the dry run says `site N files, Space 0: N to upload (X MB), 0 to delete (dry run)` and `would upload ...` lines, never a
delete. The service ends with `done: N uploaded (X MB), 0 deleted`. `--check` ends with
`check: N files on the site, N on the Space, M compared by sha256: the Space matches the site`; `--full` the same after hashing
everything once. Then:

```powershell
curl.exe -sI https://files.werdegames.com/mxl2012/channels/test.json | findstr /i "HTTP cache-control content-type cf-cache-status"
#   200, cache-control: no-cache, content-type: application/json, cf-cache-status: REVALIDATED / EXPIRED / MISS / DYNAMIC (never a stale HIT)
curl.exe -sI https://files.werdegames.com/mxl2012/.sync/status.json | findstr /i "HTTP"       # 404: dot files are never uploaded
curl.exe -sI https://files.werdegames.com/mxl/channels/stable.json | findstr /i "HTTP"        # existing site still 200
py -3 tools/publish_release.py verify --url https://files.werdegames.com/mxl2012/ --channel test
py -3 tools/publish_release.py verify --url https://dl.werdegames.com/mxl2012/ --channel test    # the backup origin (step 7)
py -3 tools/publish_release.py list --target $t --identity $k      # last line: Space sync: ok at ...
```

Good: `verify` ends with `N of N objects verified`, `Range requests: ok (206)`, `<the 7z>: sha256 ok`. The 200 on `channels/test.json`
is also the proof that the Worker edit works (it was 404 before, section 4). Only then promote:

```powershell
py -3 tools/publish_release.py promote 0.1.0 --channel stable --target $t --identity $k        # a --no-data package is refused for stable
```

and tell the coordinator the root URL works (`https://files.werdegames.com/mxl2012/` is already the downloader's default,
`launcher/src/win/app.h`).

## 6. Day to day

```sh
journalctl -u mxl2012-dl-ingest -n 50 --no-pager               # what the last ingests did; refusals show as errors
journalctl -u mxl2012-dl-sync -n 50 --no-pager
ls -la /srv/dl/incoming-mxl2012                                # uploads waiting, or refused (with a REFUSED file)
cat /srv/dl/incoming-mxl2012/<v>/REFUSED                       # why
mxl2012-dl-ingest --retry <v>                                  # try a refused upload again
mxl2012-dl-sync                                                # a sync by hand (the path unit and the 30-minute timer do it)
mxl2012-dl-sync --check [--full]                               # compare the Space with the site
cat /srv/dl/mxl2012/.sync/status.json                          # the last sync run
```

On the PC: `publish_release.py list | gc --keep 3 [--dry-run] | promote` as in release.md. A refused upload is also reported by the
next `publish` of that version; `publish --force` deletes it there and uploads again. Do not run `gc` while an upload waits
in `incoming-mxl2012/` (it could delete objects that upload counts on; the ingest would then refuse it with "objects the
host does not have", and publishing again fixes it).

- **Disk:** one 7z per kept release plus the objects of all kept releases (shared by versions), plus room for one upload and
  the 7z being built, on top of the existing site's.
- **Backup:** the site folder is rebuildable from `dist/` of each release (7z, manifest); keep those. The Space is rebuildable
  from the site: `systemctl start mxl2012-dl-sync` (after a big cleanup once by hand: `mxl2012-dl-sync --allow-mass-delete`).
- **Rolling back a release:** `promote <older version> --channel stable` (the older release must still be on the host).
- **Failures of the sync:** it exits 1 with the error in the journal and in `status.json` (`publish_release.py list` shows
  `Space sync: FAILED at ...: <error>`), and is retried by the next trigger or the timer. It never deletes an object a
  release on the site uses, and never more than half the Space at once without `--allow-mass-delete`.
- **Updating a script:** copy it again as in step 2; no restart (every run starts the file anew). `dl_sync.py` and
  `dl_ingest.py` are shared with the existing site: after a change, both sites' tests must pass, and the installed copy
  should stay the same file for both.

## 7. Undoing it, and the alternatives

**Remove D2R-XL 2012 from the server** (the existing site is not involved):

```sh
systemctl disable --now mxl2012-dl-ingest.path mxl2012-dl-ingest.timer mxl2012-dl-sync.path mxl2012-dl-sync.timer
rm /etc/systemd/system/mxl2012-dl-ingest.* /etc/systemd/system/mxl2012-dl-sync.* /usr/local/sbin/mxl2012-dl-ingest /usr/local/sbin/mxl2012-dl-sync
systemctl daemon-reload
# the data, only when you are sure: /srv/dl/mxl2012, /srv/dl/incoming-mxl2012, /var/lib/mxl2012-dl-sync, the Space prefix mxl2012/
```

The new `dl_ingest.py` can stay (with its defaults it behaves as before); to go back anyway:
`cp -p /opt/mxl-dl/dl_ingest.py.before-mxl2012 /opt/mxl-dl/dl_ingest.py`.

**A second copy of the script** (no change at all to the installed file): put this repository's `dl_ingest.py` at
`/opt/mxl2012-dl/dl_ingest.py` (and `dl_sync.py` at `/opt/mxl2012-dl/dl_sync.py`, if you also want those apart) instead of step 2,
and use that path in the two `ExecStart=` lines and the wrappers. Everything else is the same. The price is two files to keep
in step when the pipeline changes.

**Separate user** (`mxl2012up`): a second `Match User` block in `sshd_config` (same options as `mxlup`'s, its own
`authorized_keys.d/mxl2012up` with its own `restrict ssh-ed25519 ...` key), the folders `/srv/dl/mxl2012` and
`/srv/dl/incoming-mxl2012` owned by it, `User=`/`Group=` of the four service units, a group that can read
`/etc/mxl-dl/rclone.conf`, and `scp`/publish with that user and key. The chroot `/srv/dl` would still contain the existing site's
folders, so for real separation each user needs its own chroot (`/srv/dl-mxl2012`), which moves every path in this
document. Not recommended unless somebody else will publish D2R-XL 2012.

## 8. Reference

### What `dl_ingest.py` does

(`tools/dl_ingest.py`; details also in release.md "Publishing".) It checks an upload in the uploads folder, moves its
objects into `<site>/objects/`, builds `releases/<v>/D2R-XL-2012-<v>.7z` from the objects, writes the release, the downloader
and the channel file (last), then deletes the upload. Anything that fails a check is refused and left in place with a
`REFUSED` file. It takes a lock (two starts at once are harmless), keeps its scratch files inside the upload folder (so it
does not trigger its own path unit), and after publishing writes `<site>/.sync/wanted`, which starts the sync. It has no
network and writes nothing outside `/srv/dl`. Flags for a product (the defaults are the existing site's values):

| Flag | D2R-XL 2012 | Default | Meaning |
|---|---|---|---|
| `--site` | `mxl2012` | `mxl` | the served folder under `--root` |
| `--incoming` | `incoming-mxl2012` | `incoming` | the uploads folder under `--root` (must differ from the site) |
| `--archive-prefix` | `D2R-XL-2012` | the existing site's | name of the 7z it builds: `<prefix>-<v>.7z` |
| `--launcher-name` | `D2R-XL-2012-Downloader.exe` | the existing site's | the only exe name an upload may carry |
| `--mod-folder` | `mxl2012` | none (any) | refuse a manifest whose `modFolder` is another |

### What `dl_sync.py` does

It mirrors `<site>` to `<remote>` (rclone), in an order in which a player never sees a channel that points at something the
Space does not have yet: objects first, then releases (7z, notes, sums), launcher, assets, the release manifests, **the
channel files last**, and deletions (what `gc` removed) only after all of that went through, never an object a release on
the site still uses, and never more than half the Space at once without `--allow-mass-delete`. Only new or changed files go
up (objects: by name and size; other files: by sha256 against `<state>/uploaded.json`). The JSON files are copied into
`<state>/stage` when a pass starts, so a channel the ingest rewrites during the pass cannot reach the Space before its
objects. Every file gets the public-read ACL and these headers (the same as Caddy's):

| Prefix | Cache-Control | Content-Type |
|---|---|---|
| `objects/` | `public, max-age=31536000, immutable` | `application/octet-stream` |
| `channels/` | `no-cache` | `application/json` |
| `releases/`, `launcher/`, `assets/` | `public, max-age=3600` | by extension: `.json` application/json, `.7z` application/x-7z-compressed, `.exe` application/octet-stream, `.md` text/markdown, `SHA256SUMS` / `.sha256` text/plain |

Never uploaded: dot files and folders (`.sync/`), temp files (`*.part-*`), anything outside those five folders. The ingest unit
keeps `PrivateNetwork=yes`: it only writes the trigger file; the network belongs to the sync unit. `publish_release.py promote`,
`gc` and an `--assets` upload write the same trigger file over SFTP.

### Caddy notes

- CORS is not needed (the downloader is a program). No `Access-Control-*` headers.
- Objects have no file extension, so Caddy sniffs their type; if `publish_release.py verify --url https://dl.werdegames.com/mxl2012/`
  shows `Range requests` failing or a `Content-Encoding` on a 206 answer, drop the `text/*` line from the site block's
  `encode ... match`: resumable downloads win over a few MB.
- `header` also stamps error answers, so a request for an object that is not uploaded yet gets `immutable` on its 404; the
  downloader only asks for objects a published manifest names, so this only matters for a browser or a CDN.

### Stale channels, purging by hand

Cloudflare follows the origin's `Cache-Control`: objects are cached for a year (they never change), releases / launcher /
assets for an hour, and `channels/*.json` (`no-cache`) are revalidated on every request, so a new channel version shows at once,
and the downloader's sha256 check of the manifest catches anything half-updated. If a channel ever shows an old version after
`list` says the sync is done (compare `curl.exe -s https://files.werdegames.com/mxl2012/channels/stable.json` with the same path on
dl.werdegames.com), purge by hand: Cloudflare, Caching, Configuration, Purge Cache, Custom purge, URLs
`https://files.werdegames.com/mxl2012/channels/stable.json` and `.../test.json`. A `publish --force` of an existing version
rewrites files under `releases/<v>/`: purge those URLs the same way (or wait an hour).

### The Worker, and why it exists

A proxied CNAME to the Spaces CDN fails (error 1014: DigitalOcean's CDN runs on Cloudflare itself) and a grey-cloud record would
show players the Cloudflare Origin CA certificate. So the Worker `d2r-xl-files` (free plan, custom domain
`files.werdegames.com`) fetches `https://d2r-xl.fra1.digitaloceanspaces.com<path>`, which is not behind Cloudflare: GET and HEAD
only, only the product folders, no dot segments; it forwards `Range`, `If-None-Match`, `If-Modified-Since`; it fetches with
`cf: { cacheEverything: true }` so caching follows the origin's `Cache-Control`; a 403 from the Space (missing file, listing
restricted) becomes a 404; the `x-amz-*` headers are dropped. Cloudflare's zone **Browser Cache TTL** (4 h) rewrites the
`Cache-Control` that clients see (e.g. `max-age=14400` on channels); the edge still revalidates them, and the downloader (WinHTTP)
keeps no HTTP cache, so this only affects browsers. To pass the origin's headers through, set Caching, Configuration, Browser
Cache TTL to "Respect Existing Headers" (zone-wide, so it also affects the existing site).

### Offline test of the same layout, no server

A folder `X` with `X/mxl2012` and `X/incoming-mxl2012`: `publish --target dir:X/mxl2012`, then
`py -3 tools/dl_ingest.py --root X --site mxl2012 --incoming incoming-mxl2012 --archive-prefix D2R-XL-2012 --launcher-name D2R-XL-2012-Downloader.exe --mod-folder mxl2012`,
`py -3 tools/serve_dir.py X/mxl2012`, then `verify --url http://127.0.0.1:<port>/`. `tools/test_dl_ingest.py` and
`tools/test_publish_release.py` do exactly this, including a second product (`X/mxl`, `X/incoming`) in the same root.
