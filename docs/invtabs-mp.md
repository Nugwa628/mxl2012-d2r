# invtabs in TCP/IP games

How the invtabs plugin (the tabbed custom player page, item page 6) behaves when one D2R-XL 2012 game hosts a TCP/IP
game and others join it. It covers what wild-healer's plugins do, the protocol and rules we use instead, and the
two-client test rig. Sections 2 and 3 are the design; **section 6 says what the plugin does today**, where it differs
from the design, and how it was proven with two clients.

Code: `invtabs/src/mp_protocol.h` / `.cpp` (pure: messages, handshake, placement and the charm rule; the header lists what
the core calls), tests `invtabs/tests/mp/` (76 checks; `tools/build_plugin.ps1 -Tests` runs them as `invtabs_mp_tests`),
the core's part in `invtabs/src/invtabs.cpp` ("TCP/IP games"), rig `tools/invtabs_mp_checks.py` (tests
`tools/test_invtabs_mp_checks.py`).

Upstream line numbers are from the copies in `mxl2012-runs\invtabs\upstream\plugins\`: `aaa-player-page-host/src/host.cpp`
(3218 lines, "host") and `wild-healers-charm-inventory/src/plugin.cpp` (1084 lines, "charm").

## 1. What upstream sends

### Player Page Host 1.0.2 (host.cpp)

One D2RLoader channel (`NetworkService`, payload at most 224 bytes, rate limited, not on Battle.net):

| what | value | where |
|-|-|-|
| channel id | 1 | host.cpp:1067 |
| compatibility token | `0x5048'4E45'5401'0001` ("PHNET", major 1) | host.cpp:1065 |
| protocol number | 2, inside Hello / Welcome | host.cpp:1066 |
| nonce | random u64 per process; a Welcome carrying our own nonce means "this process is the host" | host.cpp:1063, 1478 |

Messages (packed structs, host.cpp:1072-1105):

| id | direction | content | used for |
|-|-|-|-|
| 1 Hello | joiner to host | protocol, nonce, playerId, count, up to 12 charm rectangles {x,y,w,h} | tells the host where the joiner's charm slots are |
| 2 State | joiner to host, every 500 ms while an area is open (host.cpp:1515-1537) | seq, open, verdict, area, runtimeId, classId | the joiner's own verdict for the item on its cursor |
| 3 Ctrl | joiner to host | seq, runtimeId, x, y, verdict, area | Ctrl+click: put item `runtimeId` at x,y |
| 4 ReqPart | joiner to host, 200-byte parts up to 0x8000 bytes, 10 s timeout (host.cpp:2366-2440) | request body | item create-from-save-bytes, save item, move, destroy, itemsWhere |
| 101 Welcome | host to joiner | protocol, nonce, version text | link up |
| 102 CtrlDone | host to joiner | seq, runtimeId, result | |
| 103 AnsPart | host to joiner | answer parts | request answers |

Flow: on LocalPlayerReady and on GameLeft the link resets (host.cpp:1593-1609, 3166-3175); a 200 ms ticker thread
(host.cpp:1628-1673) calls `connectToHost` up to 30 times (host.cpp:1540-1591), then sends Hello. The host stores the Hello
as it is (host.cpp:1326-1350) and answers Welcome. A joiner click on a reserved area becomes a Ctrl message
(host.cpp:1675-1704, 1612-1623); the host runs it (host.cpp:1286-1324, 1378-1396).

What the host trusts (review `mxl2012-runs\invtabs\review\FINDINGS.md` section 2):

- **Item bytes.** ReqPart "create" hands joiner bytes to the game's save loader `0x43D900` / CreateItem `0x43CD50`
  (host.cpp:2631-2665, natives 2290-2348), with `AllowDuplicateUnique` passed through (host.cpp:2636). A joiner can create any
  item (forging) or keep a copy of one it also keeps elsewhere (duplicating), and a malformed body reaches the save parser
  on the hosting game (crash surface).
