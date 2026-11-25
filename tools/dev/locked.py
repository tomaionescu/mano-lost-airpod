"""Run any command under the project's Godot lock (tools/dev/godot.py), so a heavy Blender build never runs
at the same time as a Godot test run (it would skew the frame timings).
usage: python3.11 tools/dev/locked.py <command> [args...]"""
import fcntl, subprocess, sys
import os
LOCK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "out", ".engine.lock")   # as godot.py
with open(LOCK, "w") as lk:
    fcntl.flock(lk, fcntl.LOCK_EX)
    sys.exit(subprocess.call(sys.argv[1:]))
