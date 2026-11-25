"""GPU time per perf spot from Apple's Metal HUD log (Godot reports 0 ms GPU time on Metal).

usage: MTL_HUD_ENABLED=1 MTL_HUD_LOG_ENABLED=1 python3.11 tools/dev/godot.py --log tools/out/x.log -- --path . -- autotest=perf qs=high
       python3.11 tools/dev/metal_hud.py tools/out/x.log [more logs...]

Each "metal-HUD:" line carries pairs of (frame interval ms, GPU ms) after three header values. The intervals are
multiples of 16.67 ms when macOS keeps vsync on (it does even with vsync disabled), so a GPU frame just over 16.7 ms
shows as 30 fps: read the GPU column, not the frame rate. For each "[autotest] <quality> <spot> ... frame" line the
median of the last 60 GPU samples before it is printed. Runs drift by several ms with heat and with other GPU work
(a Blender render); compare interleaved runs (A, B, A, B) and their minimums.
"""
import statistics
import sys


def spots(path: str) -> list:
    out, gpu, started = [], [], False
    for line in open(path, errors="replace"):
        if line.startswith("[autotest] 3d view"):
            started, gpu = True, []
        elif "metal-HUD:" in line and started:
            v = [float(x) for x in line.split("metal-HUD: ")[1].split(",") if x.strip()]
            gpu += [g for i, g in zip(v[3::2], v[4::2]) if i < 200.0 and g > 1.0]   # skip idle gaps
        elif line.startswith("[autotest]") and " frame " in line and started:
            w = line.split()
            tail = gpu[-60:]
            out.append((w[1], w[2], statistics.median(tail) if tail else 0.0, len(tail)))
            gpu = []
    return out


if __name__ == "__main__":
    for p in sys.argv[1:]:
        print(p, "  ".join("%s %s GPU %.1f ms (n %d)" % s for s in spots(p)))