- **Rectangles and verdicts.** The Hello carries the joiner's charm rectangles and the host counts charms inside them
  (`PeerCharmsAt`, host.cpp:1241-1254; `HookCharm` host.cpp:854-926). The Ctrl verdict `RemoteAllow` skips the host's own
  item policy (host.cpp:1319); the placement test looks at the top-left cell only (host.cpp:1378-1384, `DestinationOf`
  2561-2584). The playerId in Hello is the joiner's word (host.cpp:1337); with no Hello the host falls back to its own
  slots (host.cpp:893-896).
- **Drops.** A joiner's ordinary drag and drop onto page 6 is attributed by a heuristic (host.cpp:1256-1284).

When one side lacks the plugin: the channel is refused (`UnknownPlugin` / `UnknownChannel`), the joiner logs "the hosting
game refused the connection: <reason>. Page areas can't take items in this game." (`RejectionName` host.cpp:1416,
logged at 1463 and 1578). When the token matches but the protocol number differs, the host does not check it: it logs the
Hello's protocol (host.cpp:1341) and sends Welcome; the joiner keeps the host's number (`HostProtocol`, host.cpp:1486) and
uses item requests only with a protocol-2 host.

### Wild Healer's Charm Inventory (plugin.cpp): why its rule is local-player only

`HookCharm` (plugin.cpp:322-360) answers 0 for a charm of the LOCAL player that is not on page 6; for any other player it
"keeps the game's rule" (plugin.cpp:342-354: `IsLocalPlayer` via the local index `0x8B2D0` and `PlayerUnit` `0x9A480`;
without those lookups the rule covers every player). The reason is the comment at plugin.cpp:436-446: the plugin cannot
know another player's charm area, because each client chooses its own (`reserveArea` with its own rectangles,
plugin.cpp:645-666). The hosting game therefore counts a joiner's charms by the vanilla rule (inventory), while the joiner's
screen shows its own rule: the two can disagree. The CharmsOnly policy (plugin.cpp:616-627) reads the LOCAL player's
cursor, so on the hosting game it judges a joiner's drop by the host's cursor.

## 2. Our protocol

Decisions (coordinator, 2026-11-11): no item requests (create-from-save / save-item / destroy / itemsWhere); the hosting
game decides everything from its own config; a joiner sends nothing beyond a move request; tab rectangles come only from
the toml and the tab table (charm tab pinned at 0,0, no sidecar files).

### Channel

| what | value |
|-|-|
| channel id | 1 (D2RLoader scopes it by our plugin id `invtabs`) |
| compatibility token | `0x494E565441425301` ("INVTABS", major 01); a major change changes the token, so old and new never link |
| protocol | 1 (minor), in Hello / Welcome |
| plugin role | **Shared** (Client + Server + NativeHooks). The core's `invtabs.cpp` currently says `Client \| NativeHooks`; with Shared, D2RLoader records invtabs in the character's plugin history and refuses a TCP/IP join when host and joiner differ in id, version, ABI, scope or flags (SDK README). It also compares a content hash of each shared plugin ("shared plugin changed identity", run 2026-11-11 13:24), which is what we want: the charm rule is server-side |

### Messages (little-endian, exact sizes; a wrong size or out-of-range field is dropped)

| id | direction | bytes | fields |
|-|-|-|-|
| 1 Hello | joiner to host | 26 | protocol u16, tableHash u64, version char[16] (printable ASCII, NUL-terminated) |
| 2 Move | joiner to host | 10 | seq u32, runtimeId u32, kind u8 (1 IntoTab, 2 OutOfPage), tab u8 (< 12; 0 for OutOfPage) |
| 101 Welcome | host to joiner | 27 | protocol u16, verdict u8 (0 Accepted, 1 ProtocolMismatch, 2 TableMismatch), tableHash u64, version char[16] |
| 102 MoveDone | host to joiner | 11 | seq u32, runtimeId u32, result u8 (Moved, NotWelcome, BadMessage, UnknownTab, NotFound, TypeRefused, NoRoom, RateLimited, Failed, NotOnPage), x u8, y u8 |

