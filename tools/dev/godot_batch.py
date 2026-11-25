"""Several Godot runs under one hold of the engine lock (tools/out/.engine.lock, shared with godot.py and locked.py),
so a batch of headless checks waits for other runs once instead of once per run.

usage: python3.11 tools/dev/godot_batch.py JOBS.json
JOBS.json: [{"name": "line_check", "args": ["--headless", "--path", ".", "res://scenes/dev/line_check.tscn"],
             "timeout": 300, "log": "tools/out/x.log"}, ...]
Each job prints its [test]/[autotest] lines, its exit code and its SCRIPT ERROR / ERROR lines, as godot.py does.
Exit code: the number of jobs that exited non-zero. Headless runs only (no parse-error watchdog here)."""
import fcntl, json, os, subprocess, sys, time

GODOT = os.path.expanduser("~/Applications/godot/Godot.app/Contents/MacOS/Godot")
LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", ".engine.lock")
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def main():
    jobs = json.load(open(sys.argv[1]))
    bad = 0
    with open(LOCK, "w") as lk:
        t0 = time.time()
        fcntl.flock(lk, fcntl.LOCK_EX)
        waited = time.time() - t0
        if waited > 1:
            print(f"[godot_batch] waited {waited:.0f} s for another engine run", flush=True)
        for j in jobs:
            log = os.path.join(ROOT, j.get("log", f"tools/out/batch_{j['name']}.log"))
            os.makedirs(os.path.dirname(log), exist_ok=True)
            t1 = time.time()
            with open(log, "w") as out:
                p = subprocess.Popen([GODOT] + j["args"], cwd=ROOT, stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    code = p.wait(timeout=j.get("timeout", 300))
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid, 9)
                    p.wait()
                    code = 124
            lines = open(log, errors="replace").read().splitlines()
            errs = [l for l in lines if "SCRIPT ERROR" in l or l.startswith("ERROR") or "Parse Error" in l]
            print(f"== {j['name']}: exit {code}, {time.time() - t1:.0f} s, {len(errs)} error lines, log {os.path.relpath(log, ROOT)}")
            for l in lines:
                if l.startswith("[test]") or l.startswith("[autotest]"):
                    print("  ", l)
            for l in errs[:25]:
                print("   !", l)
            bad += 1 if code != 0 else 0
    sys.exit(bad)


if __name__ == "__main__":
    main()
