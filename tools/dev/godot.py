"""Run Godot for this project with one run at a time (an exclusive lock, so parallel jobs queue), a hard timeout, and
the log saved next to the screenshots.

usage: python3.11 tools/dev/godot.py [--timeout S] [--log FILE] -- <godot args...>
  e.g. python3.11 tools/dev/godot.py -- --headless --path . --import
       python3.11 tools/dev/godot.py --timeout 400 -- --path . -- autotest=convo ids=toma shots=ui1
Exit code: Godot's; 124 on timeout; 65 when a script failed to parse or load (see below). Prints the log's
SCRIPT ERROR / ERROR lines at the end.

A scene whose script fails to parse still opens its window, which then stays black and holds the engine lock
until the timeout. So once the log shows "Parse Error" or "Failed to load script", the run is stopped a few seconds
later (time for the rest of the error to be logged) and exits 65. Import, export, editor and --check-only runs are
left alone: they report such errors and carry on by design.
"""
import fcntl, os, subprocess, sys, time

GODOT = os.path.expanduser("~/Applications/godot/Godot.app/Contents/MacOS/Godot")
# inside the project, so every run shares the same lock file whatever its temp directory is
LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", ".engine.lock")
FATAL = ("Parse Error", "Failed to load script")
NO_WATCH = ("--import", "--check-only", "-e", "--editor", "--export-release", "--export-debug", "--export-pack")
GRACE = 4.0


def _stop(p):
    """SIGTERM the run's process group, SIGKILL it if it is still there after 3 s."""
    for sig in (15, 9):
        try:
            os.killpg(p.pid, sig)
        except ProcessLookupError:
            break
        try:
            p.wait(timeout=3)
            break
        except subprocess.TimeoutExpired:
            pass
    p.wait()


def _wait(p, log, timeout, watch):
    """Wait for Godot; returns (exit code, why it was stopped or None)."""
    t_end = time.time() + timeout
    pos, tail, fatal_at = 0, "", None
    while True:
        try:
            return p.wait(timeout=0.5), None
        except subprocess.TimeoutExpired:
            pass
        now = time.time()
        if now >= t_end:
            try:
                os.killpg(p.pid, 9)
            except ProcessLookupError:
                pass
            p.wait()
            return 124, "timeout"
        if watch and fatal_at is None:
            with open(log, errors="replace") as f:
                f.seek(pos)
                chunk = f.read()
                pos = f.tell()
            tail = (tail + chunk)[-8192:]  # an error line can arrive split across two reads
            if any(s in tail for s in FATAL):
                fatal_at = now
        if fatal_at is not None and now - fatal_at >= GRACE:
            _stop(p)
            return 65, "script error"


def main():
    argv = sys.argv[1:]
    timeout, log = 600, None
    while argv and argv[0] != "--":
        if argv[0] == "--timeout":
            timeout = float(argv[1]); argv = argv[2:]
        elif argv[0] == "--log":
            log = argv[1]; argv = argv[2:]
        else:
            break
    if argv and argv[0] == "--":
        argv = argv[1:]
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    log = log or os.path.join(root, "tools", "out", "godot_last.log")
    os.makedirs(os.path.dirname(log), exist_ok=True)
    # only Godot's own options count (anything after a second "--" is passed to the game's scripts)
    own = argv[:argv.index("--")] if "--" in argv else argv
    watch = not any(a in NO_WATCH for a in own)
    with open(LOCK, "w") as lk:
        t0 = time.time()
        fcntl.flock(lk, fcntl.LOCK_EX)
        waited = time.time() - t0
        if waited > 1:
            print(f"[godot.py] waited {waited:.0f} s for another Godot run", flush=True)
        with open(log, "w") as out:
            # its own process group, so a timeout kills this run and nothing else (a pkill on the app's path
            # would also kill an open Godot editor)
            p = subprocess.Popen([GODOT] + argv, cwd=root, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
            code, why = _wait(p, log, timeout, watch)
    lines = open(log, errors="replace").read().splitlines()
    errs = [l for l in lines if "SCRIPT ERROR" in l or l.startswith("ERROR") or "Parse Error" in l]
    for l in lines:
        if l.startswith("[autotest]") or l.startswith("[test]"):
            print(l)
    if why == "script error":
        print("[godot.py] stopped: a script failed to parse or load (its window would stay black until the "
              "timeout); fix it and run again")
    print(f"[godot.py] exit {code}; {len(errs)} error lines; log {log}")
    for l in errs[:25]:
        print("  ", l)
    sys.exit(code)


if __name__ == "__main__":
    main()