`tableHash` is FNV-1a 64 over the canonical tab table: count, then per tab its name, rectangle, counts-charms flag and its
item types sorted (`TableHash`). Equal hashes mean the same tabs at the same places taking the same types, so the grid sizes
of both tomls are compared too.

### What the host does with a Move

1. Drop it unless the peer's Hello was Accepted and the peer's rate limiter allows it (8 per second, burst 8).
2. On the game thread: `player = getPeerPlayer(peer)`. The item is looked up among that player's own items by
   `runtimeId` (backpack, cursor, stash, page 6); nothing found: NotFound. The player id is never read from a message.
3. `PlanMove` with the host's own table: the tab must exist and accept one of the item's types (type and Equiv parents,
   from the host's itemtypes); the host picks the first free cell over the item's WHOLE footprint (size from the game's
   item data, `ItemSize 0x371850`) inside that tab, skipping the item itself; OutOfPage needs the item to be on page 6.
4. The move itself goes through D2RLoader's `executeExistingItemTransaction` (CustomPage Exact for IntoTab, Inventory
   Automatic for OutOfPage), the same path as the host's own Ctrl+click; MoveDone carries the result and the cell.

### Drag and drop by a joiner

A joiner's ordinary drag and drop is the game's own item packet to the hosting game. D2RLoader asks the page policy on
the hosting game; it cannot tell which tab the joiner aimed at, so it allows a drop when any tab accepts the item's
types (`AnyTabAccepts`) and refuses the rest. After the move, the host's reconciler (every ~10 frames and after each page
item event, for every player) checks each page-6 item with `Reconcile`: an item straddling two tabs, outside every tab,
or in a tab that does not take its type is moved back to that player's backpack (Automatic), and the eviction is logged.
Until then it gives nothing (charm rule below).

### Charm rule for every player

D2RCore's charm check goes through one thunk, `exe+0x3E2B61C` (`FF 25 7E F6 FF FF`, slot `0x3E2ACA0`), with signature
`int32 (item, unit)` (docs/d2r-addresses.md 22b / 22c). The same slot serves the server's refresh and can-use checks for
every player and the client's display refresh, so one slot wrapper gates both sides. Its call sites are found by three
patterns verified unique in `.text` of build 93847 (each `E8` targets the thunk):

| use | pattern | match | call at |
|-|-|-|-|
| server refresh, charm loop (all players) | `83 F8 01 75 ?? 48 8B D7 48 8B CB E8 ?? ?? ?? ?? 85 C0 74 ?? 33 D2 48 8B CB E8` | 0x470D8F | +11 (0x470D9A) |
| server can-use check | `48 8B D7 48 8B CB E8 ?? ?? ?? ?? 85 C0 74 18 0F B6 8E 06 01 00 00` | 0x4750FC | +6 (0x475102) |
| client refresh, charm loop (display) | `83 F8 01 75 ?? 48 8B D3 48 8B CF E8 ?? ?? ?? ?? 85 C0 74 ?? 33 D2 48 8B CF E8` | 0x1C97D8 | +11 (0x1C97E3) |

All three must reach the same thunk; else the wrapper is not installed and the log says so. The calls sit deep inside
`0x470CA0` / `0x1C9610`, whose entries charmdup hooks; we patch neither those nor `0x36BC50` nor `0x3E2ABB0` (charmdup and
mercequip own them). The wrapper is chained: it saves the slot's previous target and calls it.

Rule (`CharmGateFor`): an item on page 6 (item+0x10 data, data+0x55 == 6) counts only when its whole footprint lies in a
tab with the counts-charms flag (the charm tab); otherwise the answer is 0. Anything else (not on page 6) goes to the
previous target, which applies D2RCore's IsCharmUsable chain and the core's inventory-charm setting. There is no
local-player test: the hosting game applies its own table to every player, and a welcomed joiner has the same table
(equal hash), so its screen agrees with the server.

