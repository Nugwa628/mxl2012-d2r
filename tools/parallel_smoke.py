#!/usr/bin/env python
"""Run the smoke scenario (game_ctl.py smoke) on several game slots at the same time, all in background mode, and
record the evidence that the user's mouse and focus were left alone.

  py -3 tools/parallel_smoke.py [--slots 2,3,4,5] [--name NAME]

Default: every one of slots 2 to 5 that exists (a missing slot named in --slots is refused before anything starts).

Slot 1 (the owner's own game) runs only when named (--slots 1,2,3); a game running there that this tool did not start
is never touched (game_ctl refuses the start, the slot is reported as not run).
For every slot: take its run lock (game.lock.N; a slot whose lock is held, e.g. by another mod's run, is skipped),
run `game_ctl.py smoke --slot N` with MXL_RUN=<NAME>-sN. Meanwhile
  - tools/input_watch.py samples the real cursor and the foreground window every 25 ms; if the cursor enters a game
    window or a game window becomes the foreground window, all games are stopped at once (abort),
  - tools/resource_sample.ps1 samples CPU, RAM and GPU of the machine and of every game process every few seconds.
Writes <RUNS>\\<NAME>\\parallel-summary.md (game_slots.RUNS) (steps per slot, timings, resources, cursor evidence).

Linux (lane slotcap, 2026-11-21): every game runs on its own private Xvfb display (game_ctl), so there is no cursor
watch; each run's owner focus watch (focus.json) is summed up instead. tools/resource_sample_linux.py samples the
machine and every game each second (--interval) into resources.jsonl. Safety stop: when MemAvailable falls below
--abort-avail-mb (default 4096) or swap use grows by more than --abort-swap-mb (256; 0 = off), all games are stopped (ABORTED).

Shared seats (<locks>/budget.json, <locks>/README.md): each slot lock comes with a seat; --seat-wait S waits up to S
seconds for one (default env MXL_SEAT_WAIT or 0: a slot without a free seat is skipped like a held slot).

Graphics profiles (Linux, lane lowprofile): every slot runs with --profile (default env MXL_PROFILE, else "test", the
low profile), the slots of --visual-slots with "visual" (game_slots.apply_profile writes it into Settings.json at launch).
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import game_slots  # noqa: E402
import resource_sample_linux  # noqa: E402
from input_watch import Watcher  # noqa: E402


def read_steps(run_dir):
    rows = []
    try:
        for ln in open(os.path.join(run_dir, "report.md"), encoding="utf-8"):
            p = [c.strip() for c in ln.strip().strip("|").split("|")]
            if len(p) >= 3 and p[1] in ("PASS", "FAIL"):
                rows.append((p[0], p[1], p[3] if len(p) > 3 else ""))
    except OSError:
        pass
    return rows


def ensure_report(run_dir, slot, out, code):
    """A slot that died before (or without) writing its report still gets a report.md, so the summary can say why."""
    p = os.path.join(run_dir, "report.md")
    if os.path.exists(p):
        return
    os.makedirs(run_dir, exist_ok=True)
    try:
        tail = open(os.path.join(out, f"smoke-s{slot}.out"), encoding="utf-8", errors="replace").read()[-3000:]
    except OSError:
        tail = "(no output file)"
    with open(p, "w", encoding="utf-8") as f:
        f.write(f"# Smoke run {os.path.basename(run_dir)}\n\n"
                f"No step report was written: game_ctl.py smoke exited with code {code}.\n\n"
                f"## Output tail\n\n```\n{tail}\n```\n")


SAMPLING = threading.Event()


def sample_linux(slots, interval, out, samples):
    """Linux: one resource sample per `interval` seconds into `samples` and <out>/resources.jsonl until SAMPLING clears."""
    SAMPLING.set()
    sm = resource_sample_linux.Sampler(slots)
    with open(os.path.join(out, "resources.jsonl"), "a", encoding="utf-8") as f:
        while SAMPLING.is_set():
            time.sleep(interval)
            s = sm.sample()
            samples.append(s)
            f.write(json.dumps(s) + "\n")
            f.flush()


def memory_alarm(samples, avail_mb, swap_mb=256):
    """Why all games must stop now (MemAvailable below `avail_mb`, swap grown by more than `swap_mb`; swap_mb 0: swap is
    not a stop reason), else None."""
    s = samples[-1]
    if s["availMB"] < avail_mb:
        return f"MemAvailable {s['availMB']} MB < {avail_mb} MB"
    if swap_mb and s["swapMB"] - samples[0]["swapMB"] > swap_mb:
        return f"swap use grew {samples[0]['swapMB']} -> {s['swapMB']} MB"
    return None


def linux_summary(active, runs, name, samples):
    """Linux part of the summary: the owner focus watch of every run and the resource figures."""
    lines = ["", "## Owner focus (each run's focus watch on the owner's display; games on private Xvfb displays)", ""]
    for n in active:
        try:
            fw = json.load(open(os.path.join(runs, f"{name}-s{n}", "focus.json"), encoding="utf-8"))
            lines.append(f"- slot {n}: " + ", ".join(f"{k} {fw[k]}" for k in fw if not isinstance(fw[k], (list, dict))))
        except (OSError, ValueError):
            lines.append(f"- slot {n}: no focus.json")
    r = resource_sample_linux.summarize(samples, active)
    if r:
        lines += ["", f"## Resources ({r['samples']} samples)", "",
                  f"- machine CPU {r['cpu_mean']:.0f}% mean, {r['cpu_peak']:.0f}% peak of {samples[0]['cores']} cores; "
                  f"load1 peak {r['load1_peak']:.1f}; MemAvailable min {r['avail_min_mb'] / 1024:.1f} GB; swap peak "
                  f"{r['swap_peak_mb']} MB; VRAM peak {r['vram_peak_mb'] / 1024:.1f} GB, GTT peak {r['gtt_peak_mb'] / 1024:.1f} GB; "
                  f"GPU busy {r['gpu_mean']:.0f}% mean, {r['gpu_peak']:.0f}% peak; Xvfb CPU {r['xvfb_cpu_mean'] / 100:.2f} cores mean"]
        for n, g in r["games"].items():
            lines.append(f"- slot {n}: CPU {g['cpu_mean'] / 100:.2f} cores mean, {g['cpu_peak'] / 100:.1f} peak; PSS "
                         f"{g['pss_peak_mb'] / 1024:.1f} GB peak; VRAM {g['vram_peak_mb'] / 1024:.1f} GB peak, GTT {g.get('gtt_peak_mb', 0) / 1024:.1f} GB peak; {g['seconds']} s running")
    return lines


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slots", default=None, help="comma-separated slot numbers to run (default: those of 2,3,4,5 that exist; slot 1 only by name)")
    ap.add_argument("--name", default=None, help="run name; folder under the runs directory (default: parallel-<time>)")
    ap.add_argument("--seat-wait", type=float, default=None, help="seconds to wait for a free seat (budget.json)")
    ap.add_argument("--stagger", type=float, default=4.0, help="seconds between the launches")
    ap.add_argument("--interval", type=float, default=1.0, help="Linux: resource sample interval in seconds")
    ap.add_argument("--abort-avail-mb", type=int, default=4096, help="Linux: stop every game below this MemAvailable")
    ap.add_argument("--abort-swap-mb", type=int, default=256,
                    help="Linux: stop every game when swap use grows by more than this (0: swap alone never stops a run; "
                         "lane vramcap: with the owner's zram the growth is mostly other programs' idle pages)")
    ap.add_argument("--profile", default=None, choices=game_slots.PROFILES,
                    help="Linux: graphics profile of every slot (default env MXL_PROFILE, else test)")
    ap.add_argument("--vram-mb", default=None,
                    help="Linux: VRAM cap in MB told to every game (DXVK dxgi.maxDeviceMemory; 0 or none: no cap; "
                         "default env MXL_VRAM_MB, else the profile's default, game_slots.VRAM_DEFAULTS)")
    ap.add_argument("--visual-slots", default="", help="Linux: comma-separated slots that run the visual profile instead")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(sys.argv[1:] if argv is None else argv)
    game_slots.require_machine("parallel_smoke")
    slots = ([game_slots.require_present(x, "parallel_smoke") for x in args.slots.split(",")] if args.slots
             else game_slots.present_set())
    if not slots:
        print("no game slot exists (slots 2 to 5 all missing)")
        return 1
    visual = {int(x) for x in args.visual_slots.split(",") if x.strip()}
    profiles = {n: "visual" if n in visual else game_slots.profile_name(args.profile) for n in slots}
    vram = {n: game_slots.vram_mb(profiles[n], args.vram_mb) for n in slots}  # checked before anything starts
    name = args.name or time.strftime("parallel-%Y%m%d-%H%M%S")
    runs = game_slots.RUNS
    out = os.path.join(runs, name)
    os.makedirs(out, exist_ok=True)
    active, notes = [], []
    for n in slots:
        owner = f"{name}-s{n}"
        ok, msg = game_slots.acquire(n, owner, seat_wait=args.seat_wait)
        notes.append(f"slot {n}: {msg}")
        if ok:
            active.append(n)
    print("\n".join(notes), flush=True)
    if not active:
        print("no slot available")
        return 1
    folders = [game_slots.slot_dir(n) for n in active]
    samples = []
    if game_slots.LINUX:
        watcher = sampler = None
        threading.Thread(target=sample_linux, args=(active, args.interval, out, samples), daemon=True).start()
    else:
        watcher = Watcher(os.path.join(out, "input-watch.json"), folders=folders).start()
        # -ExecutionPolicy Bypass applies to this powershell process only; the machine policy is left alone
        sampler = subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                                    os.path.join(HERE, "resource_sample.ps1"),
                                    "-Folders", ",".join(folders), "-Interval", "3"], stdout=subprocess.PIPE, text=True)

        def read_samples():
            for ln in sampler.stdout:
                try:
                    samples.append(json.loads(ln))
                except ValueError:
                    pass

        threading.Thread(target=read_samples, daemon=True).start()
    t0 = time.time()
    procs, ends, outs = {}, {}, {}
    for n in active:
        env = dict(os.environ, MXL_RUN=f"{name}-s{n}", PYTHONIOENCODING="utf-8")
        env.pop("MXL_D2R_GAME", None)
        env["MXL_PROFILE"] = profiles[n]
        if args.vram_mb is not None:
            env["MXL_VRAM_MB"] = str(args.vram_mb)
        outs[n] = open(os.path.join(out, f"smoke-s{n}.out"), "w", encoding="utf-8", errors="replace")
        procs[n] = subprocess.Popen([sys.executable, os.path.join(HERE, "game_ctl.py"), "--slot", str(n), "smoke"], env=env,
                                    stdout=outs[n], stderr=subprocess.STDOUT)
        time.sleep(args.stagger)  # stagger the launches a little so the loaders do not compile at the same instant
    aborted = None
    while len(ends) < len(procs):
        for n, p in procs.items():
            if n not in ends and p.poll() is not None:
                ends[n] = time.time() - t0
        why = None
        if os.path.exists(os.path.join(out, "input-watch.json.abort")) and not aborted:
            why = open(os.path.join(out, "input-watch.json.abort")).read()
        elif game_slots.LINUX and samples and not aborted:
            why = memory_alarm(samples, args.abort_avail_mb, args.abort_swap_mb)
        if why:
            aborted = why
            print("ABORT:", aborted, flush=True)
            for n, p in procs.items():
                p.terminate()
            for n in active:
                subprocess.run([sys.executable, os.path.join(HERE, "game_ctl.py"), "--slot", str(n), "stop"],
                               env=dict(os.environ, MXL_RUN=f"{name}-s{n}"), capture_output=True)
            break
        time.sleep(1)
    wall = time.time() - t0
    cursor = watcher.stop() if watcher else None
    if sampler:
        sampler.terminate()
    SAMPLING.clear()
    codes = {}
    for n in active:
        try:
            procs[n].wait(timeout=30)
        except subprocess.TimeoutExpired:
            procs[n].kill()
            procs[n].wait()
        codes[n] = procs[n].returncode
        outs[n].close()
        ensure_report(os.path.join(runs, f"{name}-s{n}"), n, out, codes[n])
        game_slots.release(n, f"{name}-s{n}")

    lines = [f"# Parallel smoke {name}", "", f"slots {active}, wall time {wall:.0f} s" + (f", ABORTED: {aborted}" if aborted else ""),
             "", "graphics profiles: " + ", ".join(f"slot {n} {profiles[n]}" for n in active),
             "VRAM caps: " + ", ".join(f"slot {n} {vram[n] or 'none'}" + (" MB" if vram[n] else "") for n in active), ""]
    lines += ["## Steps per slot", "", "| Slot | Exit | Time | Steps | Detail |", "|---|---|---|---|---|"]
    for n in active:
        rows = read_steps(os.path.join(runs, f"{name}-s{n}"))
        passed = sum(1 for r in rows if r[1] == "PASS")
        bad = "; ".join(f"{r[0]}: {r[1]} {r[2]}" for r in rows if r[1] != "PASS") or "-"
        lines.append(f"| {n} | {codes[n]} | {ends.get(n, wall):.0f} s | {passed}/{len(rows)} passed | {bad} |")
    if game_slots.LINUX:
        lines += linux_summary(active, runs, name, samples)
        result = {"name": name, "slots": active, "profiles": {n: profiles[n] for n in active}, "vram_mb": {n: vram[n] for n in active}, "wall": wall, "aborted": aborted, "codes": codes,
                  "ends": ends, "steps": {n: read_steps(os.path.join(runs, f"{name}-s{n}")) for n in active},
                  "resources": resource_sample_linux.summarize(samples, active)}
        json.dump(result, open(os.path.join(out, "parallel-result.json"), "w"), indent=1)
        open(os.path.join(out, "parallel-summary.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
        print("\n".join(lines))
        return 2 if aborted else (0 if all(c == 0 for c in codes.values()) else 1)
    c = cursor
    lines += ["", "## Real cursor and focus (every 25 ms)", "",
              f"- samples {c['samples']} over {c.get('seconds')} s, longest gap {c['max_gap_ms']} ms, game windows seen {c['game_windows_seen']}",
              f"- cursor before {c['cursor_first']}, after {c['cursor_last']}, x range {c['x_range']}, y range {c['y_range']}, "
              f"{c['cursor_moves']} samples where it moved (the user's own mouse use)",
              f"- cursor over a game window rectangle: {c['cursor_in_game_window']} samples ({c['cursor_moved_in_game_window']} of them while it moved); "
              f"teleports into a game window: {c['teleports_into_game_window']}; a game window as foreground window: {c['game_foreground']} samples",
              f"- first violation: {c['first_violation'] or 'none'}"]
    lines += ["", "## What the games asked Windows for (plugin trace, calls the harness kept away from the desktop)", ""]
    for n in active:
        trace = os.path.join(game_slots.mod_dir(n), "d2rloader", "plugins", "mxl2012-testharness-trace.log")
        try:
            calls = {}
            for ln in open(trace, encoding="utf-8", errors="replace"):
                for fn in ("NtUserSetCursorPos", "NtUserClipCursor", "NtUserSetForegroundWindow", "NtUserSetActiveWindow"):
                    if ln.startswith(fn + " calls="):
                        calls[fn] = ln.split("calls=")[1].split()[0]
            lines.append(f"- slot {n}: " + ", ".join(f"{k} {v}" for k, v in calls.items()) + " (all answered by the plugin, none reached the system)")
        except OSError:
            lines.append(f"- slot {n}: no trace log")
    if samples:
        cpu = [s["cpu"] for s in samples]
        avail = [s["availMB"] for s in samples]
        gall = [s["gpuAll"] for s in samples]
        lines += ["", "## Resources (3 s samples)", "",
                  f"- machine CPU {sum(cpu) / len(cpu):.0f}% mean, {max(cpu):.0f}% peak ({samples[0]['cores']} logical cores); "
                  f"free RAM min {min(avail) / 1024:.1f} GB; GPU engines sum mean {sum(gall) / len(gall):.0f}%, peak {max(gall):.0f}%"]
        per = {}
        for s in samples:
            for p in s["procs"]:
                per.setdefault(p["pid"], []).append(p)
        for pid, ps in sorted(per.items()):
            lines.append(f"- pid {pid}: CPU {sum(x['cpu'] for x in ps) / len(ps):.0f}% of one core mean ({max(x['cpu'] for x in ps):.0f}% peak), "
                         f"RAM {max(x['ws'] for x in ps)} MB peak, GPU {sum(x['gpu'] for x in ps) / len(ps):.0f}% mean ({max(x['gpu'] for x in ps):.0f}% peak), "
                         f"VRAM {max(x['gpumem'] for x in ps)} MB peak")
        json.dump(samples, open(os.path.join(out, "resources.json"), "w"))
    open(os.path.join(out, "parallel-summary.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 2 if aborted else 0


if __name__ == "__main__":
    sys.exit(main())