### Cases

| case | what happens |
|-|-|
| both sides, same version, same tables | Welcome Accepted; Ctrl+click on the joiner sends Move; the host places, counts and reconciles for everyone |
| host with invtabs, joiner without | with the Shared role D2RLoader refuses the join (plugin history mismatch). Were it Client-only: the joiner has no page 6 UI; the host still applies its rule to whatever the joiner's save holds on page 6 (only charm-tab charms count) |
| joiner with invtabs, host without | Shared: the join is refused. Client-only: the channel is refused (UnknownPlugin / UnknownChannel), `JoinerLink::OnRefused`: tabs open and show, our moves are off, and the host (no rule) counts by D2RCore's default |
| other invtabs major version | other token: the channel is refused, as above |
| other protocol minor | Welcome ProtocolMismatch: view-only |
| other grid sizes in the two tomls, or other tab lists | Welcome TableMismatch: view-only on the joiner, and the joiner's console says why. The host's table rules the game; the joiner's screen may show its own (wrong) rectangles, so its charm display can differ until the toml matches |
| a joiner that lies (a tab index it has no right to, another player's item id, an item that does not fit, a flood) | each is refused by the host's own checks: the item must be the peer's own, the tab must accept it, the footprint must fit, 8 moves per second |
| a joiner with page-6 items from another toml or another plugin (orphans) | the reconciler moves them to the backpack (or leaves them where they give nothing when the backpack is full); charmdup asks invtabs whether a page-6 charm counts (review 3.3), so no "page 6 = counts" rule elsewhere |

### What a joiner loses compared with upstream

- Item requests: no create-from-save, save-item, destroy or itemsWhere for a joiner (no Grail On!-style plugin can use the
  page from a joining client). They were a duplication and forging primitive.
- A drop into the wrong tab by drag and drop is not refused at the drop; it bounces back to the backpack after it.
- No tabs at all against a host without invtabs (or another major version): the join is refused with the Shared role.
- Nothing else: Ctrl+click placement, the charm bonus and the display are the same as on the host.

## 3. What the core must add

- Role `Shared` in `invtabs.cpp` (now `Client | NativeHooks`).
- The calls listed at the top of `invtabs/src/mp_protocol.h`: channel registration, Hello on connect, the host's Move job,
  the reconciler tick for every player, the charm slot wrapper, the page policy for joiner drops.
- A harness verb to read another player's stat on the hosting game (`stat plr:<id> <stat>`): today `stat` reads only the
  harness's own player, so the host's server view of a joiner is read on the joiner through `cstat` (the client copy the
  server's stat updates fill).
- charmdup: ask invtabs whether a page-6 charm counts instead of "page 6 = counts" (review 3.3).

## 4. Test rig

`py -3 tools/invtabs_mp_checks.py run --host-slot H --join-slot J [--stage-charminv]` (`preflight` first). Two workers, each
under `mxl2012-runs\tools\heavy_lock.py game invtabs-mp`, each owning its slot lock (a session lock taken before anything
is changed, released after the loader config is back) and doing start, checks and stop in one process; they meet at
file barriers in `work/runs/invtabs-mp-<time>/sync` and either side can abort both. A worker that holds its token waits at
most 10 minutes for the other's, then gives it back. Each worker sets `automatic_port_mapping = false` and
`hosting_check = false` in the slot's `d2rloader.toml` for the run and puts the file back byte for byte (the Multiplayer
dialog otherwise asks the router for a port mapping and probes the port from outside, seen on the 2026-11-11 probe at
11:43 before LAN Only was ticked). Throwaway characters MpHost<nn> / MpJoin<nn>; report.md and screenshots per role.

Scenario `charminv`: joiner in single player makes `x1x` +7 strength (backpack) and `x2x` +3 (moved into CharmInv with
real clicks), reads `stat player 0`, Save and Exit; host makes a character, hosts "mpt<nn>" (Unlisted, LAN Only); joiner
Direct Joins 127.0.0.1 and reads `cstat 0`, then moves the backpack charm into CharmInv and the CharmInv charm back, with
`cstat 0` after each.

### Runs

- 2026-11-11 11:40, probe: slot 2 hosted the LAN-only, unlisted game "mpt1" (MpHostA, Amazon), D2RLoader "TCP/IP hosting is
  using TCP port 4000". Screenshots `work/runs/invtabs-mp-probe-s2/` (menu, mp1, host_form, browse, direct). The joiner
  could not be started: slot 4's mxl2012-core refused startup with its save-cleanup modal ("could not safely retire
  personal stash page 2 ... unknown item stat"; a save of another lane in `mxl2012-s4`; core log 11:51:20), slot 3 was
  locked by another lane.
- 2026-11-11 13:24, `run --host-slot 2 --join-slot 3 --stage-charminv` (run folder `work/runs/invtabs-mp-20261111-132417/`):
  - Single player on the joiner: strength 25, 32 with `x1x` +7 in the backpack, 35 with `x2x` +3 moved into CharmInv.
    Both places count.
  - The host (slot 2, MpHost) hosted on port 4000. The joiner (slot 3, MpJoin) reached the host over 127.0.0.1, and
    D2RLoader on the host refused it: "TCP/IP environment admission denied: client=1 reason=shared plugin changed
    identity="mod:mxl2012-core" expected="8cee3c14..." actual="f24a2245..."", and the joiner got error screen reason 36
    (D2RLoaderEnvironmentMismatch). The two slots run two different mxl2012-core builds of other lanes (same version,
    other bytes). So **two clients on this PC can reach each other**; D2RLoader then compares shared plugins by a
    content hash. For invtabs this means host and joiner need the byte-identical DLL. The tab-table hash is still needed,
    because the two tomls can differ.
  - **Unwanted contact with the online directory.** The Multiplayer dialog remembers its checkboxes between games. The
    probe at 11:40 had left LAN Only ticked, so the rig's blind click turned it off (`host/host_form.png`: Unlisted on,
    LAN Only off). With `automatic_port_mapping = false` there was no router mapping, but the hosting game registered
    with D2RLoader's game directory every 30 s from 13:26:20 to 13:28:33. The directory probed port 4000 from outside and
    answered HTTP 422 game_unreachable. The game was Unlisted and never reachable, and registration stopped when the host
    quit at 13:28:45. The rig now reads the LAN Only box (pixel test, `checkbox_ticked`), clicks it only when it is off,
    reads it again, and creates no game unless it is ticked. It also aborts at once on any "[HOSTING] Host registration"
    line.
  - Clean-up verified: both slots' shared files restored and verified, `d2rloader.toml` restored byte for byte, the staged
    CharmInv removed, both slot locks released, both game tokens free.
- Answered on 2026-11-11 (section 5): the CharmInv joiner result. It needed two slots with the same
  mxl2012-core and drawcap bytes. `preflight` now hashes the DLLs and refuses such a pair. Slots 2 and 3 differ. Slot 4
  still refuses startup (the same save). Slot 1 is the owner's install: it has an older core and no CharmInv, and its
  exception allows no loader-config change, which the rig needs. A coordinator install of one build into two slots
  (`install_mod.py`) unblocks it: `py -3 tools/invtabs_mp_checks.py run --host-slot A --join-slot B --stage-charminv`.

## 5. CharmInv 1.0.1 in TCP/IP games: observed

Released 0.1.19 (`dist/D2R-XL-2012-0.1.19.7z`, sha256 as in SHA256SUMS) put into slots 3 (host) and 4 (joiner) with
`tools/release_install.py`; `preflight` found every shared plugin byte-identical. Unlisted, LAN Only read as ticked before
every game creation, port 4000, router mapping and hosting check off, `d2rloader.toml` restored byte for byte. No
"[HOSTING] Host registration" line in any run (the rig's own watch plus an independent watchdog on the host log). Throwaway
Amazons: MpHost<nn> (level 1) hosts, MpJoin<nn> (level 120) joins. Joiner's charms: x1x Sunstone +7 strength +10 life
(backpack), x2x +3 strength +20 life and Butcher's Tooth A (+10 all attributes) in CharmInv, Tooth B (a second copy) in the
backpack. Run `py -3 tools/invtabs_mp_checks.py run --host-slot 3 --join-slot 4 --scenario full --session invtabs-mp`.

Result, run 8 (`work/runs/invtabs-mp-20261111-164214/`, report.md and screenshots per role; runs 5 and 6 give the same
numbers):

| step | joiner's character sheet | server (host reads the joiner) |
|-|-|-|
| single player set-up | strength 45 (25 + 7 + 3 + 10) | 45, life 3095 |
| joined, x2x and Tooth A in CharmInv | 45, life 3095/3095 | 45, 3095/3095 |
| joiner moves the x1x into CharmInv | 45, 3095/3095 | 45, 3095/3095 |
| joiner moves the x2x out to the backpack | 45, 3095/3095 | 45, 3095/3095 |
| joiner puts Tooth B into CharmInv beside Tooth A | 45, 3095/3095 (B green, +10 once) | 45, 3095/3095 |
| Save and Exit, joined again | 45, 3095/3095 | 45, 3095/3095 |
| single player afterwards | 45; CharmInv: Tooth A, x1x; backpack: x2x, Tooth B | |

- **A joiner's CharmInv works and counts.** The joiner opens the panel with CharmInv's inventory button (the arrow on the
  inventory's left edge, tooltip "Charm Inventory"), places and takes charms, and the hosting server counts the charms
  on the CharmInv page exactly as in single player (strength and life above; life current = maximum all the time). The
  moves and the CharmInv page survive Save and Exit, a second join and single player.
- **The host's own CharmInv** works the same: its +5 charm in the backpack, in CharmInv and back gives strength 30 on its
  sheet each time, life 70/70 (`host/host_sheet_*.png`).
- **Other players' copies are display only and differ.** Another client counts a player's charms by the vanilla rule
  (backpack only): the joiner's client showed the host at 30 / 25 / 30 (charm in the backpack / in CharmInv / back), the
  host's client copy of the joiner went 42 / 35 / 38 / 28 with the joiner's moves while the server stayed at 45. This
  shows only on another player's view (e.g. a party member's stats); combat uses the server.
- **The `charminv` console command does nothing for a joiner** (the console takes the line; CharmInv neither opens nor
  logs). The button works. On the host the command works.
- **Second copy of a unique.** One Butcher's Tooth counts, in CharmInv or the backpack, in a TCP/IP game as in single
  player.

What players of 0.1.19 should be told: CharmInv works in TCP/IP games for host and joiners, and charms on its page count.
Open it with the button on the inventory's left edge; the `charminv` console command only works for the host and in
single player. In the party view another player's stats can look lower than they are while that player keeps charms in
CharmInv.

Rig notes:
- The Multiplayer dialog hosts or joins with the SELECTED character card, not the one just made. Run 1 played two other
  lanes' throwaway characters (slot 3 MxlBarb got an x1x +5 strength charm, slot 4 Slootfour was saved). The rig now
  clicks its own card first.
- In a TCP/IP game every harness read points at the wrong unit. `FindPlayer` returns the first client in the game's
  list, the newest. So on the host every server verb (`stat`, `item`, `items`) acts on the JOINER, and `cstat` (the
  last server verb's unit id) reads the host's client copy of the joiner. On a joiner, `cstat` reads the host's copy
  (id 1). In run 4 the host's `item` command put its charm into the joiner's backpack. The rig uses this: the host
  reads the joiner's server values. The players' own values come from character sheet screenshots, and the host's
  charm is made in its single-player game.
- CharmInv logs "panel is now open" only for its console command. The rig sees the panel by its red close box.
- Background typing of "127.0.0.1" into Direct Join came out wrong (for example "127.70.00.1"). The rig types one
  character at a time and dismisses the error box before the second try.
- Runs 4 to 6 lost throwaway items: in run 4 the panel was closed, so drops landed on the ground, the joiner lost its
  x1x +7 and Tooth B, and it got the host's +5 charm. Runs 5 and 6 skipped the joiner's moves because of the log-only
  panel check.

## 6. What was built (2026-11-12, lane invtabs stage 4)

Only the hosting game changes items. A joined player's tab is either **full** (everything works, the hosting game
decides) or **read-only** (charms can be taken out, nothing can be put in, the reason stands above the charm summary).

### How it works

- **Who is a joined player.** At "character ready" the plugin queues its page scan on the game thread; D2RLoader answers
  `Unavailable` on a client whose game another PC hosts (SDK `threads.h`). That answer is the test; nothing is read from
  the game's memory for it.
- **Link.** The channel (id 1, token `0x494E565441425301`) is registered at load. A joined player connects
  (`connectToHost`, retried every 2 s, at most 30 times, `Busy` included) and says Hello (protocol, table hash, plugin
  version text; again every 3 s, at most 5 times). The hosting game answers Welcome: Accepted when the protocol and the
  table hash are its own. The hash covers every tab's name, place, size and item types and the `inventory_charms`
  setting. The plugin version travels for the log only; it decides nothing. Until Accepted the tabs are read-only;
  a refused channel, another protocol, another table or no answer leave them read-only for that game.
- **Read-only.** The plugin's own grid wrappers refuse every cell while an item is held (`TakeOnly`, the rule of the
  whole-page view), its own item policy refuses, and Ctrl+click sends nothing. Lifting an item out and dropping it in
  the backpack is the game's own move and works. The notice is the first lines of the charm summary
  (`Summary::SetNotice`), in plain words without file names: "The host's charm inventory is set up differently from
  yours. You can take charms out here, but not put them in." (other tab table); "The host does not have this charm
  inventory. ..." (no channel); "The host's charm inventory does not match yours. ..." (other protocol); "Connecting to
  the host's charm inventory. ..." (the first moments of a game). The technical reason is in the log. The `invtabs`
  status line ends with `link local`, `link joined, full`, `link joined, read-only` or
  `link joined, connecting (read-only)`; the hosting game adds `, N joined`.
- **Ctrl+click of a joined player.** Always consumed on the client. Backpack item with a tab shown: Move IntoTab; item
  in the tab: Move OutOfPage. The hosting game (welcomed peer, 8 moves a second) runs it on its game thread:
  `getPeerPlayer`, the item found by `runtimeId` among THAT player's backpack items (IntoTab) or page items (OutOfPage),
  the first free cell of the tab over the whole footprint (`FirstFreeCell`, sizes from the game's item data), then
  `executeExistingItemTransaction` with the tab's type rule (the same path as the host's own Ctrl+click). MoveDone
  carries the result; both logs name it (`refused: the tab does not take this item`, `no room in the tab`, ...).
- **Drag and drop of a joined player.** The game's own request to the hosting game. The area is limited by the joined
  player's own grid wrappers (same plugin, same table: the link is full only then). The hosting game's item policy
  cannot see whose drop it is or which cell it aims at (`ItemPolicyRequest` has neither), so while a welcomed player is
  in the game it applies the type rule of any tab, and no longer the "tab shown on this screen" rules, which would judge
  another player's drop by the host's own screen.
- **The host's own moves** are unchanged: its grid, its policy, D2RLoader's Ctrl+click out of the tab.
- **Charm bonus.** Decided by the hosting game for every player by the same rule as in single player (D2RLoader's page
  charm policy and mxl2012-core's charm area, docs/d2r-addresses.md 22c). Read on the server for the joined player:
  the same strength with the charms in the backpack and in the tab, 7 less while the +7 charm is on the cursor.

### Differences from the design (sections 2 and 3)

| design | built | why |
|-|-|-|
| role Shared | role stays `Client \| NativeHooks` | the plugin has no server part of its own: items move through D2RLoader's item service on the hosting game. The handshake, not the role, tells whether both sides agree |
| a Move may name an item on the cursor or in the stash | backpack (in) and page (out) only | what Ctrl+click can click on |
| reconciler moves wrongly placed items to the backpack | not built | decision 1 of docs/invtabs.md: the plugin never moves an item on its own |
| charm slot wrapper (`CharmGateFor`, three call sites) | not built | the shipped config has one tab, so no page cell of a welcomed player lies outside the charm tab; no game function is hooked for multiplayer at all |
| a drop into a wrong tab bounces back | with several tabs (test configs only) a joined player's drag into the wrong tab is judged by the type rule of any tab | no reconciler; the shipped config has one tab |

Known limits: a joined player leaving is not reported to the plugin, so the hosting game keeps the any-tab type rule
until its game ends (same result with one tab). A changed client could drop a charm on its own page outside the area;
it stays that player's own item, the type rule still holds, and what counts is still the hosting game's rule. A host
without invtabs (or with another major version) was not run: the channel is refused and the tabs are read-only by the
same code path as the table mismatch.

### Proof (slots 2 host and 5 joiner, HD, background input, the same build on both)

`mxl2012-runs\invtabs\stage4\scripts\mp_session.py` locks both slots, installs the build, runs
`py -3 tools/invtabs_mp_checks.py run --host-slot 2 --join-slot 5 --scenario invtabs --session invtabs` and puts main's
developer install back. After every step of the joined player the HOST reads that player's items, cursor and strength on
the server (its server verbs act on the newest player) and takes a screenshot; the saves of both characters are kept at
set-up, after the first game and after the second, with `tools/d2save.py diff` of each pair (`diff-*.txt`).

| run (`mxl2012-runs\invtabs\stage4\runs\`) | scenario | result |
|-|-|-|
| `invtabs-mp-20261112-013307` | the shipped settings on both sides, fresh characters. Joined player: link full; charm dragged to tab cell 2,1; second charm Ctrl+clicked in (first free cell 0,0); dragged out; Ctrl+clicked out; rune by drag (stays on the cursor) and by Ctrl+click (`refused: the tab does not take this item`); held charm clicked on the panel outside the grid (stays on the cursor); both charms in again. Host, with the joined player in the game: the same with its own charm and rune. Both Save and Exit, new hosted game, joined again: every item where it was | 24 of 24 rows PASS |
| `invtabs-mp-20261112-014133` | `--join-char Ifiveseed`: the joined player was saved with CharmInv 1.0.1 (tooth at 0,0, key at 9,2). Items where CharmInv saved them; tooth Ctrl+clicked out and in; rejoin | 16 of 16 PASS |
| `invtabs-mp-20261112-014939` | `--join-char Ifiveseed --join-rows 4`: another tab table on the joined player. Link read-only with the plain notice (`join/join_tab_open.png`); tooth dragged out; drag in refused (stays on the cursor); Ctrl+click in refused; rejoin | 15 of 15 PASS |

These are the runs on the final build; the same three passed on the build before the notice was reworded
(`invtabs-mp-20261111-234403`, `invtabs-mp-20261112-000020`, `invtabs-mp-20261112-003203`). The first read-only run
(`invtabs-mp-20261112-000828`) failed on the rig's own clicks (a 10 x 4 grid starts two rows lower in the panel); the rig
takes the rows into account now. Every scenario was scripted with background input; none needed a hand.
