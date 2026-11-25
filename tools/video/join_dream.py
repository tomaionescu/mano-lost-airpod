#!/usr/bin/env python3.11
"""Join the opening dream's two halves into one 1920x1080 24 fps clip for review.

  clip A  round2/start.png -> round2/mid.png       the earbud's tumble and the crane up
  clip B  round2/mid.png   -> final/dream_end.png  the drift right to the notebook

usage:
  python3.11 tools/video/join_dream.py --a A_wan3 --b B_wan3 --out tools/out/dream/joined3   # the reference join
  python3.11 tools/video/join_dream.py --a tools/out/dream/takes4/A_wan3_v2.mp4 --b B_wan3  # any file by path
  python3.11 tools/video/join_dream.py --a tools/out/dream/engine/clipA.mp4 --matrix-a bt709 --a-even --a-moving \
      --b B_wan3                                    # the engine render: 24 fps, BT.709, arrives at mid.png moving
  python3.11 tools/video/join_dream.py --a tools/out/dream/engine/clipA_mb.mp4 --matrix-a bt709 --a-even --a-moving \
      --b B_wan3 --out tools/out/dream/joined5_r1 --hold-first 3 --max-seconds 9.0 --a-soften \
      --earbud-grade 218,2.4,0.5,1 --earbud-floor-lock --bridge-fb 1.0 --bridge-fb-region 20 --bridge-fb-feather 8 \
      --bridge-detail --overscan-release 30 --morph-ease \
      --b-ease-out 1.5                              # the slowed, motion-blurred render
  python3.11 tools/video/join_dream.py --a tools/out/dream/engine/clipA_mb.mp4 --matrix-a bt709 --a-even --a-moving \
      --b B_wan3 --out tools/out/dream/joined6_r1 --hold-first 3 --max-seconds 9.0 --a-soften \
      --earbud-grade 218,2.4,0.5,1 --earbud-matte clipA_mb16 --earbud-flip clipA_mb16f --earbud-xfade \
      --earbud-floor-lock --bridge-fb 1.0 --bridge-fb-region 20 --bridge-fb-feather 8 --bridge-detail \
      --overscan-release 30 --morph-ease --b-ease-out 1.5   # A's earbud from its passes
  python3.11 tools/video/join_dream.py                                   # every A_* x B_* pair in tools/out/dream/takes3
  python3.11 tools/video/join_dream.py --conform-report                  # also compare 30->24 fps conform methods

--a / --b take names (looked up in --takes) or paths to any video ffmpeg reads (a new take, an engine render); the
output is named <A>+<B> after the files' base names (--name overrides it for a single pair). A take listed in
PAINT_PRESETS gets its paint-out (step 2) unless --paint is given for its side or --no-presets. Writes, per pair, in
--out (tools/out/dream/joined):
  <A>+<B>.mp4          h264 High, CRF 12, yuv420p, BT.709 tagged, no audio
  <A>+<B>.png          contact sheet: speed graph, frames every 0.25 s, the seam, start/end against the keyframes
  <A>+<B>_tumble.png   every frame while the earbud is in view, at 1:1 around it: output components/area | the source
                       frame its earbud came from; a red border is a failed earbud check (step 12)
  <A>+<B>_seam.png     every frame around the bridge: thumbnails, both edges at half scale, the earbud at 1:1
  <A>+<B>_end.png      every frame of the end (the paint-out, the morph, the hold): thumbnails, both edges and the
                       bottom rows at half scale
  <A>+<B>.json         the plan and the measurements (the earbud check frame by frame); report.json for a full run.
Runs locally on ffmpeg + OpenCV (DIS optical flow, GrabCut; no learned models).

Steps
 1. decode()  The takes are untagged h264 whose Y'CbCr was made with the BT.601 matrix (regressing their Y'CbCr on
    the keyframes' RGB gives the 601 coefficients, not 709), so they are decoded with 601, limited range, to full-range
    RGB (--matrix-a / --matrix-b for a source that is not). MiniMax's 2560x1440 is scaled 0.75 (lanczos). FLUX's
    1920x1088 is the 16:9 keyframe scaled to cover 1936x1088 with 8 px cut off each side, so its centre 1080 rows are
    kept unscaled: that frame is 0.8 % closer than the keyframes (Clip.zoom); B then eases from that zoom to 1.0.
 2. paint  --paint SIDE:FIRST-LAST:REGION[:REF] replaces a region (X0,Y0,X1,Y1, or a polygon x1,y1,x2,y2,...) in a
    run of source frames by a clean frame REF of the same take, moved onto each frame by optical flow measured around
    it (the flow inside is filled in from its surroundings), feathered ~12 px except along the frame's own edge.
    B_wan3 needs it (its preset): a sharp seat-back sliver pops in at its right edge at frame 84, as the blurred near
    panel leaves, and slides out by 101; frame 106 is past it. Its region stops at the floor line, so the blurred
    panel's tail below it still leaves the frame as filmed:
      --paint B:84-101:1784,560,1920,560,1920,915,1784,850:106
    That region also holds the blurred panel's top, which would vanish with it in one frame, so the preset keeps what
    is brighter than the painted-in picture and carries frame 83's panel (keyed against it) on through the region,
    shifted each frame to line up with the panel still filmed below it, so the panel leaves the frame in one motion
    (parse_paint's keep= and carry=):
      --paint B:84-101:1784,560,1920,560,1920,915,1784,850:106:keep=40-90,carry=83
 1b. --a-soften (soften_to_keys)  The engine render is about twice as crisp as the game's keyframes (detail(): the
    variance of the Laplacian of the 720p luma, 175 against start.png's 80): A's frames get the Gaussian blur that
    brings each down to the keyframes' level at its place in the clip (start.png's at the first frame, mid.png's at the
    last), smoothed over +-2 frames; the motion-blurred middle is already under it and is left alone.
 3. Clip.analyse()  DIS flow between neighbouring frames at 960x540: median length = motion per frame (px at 1920),
    plus a robust affine fit (camera motion, used to predict where the earbud goes).
 4. Clip.track()  The earbud is the small bright desaturated blob (max(RGB) > 135, (max-min) < 0.3 max): seeded in
    A's first frame (B: next to where A's track ends, or --earbud-seed), then followed frame to frame inside a window
    around the affine prediction; every earbud-like component near it joins its group, so a doubled earbud (A_wan3's
    second one, frames 8-36) is one group. Its pixels in each frame (earbud_pixels) come from GrabCut, seeded with
    that bright core and a band of 0.35x its size around it: in this light its underside is as warm as the wood, and a
    colour threshold cut the bud flat. Masks are those pixels dilated: "hole" 5 px, "sprite" 3 px, "wide" 10-30 px.
 4b. --earbud-grade (earbud_grade)  In the shade the earbud's highlights fall to 130-170 levels and it reads tan; in
    both clips' source frames its difference to the plate under it is lifted (a curve per pixel, the highlight to
    TARGET, the shaded side a little more) and pulled toward grey, inside its matte only, eased in over ~6 frames as it
    enters the shade. Everything downstream (the paste, the bridge, the earbud check) uses the graded frames.
    --earbud-matte NAME[,TARGET,GAMMA,CHROMA] (dream_matte.py) replaces this for clip A: the engine renders the tumble
    again in passes (normal, plate, white, black; 16 steps a frame, the middle 8 averaged), which give the earbud's
    true soft matte (its motion blur and the carpet fibres in front of it included), its own colour unmixed from the
    floor and the floor under it. Its highlight is held on a smooth target on every frame and its chroma eased to its
    own sunlit cream (no brightness key, no inpainted floor: a keyed matte misses the blurred fringe and smears the
    yellow stripe under the earbud), and it is composited back over its own floor inside its support, every other
    pixel of the frame as it was. --earbud-flip NAME takes the frames flip.py re-posed (the fall off the nosing as a
    cartwheel) from that render's passes. --earbud-grade still grades B.
 4c. --earbud-floor-lock (Join.floor_locked_track, Clip.earbud_pos)  B's earbud rests on the floor. Its centre is
    the whole earbud's (the sprite matte's centroid; Wan's bright core keeps splitting, which moves a core-based
    centre by 5-13 px), and its path is a smooth function of B's content time (a robust local linear fit), so the
    pasted earbud does not twitch with Wan's shimmer and cadence. On the bridge it follows a cubic in output frames
    from its place and velocity before the bridge to its place and velocity after it (Join.bridge_earbud_path).
    --earbud-xfade: on the bridge, A's earbud and B's are each pasted on that path and cross-dissolved by the
    footage's own weights, over the frames where both carry weight (a one-frame handover pops: B's earbud is 12 %
    smaller, with a crisper grille).
 5. Clip.content_time()  Hitch removal. Wan's 30 fps runs in blocks with a 5-frame cadence of frame times
    (motion 2, .5, .5, 1, 1 x the local mean: a 6 Hz judder), FLUX and MiniMax B skip one frame every 24. Each frame
    gets a content time from its share of motion against the local mean (median-7 then Gaussian), and output frames
    are taken at even content times (--a-even: A's frames are evenly timed already, an engine render, so its
    content time is its frame index and at 24 fps it plays frame for frame). Plain frame selection keeps the judder (--conform-report: scatter 1.16 on A_wan3
    against 0.03), so the frames in between are interpolated, and the earbud is never interpolated:
      Join.clean()  Each source frame with the earbud has it inpainted away (its "hole"). The flows (Join.fl) are
      measured on these clean plates, the holes' flow filled from the floor around them: with the earbud in, its own
      motion drags DIS's field, which is ~100 px off around it on Wan's 2x cadence steps and puts its warped copies
      far from it (doubles, strings and tears). Join.src_frame()  The two clean plates are warped to the in-between
      time and blended by time, forward-backward visibility and an inside-the-frame test (no sample from beyond an
      edge); an inpainted hole gives way to the other frame's real floor, or, where both had the earbud, frame i-1's
      or i+2's through the composed flows. Join.paste_earbud()  Then the nearer real frame's earbud (its "sprite", no
      floor around it) is pasted whole, moved by ONE translation to where its own track is at that moment
      (Clip.track_shift; the flow is not trusted for it). So the earbud on screen is always one real frame's earbud,
      rigid: it cannot double, ghost, tear or bend; its pose changes at the source's frames.
 6. Clip.trim  A frozen tail (MiniMax holds its last ~0.3 s) is cut where the motion stays under 0.35 px/frame.
 7. Join.plan()  The seam. Both models ease into / out of mid.png, so a straight cut stalls (20-30 frames under a
    quarter speed). A's ease-out after the point where its speed falls under --seam-keep (0.7) of its peak and B's
    ease-in before the point where it reaches that share are replayed by arc length at a speed going smoothly from A's
    to B's. With --a-moving (A glides into mid.png without easing out, as the engine render does) A is not replayed:
    it plays at its own speed until the bridge's A half, and B is joined where its ease-in first reaches A's arrival
    speed, so only B's slower head is replayed, at A's speed. Around mid.png the clips are bridged over about --bridge-frames (10) frames from an A frame P to a B frame
    Q (Join.bridge_render()): each pixel follows a Hermite curve leaving P with A's motion and reaching Q with B's,
    and the pictures on it are the footage between P and Q (clean plates, places chained from small neighbour
    flows), each warped only by how far the curve cuts the corner. A's footage hands over to B's in a short dissolve
    (--dissolve, 0.3 of the bridge) at the frames nearest mid.png, where they agree; the earbud is pasted from the
    heaviest footage frame. Nothing is sampled outside a frame: a sample from beyond its frame's edge gets no weight.
    The corner the path cuts needs up to a few % beyond the footage's edges; stitching that from other footage frames
    tears the edges, so the picture is pushed in about the centre just enough that none of it stays in view
    (Join.overscan_needed: 1.041 at the peak for A_wan3+B_wan3), eased in and out over --overscan-ramp (14) frames, at
    most --overscan-max (1.06; A_minimax+B_minimax would want 1.077). What is still uncovered then comes from the
    nearest other footage frame (bridge_uncovered_px counts it). --overscan-release N lets the push-in go over N
    frames after the bridge (over B's still head a quick release reads as a pull-back). --bridge-fb E: wherever a step
    of the bridge's flow chain (or the direct P -> Q refinement) fails its forward-backward check by more than E
    half-res px, every field of the bridge is replaced by a smooth fill from around it (smooth_in): the per-pixel
    warps tear the left seat panels' bases and kink the treads where the engine's and Wan's geometry disagree; there
    each footage frame moves by its own camera motion only and A's picture dissolves into B's. --bridge-fb-region S
    also counts a passing island inside a mostly failing neighbourhood (Gaussian sigma S half-res px) as failing, and
    --bridge-fb-feather F softens the failing region's edge (sigma F): the islands' own per-pixel fields next to the
    smooth fill shear the far treads into 1-3 px Z-steps. --bridge-detail: the dissolve of two different pictures
    averages their fine textures away (a focus dip at the handover); each bridge frame gets the unsharp mask that
    brings its detail back to the line between the frames on either side (Join.bridge_detail).
 8. Colour  Each clip's colour is fitted (3x4 affine, robust least squares, on flow-aligned pixels) to its two
    keyframes and interpolated along the clip.
 9. End  Over the last --morph-frames (12) motion frames, when B is within ~18 px of dream_end.png, the B frame and
    dream_end.png are warped toward each other (geometry eases in first, the picture follows), each sample weighted
    to 0 outside its frame (no streaks, no see-through panel); then --hold-frames (8, 0.33 s) of dream_end.png
    itself, which main.gd dissolves into the live shot over DREAM_OUT = 0.3 s. --morph-ease: the geometry's share
    follows from a cubic for the distance left (B's median flow length to dream_end.png), from the last frame before
    the morph (value and rate) to 0 at rest, so the morph's own pull adds no speed; --b-ease-out S: B's last S seconds
    are replayed by arc length along a cubic ease-out from its incoming speed to rest (B's cadence leaves a wobble).
    --push-in Z,T0,T1,T2,T3[,X,Y] (off by default) pushes in toward the earbud, or about the fixed point X,Y. It stays
    off: a crop following the earbud raises the picture speed by 10-40 %, and a push about a fixed point still adds
    10-15 % in the opening for an earbud 8 % larger.
10. Length  A plays at its own speed (never sped up), from --a-start; the first frame is held --hold-first (6) frames
    under main.gd's DREAM_IN fade so the tip-over starts in full view. If the whole is longer than --max-seconds
    (8.5), only B (after the seam) plays faster, easing in over 0.5 s, at most --max-b-speedup (1.25). (The engine
    clip clipA_mb is already slowed where it ran fast, in the render itself: tools/out/dream/engine/retime.py.)
11. encode()  RGB -> BT.709 limited (to_ogv.py converts 709 -> 601 for Theora), x264 slow, CRF 12.
12. measure()  The mp4 is decoded again and measured: motion per frame and its scatter (hitches), the seam (dense
    speed; direction and acceleration from tracked corners), the same for a straight cut, MAD of the first frame against
    start.png and of the last against dream_end.png at 1792x1008, and the earbud (earbud_check): tracked through the
    output and, frame by frame, the source frame its pixels came from matched into it (earbud_residual: RMS levels at
    the best offset, the overscan undone; a rigid copy scores ~1-8, a bent, ghosted or doubled one tens; over
    EB_RMS_MAX fails), its area against the source's, and whether it was lost while the source has it.
"""
import argparse, json, math, os, subprocess, sys, time
from collections import OrderedDict

import cv2
import numpy as np
from scipy.ndimage import gaussian_filter1d, median_filter

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
TAKES = os.path.join(ROOT, "tools", "out", "dream", "takes3")
OUT = os.path.join(ROOT, "tools", "out", "dream", "joined")
KEYS = {"start": "shots/dream/round2/start.png", "mid": "shots/dream/round2/mid.png",
        "end": "shots/dream/final/dream_end.png"}
W, H, FPS = 1920, 1080, 24
FW, FH = 960, 540                     # flow resolution (half)
KW, KH = 1792, 1008                   # the keyframes' size: MADs are measured there
EB_V, EB_S = 135, 0.30                # earbud-like: max(RGB) above EB_V, (max - min) under EB_S * max
# per-take fixes applied when the take is used and no --paint is given for its side (--no-presets to skip)
PAINT_PRESETS = {"B_wan3": ["B:84-101:1784,560,1920,560,1920,915,1784,850:106:keep=40-90,carry=83"]}

cv2.setNumThreads(max(1, (os.cpu_count() or 4)))
np.seterr(all="ignore")     # Accelerate's matmul raises spurious divide/overflow flags on this Mac
_DIS = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
_DIS_FINE = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)   # one-off flows (bridge, end morph):
_DIS_FINE.setFinestScale(0)                                                # patches down to the 960x540 pixels
_GRIDS = {}


def grid(h, w):
    if (h, w) not in _GRIDS:
        _GRIDS[(h, w)] = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return _GRIDS[(h, w)]


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- I/O

def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate", "-of", "json", path], capture_output=True, text=True)
    s = json.loads(r.stdout)["streams"][0]
    n, d = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(n) / float(d)


def decode(path, matrix="bt601"):
    """All frames as uint8 RGB (N, 1080, 1920, 3), full range, writable. 16:9 sources are scaled to 1920x1080; a
    source a few rows taller than 16:9 (FLUX's 1088) keeps its centre 1080 rows unscaled. Returns (frames, fps)."""
    w, h, fps = probe(path)
    vf = []
    h169 = round(w * 9 / 16)
    if h != h169 and abs(h - h169) <= 16 and w == W:
        vf.append("crop=%d:%d:0:%d" % (w, h169, (h - h169) // 2))
    vf.append("scale=%d:%d:flags=lanczos+accurate_rnd+full_chroma_int:in_color_matrix=%s:in_range=tv:out_range=pc"
              % (W, H, matrix))
    vf.append("format=rgb24")
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", ",".join(vf), "-f", "rawvideo", "-"],
                       capture_output=True)
    if r.returncode != 0:
        sys.exit("decoding %s failed: %s" % (path, r.stderr.decode()[-500:]))
    return np.frombuffer(r.stdout, np.uint8).reshape(-1, H, W, 3).copy(), fps


def load_key(name):
    im = cv2.cvtColor(cv2.imread(os.path.join(ROOT, KEYS[name])), cv2.COLOR_BGR2RGB)
    assert im.shape[:2] == (KH, KW), (name, im.shape)
    return im


def to_full(key_u8):
    return cv2.resize(key_u8, (W, H), interpolation=cv2.INTER_LANCZOS4).astype(np.float32) / 255.0


def mad_at_key(frame_rgb, key_u8):
    """Mean absolute difference (0-255) of a 1920x1080 frame against a keyframe, at the keyframe's 1792x1008."""
    f = frame_rgb if frame_rgb.dtype == np.uint8 else np.clip(frame_rgb * 255 + 0.5, 0, 255).astype(np.uint8)
    s = cv2.resize(f, (KW, KH), interpolation=cv2.INTER_AREA)
    return float(np.abs(s.astype(np.int16) - key_u8.astype(np.int16)).mean())


def encode(frames_iter, n, dst, crf=12):
    vf = "scale=out_color_matrix=bt709:out_range=tv:flags=lanczos+accurate_rnd+full_chroma_int,format=yuv420p"
    cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", "%dx%d" % (W, H),
           "-r", str(FPS), "-i", "-", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "slow", "-crf", str(crf),
           "-profile:v", "high", "-tune", "film", "-g", "48",
           "-x264-params", "colorprim=bt709:transfer=bt709:colormatrix=bt709:range=tv",
           "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
           "-movflags", "+faststart", dst]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    count = 0
    for f in frames_iter:
        p.stdin.write(f.tobytes())
        count += 1
    p.stdin.close()
    if p.wait() != 0 or count != n:
        sys.exit("encoding %s failed (%d/%d frames)" % (dst, count, n))


# ---------------------------------------------------------------- flow and warping

def gray_half(img):
    """Half-resolution grey uint8 of a float (0..1) or uint8 RGB 1920x1080 frame, for the flow."""
    u8 = img if img.dtype == np.uint8 else np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)
    return cv2.cvtColor(cv2.resize(u8, (FW, FH), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)


def flow(g0, g1, fine=False):
    """DIS flow g0 -> g1 at 960x540, in half-res pixels: g0(x) ~ g1(x + f(x))."""
    return (_DIS_FINE if fine else _DIS).calc(g0, g1, None)


def sample(field, dx, dy):
    """field (h, w, c) sampled at grid + (dx, dy) (half-res), bilinear, edges replicated. Used only on flow fields
    and masks (smooth, so their edge value is the right guess), never on pictures."""
    gx, gy = grid(*field.shape[:2])
    return cv2.remap(field, gx + dx, gy + dy, cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)


def fb_mask(f01, f10, sigma=1.0):
    """Visibility of each pixel of frame 0 in frame 1 from forward-backward consistency (1 = consistent)."""
    back = sample(f10, f01[..., 0], f01[..., 1])
    e = np.hypot(f01[..., 0] + back[..., 0], f01[..., 1] + back[..., 1])
    return np.exp(-(e / sigma) ** 2).astype(np.float32)


def fb_error(f01, f10):
    """Forward-backward error (half-res px) of a flow pair, on frame 0's grid."""
    back = sample(f10, f01[..., 0], f01[..., 1])
    return np.hypot(f01[..., 0] + back[..., 0], f01[..., 1] + back[..., 1]).astype(np.float32)


def smooth_in(X, U, sigmas=(8.0, 20.0, 50.0)):
    """A field X (h, w, 2) with what lies under the soft mask U (0..1) replaced by a smooth fill from around it
    (normalized convolution; a wider kernel only where a narrower one found too little). X itself if U is None."""
    if U is None or U.max() < 1e-3:
        return X
    valid = (U < 0.5).astype(np.float32)
    fill, den_best = None, None
    for s in sigmas:
        num = cv2.GaussianBlur(X * valid[..., None], (0, 0), s)
        den = cv2.GaussianBlur(valid, (0, 0), s)
        cur = num / np.maximum(den, 1e-6)[..., None]
        if fill is None:
            fill, den_best = cur, den
        else:
            use = den_best < 0.1
            fill = np.where(use[..., None], cur, fill)
            den_best = np.where(use, den, den_best)
    return (X * (1 - U[..., None]) + fill * U[..., None]).astype(np.float32)


def invert(d, iters=3, residual=False):
    """Backward map for a forward displacement d on the source grid: returns b with  x = y + b(y)  solving
    x + d(x) = y (fixed point), in half-res pixels; with residual=True also |b + d(y + b)|, large where no source
    pixel lands (a tear: the fixed point does not exist)."""
    b = -d
    for _ in range(iters):
        b = -sample(d, b[..., 0], b[..., 1])
    if not residual:
        return b
    r = b + sample(d, b[..., 0], b[..., 1])
    return b, np.hypot(r[..., 0], r[..., 1])


def coords_full(b):
    """Full-res sample coordinates (X, Y) for a backward displacement field at full or half resolution."""
    if b.shape[:2] != (H, W):
        b = cv2.resize(b, (W, H), interpolation=cv2.INTER_LINEAR) * (W / b.shape[1])
    gx, gy = grid(H, W)
    return gx + b[..., 0], gy + b[..., 1]


def inside(X, Y):
    """1 where a sample at (X, Y) lies inside the 1920x1080 frame (within half a pixel), else 0."""
    return ((X >= -0.5) & (X <= W - 0.5) & (Y >= -0.5) & (Y <= H - 0.5)).astype(np.float32)


def feather_inside(v, sigma=8.0):
    """A hard inside-mask made soft only on its inner side: 0 wherever v is 0, ramping up to 1 over ~2 sigma inside,
    so a sample from outside a frame never gets weight and a switch to another source is never a hard edge.
    The frame's own border counts as inside (reflected)."""
    if v.min() >= 1.0:
        return v
    b = cv2.GaussianBlur(v, (0, 0), sigma, borderType=cv2.BORDER_REFLECT)
    return np.clip(v * (2 * b - 1), 0, 1)


def warp_full(img, b):
    """Warp a full-res float image by a backward displacement field (sample at y + b(y)), given at full or half
    resolution (then upsampled, in its own pixel units). Returns (image, inside-mask): the samples that fall outside
    the frame are reflected (never streaked), and the mask says where they are so callers give them no weight."""
    X, Y = coords_full(b)
    out = cv2.remap(img, X, Y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
    return out, inside(X, Y)


def warp_mask_full(m, b):
    """A full-res mask (float) carried by the same backward map as warp_full; 0 outside the frame."""
    if m is None:
        return None
    X, Y = coords_full(b)
    return cv2.remap(m, X, Y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def up(m):
    return m if m.shape[:2] == (H, W) else cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)


def blend(i0, m0, w0, i1, m1, w1, floor=0.02, v0=None, v1=None):
    """Blend two warped frames by time weights w0 / w1, half-res confidence maps m0 / m1 and full-res inside-masks
    v0 / v1 (a sample from outside its frame gets no weight; where both are outside, the floor keeps a mean)."""
    m0 = up(m0)[..., None] + floor
    m1 = up(m1)[..., None] + floor
    if v0 is not None:
        m0 = m0 * (v0[..., None] + 1e-4)
        m1 = m1 * (v1[..., None] + 1e-4)
    a, b = w0 * m0, w1 * m1
    return (a * i0 + b * i1) / (a + b)


def fill_flow(f, region):
    """Replace a flow field inside a (half-res, bool) region by a smooth fill from its surroundings (normalized
    convolution), so a small object moving on its own (the earbud) does not drag the background flow around it.
    The replacement is feathered 3 px outside the region."""
    if region is None or not region.any():
        return f
    ys, xs = np.nonzero(region)
    size = max(int(ys.max() - ys.min()), int(xs.max() - xs.min())) + 1
    s = max(4.0, size / 2.5)
    pad = int(3 * s) + 4
    y0, y1 = max(0, int(ys.min()) - pad), min(f.shape[0], int(ys.max()) + pad + 1)
    x0, x1 = max(0, int(xs.min()) - pad), min(f.shape[1], int(xs.max()) + pad + 1)
    sub = f[y0:y1, x0:x1]
    reg = region[y0:y1, x0:x1].astype(np.float32)
    valid = 1.0 - reg
    fill, den_best = None, None
    for sc in (1.0, 2.5, 6.0):          # a wider kernel only where the narrower one found too little around
        num = cv2.GaussianBlur(sub * valid[..., None], (0, 0), s * sc)
        den = cv2.GaussianBlur(valid, (0, 0), s * sc)
        cur = num / np.maximum(den, 1e-6)[..., None]
        if fill is None:
            fill, den_best = cur, den
        else:
            use = den_best < 0.05
            fill = np.where(use[..., None], cur, fill)
            den_best = np.where(use, den, den_best)
        if den_best[reg > 0].min() >= 0.05:
            break
    a = np.clip(cv2.GaussianBlur(reg, (0, 0), 1.5) * 2 + reg, 0, 1)[..., None]
    out = f.copy()
    out[y0:y1, x0:x1] = sub * (1 - a) + fill * a
    return out


def affine_fit(f):
    """Robust affine fit of a half-res flow: (cx, cy) with flow = [x - FW/2, y - FH/2, 1] . c (half-res px)."""
    ys, xs = np.mgrid[8:FH - 8:12, 8:FW - 8:12]
    X = np.c_[xs.ravel() - FW / 2, ys.ravel() - FH / 2, np.ones(xs.size)]
    u = f[ys, xs].reshape(-1, 2).astype(np.float64)
    keep = np.ones(len(u), bool)
    for _ in range(3):
        cx = np.linalg.lstsq(X[keep], u[keep, 0], rcond=None)[0]
        cy = np.linalg.lstsq(X[keep], u[keep, 1], rcond=None)[0]
        r = np.hypot(X @ cx - u[:, 0], X @ cy - u[:, 1])
        keep = r <= max(np.percentile(r, 70), 0.05)
    return cx, cy


def affine_motion(cx, cy):
    """Translation at the centre (px at 1920), zoom and rotation (% per frame) of an affine flow fit."""
    return 2 * cx[2], 2 * cy[2], 50 * (cx[0] + cy[1]), 50 * (cy[0] - cx[1])


def affine_predict(c, p):
    """Where a full-res point p moves under an affine flow fit c = (cx, cy)."""
    x, y = p[0] / 2 - FW / 2, p[1] / 2 - FH / 2
    v = np.array([x, y, 1.0])
    return (p[0] + 2 * float(c[0] @ v), p[1] + 2 * float(c[1] @ v))


def motion_series(grays):
    """Per interval: median flow length (px at 1920), affine (tx, ty, zoom%, rot%) and the affine fit itself."""
    sp, gm, aff = [], [], []
    for a, b in zip(grays[:-1], grays[1:]):
        f = flow(a, b)
        sp.append(2 * float(np.median(np.hypot(f[..., 0], f[..., 1]))))
        c = affine_fit(f)
        gm.append(affine_motion(*c))
        aff.append(c)
    return np.array(sp), np.array(gm), aff


def smoothstep(x):
    x = np.clip(x, 0.0, 1.0)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- the earbud

def earbud_like(rgb):
    f = rgb.astype(np.int16)
    mx = f.max(2)
    mn = f.min(2)
    return (mx > EB_V) & ((mx - mn) < EB_S * mx)


def components(mask, min_area, ox=0, oy=0):
    """Connected components of a bool mask: (x0, y0, x1, y1, area, cx, cy), offset by (ox, oy)."""
    n, _, st, cen = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    return [(int(st[k, 0]) + ox, int(st[k, 1]) + oy, int(st[k, 0] + st[k, 2]) + ox, int(st[k, 1] + st[k, 3]) + oy,
             int(st[k, 4]), float(cen[k][0]) + ox, float(cen[k][1]) + oy) for k in range(1, n) if st[k, 4] >= min_area]


def seed_earbud(frame, near=None):
    """The earbud's components in a frame: the largest compact earbud-like blob in the lower 70 % (or the one nearest
    `near`), with every earbud-like component within 1.3x its size."""
    cs = [c for c in components(earbud_like(frame), 12)
          if c[2] - c[0] <= 0.15 * W and c[3] - c[1] <= 0.2 * H
          and max(c[2] - c[0], c[3] - c[1]) <= 6 * max(1, min(c[2] - c[0], c[3] - c[1]))]
    if near is not None:
        cs = [c for c in cs if math.hypot(c[5] - near[0], c[6] - near[1]) < 250]
        if not cs:
            return None
        main = min(cs, key=lambda c: math.hypot(c[5] - near[0], c[6] - near[1]) / math.sqrt(c[4]))
    else:
        cs = [c for c in cs if c[6] > 0.3 * H and c[4] >= 30]
        if not cs:
            return None
        main = max(cs, key=lambda c: c[4])
    size = max(main[2] - main[0], main[3] - main[1])
    group = [c for c in cs if math.hypot(c[5] - main[5], c[6] - main[6]) <= max(40, 1.3 * size)]
    return group_record(group, main)


def group_record(group, main):
    box = (min(c[0] for c in group), min(c[1] for c in group), max(c[2] for c in group), max(c[3] for c in group))
    return dict(comps=[list(c[:5]) for c in group], c=(main[5], main[6]), main_area=main[4],
                main_size=max(main[2] - main[0], main[3] - main[1]), box=box,
                size=max(box[2] - box[0], box[3] - box[1]), area=sum(c[4] for c in group), n=len(group))


def track_earbud(frames, aff, last, first_rec):
    """Follow the earbud from first_rec (frame 0) to `last`; None where it is not in view. aff[i] is the affine
    camera motion i -> i+1."""
    recs = [None] * (last + 1)
    recs[0] = first_rec
    prev, lost = first_rec, 0
    for i in range(last):
        if prev is None:
            break
        p = affine_predict(aff[i], prev["c"])
        d = (p[0] - prev["c"][0], p[1] - prev["c"][1])
        R = max(56.0, 1.0 * prev["size"], 1.5 * math.hypot(*d))
        bx = prev["box"]
        x0, y0 = int(max(0, bx[0] + d[0] - R)), int(max(0, bx[1] + d[1] - R))
        x1, y1 = int(min(W, bx[2] + d[0] + R)), int(min(H, bx[3] + d[1] + R))
        cs = []
        if x1 - x0 > 4 and y1 - y0 > 4:
            cs = [c for c in components(earbud_like(frames[i + 1][y0:y1, x0:x1]), 6, x0, y0)
                  if c[4] <= 6 * prev["main_area"] + 400]
        if not cs:
            lost += 1
            if lost >= 2:
                break
            # carried one frame by the camera, no mask (nothing earbud-like there to protect)
            prev = dict(prev, c=p, box=(bx[0] + d[0], bx[1] + d[1], bx[2] + d[0], bx[3] + d[1]))
            continue
        lost = 0
        main = min(cs, key=lambda c: math.hypot(c[5] - p[0], c[6] - p[1]) / math.sqrt(c[4])
                   + 2.0 * abs(math.log(c[4] / max(prev["main_area"], 1))))
        size = max(prev["size"], 20)
        ex = 0.25 * size
        pb = (bx[0] + d[0] - ex, bx[1] + d[1] - ex, bx[2] + d[0] + ex, bx[3] + d[1] + ex)
        group = [c for c in cs if math.hypot(c[5] - main[5], c[6] - main[6]) <= max(40, 1.3 * size)
                 or (c[2] >= pb[0] and c[0] <= pb[2] and c[3] >= pb[1] and c[1] <= pb[3])]
        prev = recs[i + 1] = group_record(group, main)
    return recs


def _ellipse(r):
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def _fill_enclosed(m):
    """A bool mask with what it encloses (the dark grille, a shaded dent) filled in."""
    ff = cv2.copyMakeBorder(m.astype(np.uint8), 1, 1, 1, 1, cv2.BORDER_CONSTANT, value=0)
    cv2.floodFill(ff, np.zeros((ff.shape[0] + 2, ff.shape[1] + 2), np.uint8), (0, 0), 1)
    return m | (ff[1:-1, 1:-1] == 0)


def earbud_pixels(crop, rec, x0, y0):
    """The earbud's pixels in a crop at (x0, y0). Its bright core (earbud_like, inside the group's components) is
    certain; the band within 0.35x its size (at least 8 px) around it is "probably not", everything further is floor;
    GrabCut (colour models of the two, and a graph cut) decides the band. A colour threshold could not: in this
    light the earbud's underside is as warm and saturated as the wood ((max - min) ~ 0.45 max), and a mask that
    missed it cut the bud flat. The parts touching the core are kept, enclosed gaps filled. Without enough of either
    for GrabCut, the core grown by hysteresis (max > 60, (max - min) < 0.35 max) instead."""
    core = earbud_like(crop)
    keep = np.zeros_like(core)
    for c in rec["comps"]:
        keep[max(0, c[1] - y0 - 2):c[3] - y0 + 2, max(0, c[0] - x0 - 2):c[2] - x0 + 2] = True
    core &= keep
    if not core.any():
        return core
    reach = int(max(8, 0.35 * rec["size"]))
    pr = cv2.dilate(core.astype(np.uint8), _ellipse(reach)) > 0
    fg = None
    if (~pr).sum() > 200:
        m = np.full(core.shape, cv2.GC_BGD, np.uint8)
        m[pr] = cv2.GC_PR_BGD
        m[cv2.dilate(core.astype(np.uint8), _ellipse(2)) > 0] = cv2.GC_PR_FGD
        m[cv2.erode(core.astype(np.uint8), _ellipse(1)) > 0] = cv2.GC_FGD
        if (m == cv2.GC_FGD).sum() >= 8:
            try:
                cv2.grabCut(np.ascontiguousarray(crop[..., ::-1]), m, None, np.zeros((1, 65), np.float64),
                            np.zeros((1, 65), np.float64), 5, cv2.GC_INIT_WITH_MASK)
                fg = ((m == cv2.GC_FGD) | (m == cv2.GC_PR_FGD)) | core
            except cv2.error:
                fg = None
    if fg is None:
        f = crop.astype(np.int16)
        mx, mn = f.max(2), f.min(2)
        fg = (((mx > 60) & ((mx - mn) < 0.35 * mx)) & pr) | core
    n, lab = cv2.connectedComponents(fg.astype(np.uint8), connectivity=8)
    hit = np.unique(lab[core])
    return _fill_enclosed(np.isin(lab, hit[hit > 0]))


_PIX = {}      # earbud_pixels per frame and crop (GrabCut is the costly part)


def earbud_mask(frame, rec, kind="wide"):
    """Soft full-res mask (float32 0..1) of the earbud group in a frame: its pixels (earbud_pixels), closed,
    dilated and feathered: "wide" by 0.35x its size (10-30 px: where it and its flow's influence reach), "hole" by
    5 px (what is inpainted out of the frame: the earbud and its shaded edge), "sprite" by 3 px (what is pasted back
    from the real frame: the earbud alone, no floor: a rolling earbud would carry its floor along). None without a
    record."""
    if rec is None:
        return None
    r = {"hole": 5, "sprite": 3}.get(kind) or int(np.clip(0.35 * rec["size"], 10, 30))
    pad = 72
    bx = rec["box"]
    x0, y0 = max(0, int(bx[0]) - pad), max(0, int(bx[1]) - pad)
    x1, y1 = min(W, int(bx[2]) + pad), min(H, int(bx[3]) + pad)
    key = (frame.ctypes.data, x0, y0, x1, y1)
    if key not in _PIX:
        if len(_PIX) > 400:
            _PIX.pop(next(iter(_PIX)))
        _PIX[key] = earbud_pixels(frame[y0:y1, x0:x1], rec, x0, y0).astype(np.uint8)
    m = _PIX[key]
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)))
    m = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1)))
    m = np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), r / 4) * 1.6, 0, 1)
    full = np.zeros((H, W), np.float32)
    full[y0:y1, x0:x1] = m
    return full


def paste_shifted(out, img, v, mask):
    """Paste `img` moved by one translation v (out(x) = img(x + v), px at 1920) where its own soft full-res `mask`
    lands (the mask moved by -v), never from outside the frame."""
    ys, xs = np.nonzero(mask > 1e-3)
    if not len(xs):
        return
    x0, x1 = max(0, int(math.floor(xs.min() - v[0])) - 2), min(W, int(math.ceil(xs.max() - v[0])) + 3)
    y0, y1 = max(0, int(math.floor(ys.min() - v[1])) - 2), min(H, int(math.ceil(ys.max() - v[1])) + 3)
    if x1 <= x0 or y1 <= y0:
        return
    gx, gy = np.meshgrid(np.arange(x0, x1, dtype=np.float32), np.arange(y0, y1, dtype=np.float32))
    X, Y = gx + np.float32(v[0]), gy + np.float32(v[1])
    patch = cv2.remap(img, X, Y, cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT_101)
    a = (cv2.remap(mask, X, Y, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0) * inside(X, Y))[..., None]
    out[y0:y1, x0:x1] = out[y0:y1, x0:x1] * (1 - a) + patch * a


def half_region(*masks):
    """Half-res bool region covering full-res soft masks (dilated 3 px), or None."""
    ms = [m for m in masks if m is not None]
    if not ms:
        return None
    m = np.maximum.reduce(ms) if len(ms) > 1 else ms[0]
    h = cv2.resize(m, (FW, FH), interpolation=cv2.INTER_AREA) > 0.02
    return cv2.dilate(h.astype(np.uint8), np.ones((7, 7), np.uint8)) > 0


# ---------------------------------------------------------------- detail and the earbud's grade (sources)

def detail(img_u8):
    """Fine-detail energy: the variance of the Laplacian of the 1280x720 luma."""
    g = cv2.cvtColor(cv2.resize(img_u8, (1280, 720), interpolation=cv2.INTER_AREA), cv2.COLOR_RGB2GRAY)
    return float(cv2.Laplacian(g.astype(np.float32), cv2.CV_32F).var())


def soften_to_keys(frames, key_u8, keys):
    """Step 1b (--a-soften): the engine render is about twice as crisp as the game's own keyframes (start.png's
    detail 80 against frame 0's 175; its 1920x1080 SubViewport against the keyframes' 1792x1008 view). Each frame
    gets the Gaussian blur (sigma in px at 1920, found by bisection) that brings its detail() down to the keyframes'
    level at its place in the clip (start.png's at the first frame, mid.png's at the last, linear between); a frame
    already under it (the motion-blurred middle, the end) is left alone. The sigmas are smoothed over +-2 frames so
    the focus never flickers. In place; returns the sigmas and the detail before / after."""
    t0, t1 = detail(key_u8[keys[0]]), detail(key_u8[keys[1]])
    n = len(frames)
    before = [detail(f) for f in frames]
    sig = np.zeros(n)
    for i, f in enumerate(frames):
        target = t0 + (t1 - t0) * i / max(n - 1, 1)
        if before[i] <= target * 1.02:
            continue
        lo, hi = 0.0, 3.0
        for _ in range(14):
            mid = 0.5 * (lo + hi)
            if detail(cv2.GaussianBlur(f, (0, 0), mid)) > target:
                lo = mid
            else:
                hi = mid
        sig[i] = 0.5 * (lo + hi)
    sig = np.maximum(gaussian_filter1d(sig, 2.0, mode="nearest"), 0)
    for i in range(n):
        if sig[i] > 0.05:
            frames[i] = np.clip(cv2.GaussianBlur(frames[i].astype(np.float32), (0, 0), sig[i]) + 0.5, 0, 255
                                ).astype(np.uint8)
    after = [detail(f) for f in frames]
    return dict(target=[round(t0, 1), round(t1, 1)], sigma=[round(float(s), 3) for s in sig],
                detail_before=[round(v, 1) for v in before], detail_after=[round(v, 1) for v in after])


def luma(rgb):
    return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722


def earbud_grade(clip, target=214.0, gmax=2.4, desat=0.5, cool=0.0, gamma=0.75, frames=None):
    """Step 4b (--earbud-grade TARGET,GMAX,DESAT[,COOL]): the earbud reads white, as an AirPod, in the shade too. Once it
    leaves the sunbeam the engine's earbud's highlights fall from ~228 to 130-160 levels and it reads tan or beige on
    the navy carpet (Wan's in B, ~170, likewise). Per source frame with the earbud: the floor under it (the plate:
    its "hole" inpainted), its highlight hl (95th percentile of the core's luma) and the floor's luma fl there. The
    highlight it should have, H = max(hl, TARGET) smoothed over +-2 frames (so in the sun nothing changes and the lift
    eases in over ~6 frames as it enters the shade, never brighter than in the sun), sets the curve: each pixel's
    luma difference to the plate d, as a share x = d / (hl - fl) of the highlight's, becomes (H - fl) x^g, g easing
    from 1 (sun) to GAMMA (shade: the shaded side lifts more than the highlight, the shading's order kept); the pixel's
    difference to the plate is scaled by that ratio (at most GMAX), only where it is brighter than the plate (no glow
    on the carpet, its rim's texture not amplified) and inside its soft sprite matte, so its motion blur and
    antialiased edge keep their proportions; then pulled DESAT of the way to grey (the pale blue under-rim, the tan
    cast), highlights rolling off above 236. COOL (0..1): the render's pale blue specular under the bud and along the
    stem, lifted with the rest, reads as a cut-out halo; what is bluer than the earbud's own body (B - R over the
    body's median, ramped over 14 levels) takes the body's chroma, its luma kept. In place on clip.raw; returns per
    frame [ratio at the highlight, hl, fl, H]."""
    idx = [i for i in range(clip.n) if clip.eb[i] is not None and (frames is None or i in frames)]
    if not idx:
        return {}
    geo = {}
    for i in idx:
        rec = clip.eb[i]
        S = earbud_mask(clip.raw[i], rec, "sprite")
        Hh = earbud_mask(clip.raw[i], rec, "hole")
        ys, xs = np.nonzero(Hh > 0.02)
        if not len(xs):
            continue
        x0, x1 = max(0, xs.min() - 16), min(W, xs.max() + 17)
        y0, y1 = max(0, ys.min() - 16), min(H, ys.max() + 17)
        crop = clip.raw[i][y0:y1, x0:x1]
        P = cv2.inpaint(crop, (Hh[y0:y1, x0:x1] > 0.02).astype(np.uint8), 7, cv2.INPAINT_TELEA)
        core = earbud_pixels(crop, rec, x0, y0)
        if core.sum() < 10:
            continue
        lI = luma(crop.astype(np.float32))
        lP = luma(P.astype(np.float32))
        geo[i] = (x0, y0, x1, y1, P.astype(np.float32), S[y0:y1, x0:x1], float(np.percentile(lI[core], 95)),
                  float(np.median(lP[core])))
    if not geo:
        return {}
    ks = sorted(geo)
    hl = np.array([geo[k][6] for k in ks])
    Ht = gaussian_filter1d(np.maximum(hl, target), 2.0, mode="nearest")
    shade = gaussian_filter1d(np.clip((target - hl) / 40.0, 0, 1), 2.0, mode="nearest")
    out = {}
    for k, Hk, sk in zip(ks, Ht, shade):
        x0, y0, x1, y1, Pf, S, hk, fk = geo[k]
        I = clip.raw[k][y0:y1, x0:x1].astype(np.float32)
        D = I - Pf
        d = luma(D)
        dh = max(hk - fk, 8.0)
        g = 1.0 - (1.0 - gamma) * float(sk)
        xs_ = np.clip(d / dh, 1e-3, 1.5)
        ratio = np.clip((Hk - fk) / dh * xs_ ** (g - 1.0), 1.0, gmax)
        w = cv2.GaussianBlur(np.clip((d - 4.0) / 18.0, 0, 1).astype(np.float32), (0, 0), 0.8)
        a = (S * w)[..., None]
        J = I + a * (ratio[..., None] - 1.0) * D
        lj = luma(J)[..., None]
        J = J + a * (desat * min(1.0, 1.5 * float(sk))) * (lj - J)
        if cool > 0:
            lj = luma(J)
            body = (a[..., 0] > 0.5) & (lj > fk + 0.3 * (Hk - fk))
            if body.sum() >= 12:
                ch = J - lj[..., None]
                ref = np.median(ch[body], 0)
                excess = (ch[..., 2] - ch[..., 0]) - (ref[2] - ref[0])
                wc = np.clip(excess / 14.0, 0, 1) * cool * np.clip(a[..., 0] * 1.5, 0, 1)
                J = J + wc[..., None] * (ref[None, None, :] + lj[..., None] - J)
        J = np.where(J > 236, 236 + (J - 236) * 0.35, J)
        clip.raw[k][y0:y1, x0:x1] = np.clip(J + 0.5, 0, 255).astype(np.uint8)
        # the record's earbud-like area as graded, grouped the way the output's tracker groups it (the earbud check
        # compares the output's area with it; the lift makes more of the earbud and its motion blur earbud-like)
        rec = clip.eb[k]
        rec["area_ungraded"] = rec["area"]
        g2 = seed_earbud(clip.raw[k], rec["c"])
        if g2 is not None:
            rec["area"] = max(rec["area"], int(g2["area"]))
        out[k] = [round(float((Hk - fk) / dh), 3), round(hk, 1), round(fk, 1), round(float(Hk), 1)]
    return out


# ---------------------------------------------------------------- paint-out

def parse_paint(spec):
    """SIDE:FIRST-LAST:REGION[:REF[:OPTS]] -> dict; REGION is X0,Y0,X1,Y1 (a box) or x1,y1,x2,y2,x3,y3,... (a
    polygon). OPTS, comma separated: ramp=N (or a bare N) fades the paint in over the run's first N frames;
    keep=LO-HI keeps what is brighter than the painted-in picture by LO..HI levels of luma (a smooth ramp: a bright
    thing in front stays); carry=F (with keep=) carries frame F's bright front layer (keyed the same way against
    the painted-in picture) on through the region, moved each frame by the shift that lines it up with the same
    thing just below the region, where it is still filmed (B_wan3: the blurred near panel leaving at the right edge,
    whose top the sliver painted out had covered: it now leaves the frame in one motion instead of vanishing)."""
    parts = spec.split(":")
    ramp, keep, carry = 0, None, None
    if len(parts) == 5:
        for o in parts[4].split(","):
            if o.startswith("keep="):
                keep = [float(v) for v in o[5:].split("-")]
            elif o.startswith("carry="):
                carry = int(o[6:])
            else:
                ramp = int(o.split("=")[-1])
        parts = parts[:4]
    if len(parts) not in (3, 4) or parts[0] not in ("A", "B"):
        sys.exit("--paint %s: expected SIDE:FIRST-LAST:X0,Y0,X1,Y1[:REF[:OPTS]]" % spec)
    f0, f1 = (int(v) for v in parts[1].split("-"))
    v = [int(x) for x in parts[2].split(",")]
    if len(v) == 4:
        poly = [(v[0], v[1]), (v[2], v[1]), (v[2], v[3]), (v[0], v[3])]
    elif len(v) >= 6 and len(v) % 2 == 0:
        poly = list(zip(v[0::2], v[1::2]))
    else:
        sys.exit("--paint %s: the region is 4 numbers (a box) or 3+ x,y pairs (a polygon)" % spec)
    ref = int(parts[3]) if len(parts) >= 4 else f1 + 5
    return dict(side=parts[0], first=f0, last=f1, region=[list(p) for p in poly], ref=ref, ramp=ramp, keep=keep,
                carry=carry)


def _front(img, bg, keep):
    """Soft matte (0..1) of what is brighter than the background bg by keep[0]..keep[1] levels of luma."""
    dl = (luma(img) - luma(bg)) * 255
    return cv2.GaussianBlur(np.clip((dl - keep[0]) / max(keep[1] - keep[0], 1.0), 0, 1).astype(np.float32),
                            (0, 0), 1.5)


def _shift(img, dx, dy):
    M = np.float32([[1, 0, dx], [0, 1, dy]])
    return cv2.warpAffine(img, M, (img.shape[1], img.shape[0]), flags=cv2.INTER_LINEAR,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=0)


def paint_out(frames, p):
    """Replace p's region in frames first..last by frame ref, moved onto each by flow measured around it (keep=:
    what is much brighter than that stays; carry=: a front layer carried on through it). Returns the flow (px)
    per frame and the carried layer's shifts."""
    poly = np.array(p["region"], np.int32)
    a = np.zeros((H, W), np.float32)
    cv2.fillPoly(a, [poly], 1.0)
    R = frames[p["ref"]].astype(np.float32) / 255
    gR = gray_half(frames[p["ref"]])
    reg = cv2.dilate((cv2.resize(a, (FW, FH), interpolation=cv2.INTER_AREA) > 0).astype(np.uint8),
                     np.ones((13, 13), np.uint8)) > 0
    hard = a.copy()
    a = cv2.GaussianBlur(a, (0, 0), 6, borderType=cv2.BORDER_REPLICATE)     # feathered, not at the frame's own edge
    a = np.clip((a - 0.5) * 2.2 + 0.5, 0, 1)[..., None]
    out, shifts = [], []
    ramp, keep, carry = p.get("ramp", 0), p.get("keep"), p.get("carry")
    layer = None
    if carry is not None and keep:
        Fc = frames[carry].astype(np.float32) / 255
        Rc, _ = warp_full(R, fill_flow(flow(gray_half(frames[carry]), gR, fine=True), reg))
        al = _front(Fc, Rc, keep)
        layer = (Fc - (1 - al[..., None]) * Rc, al)
        # where the shift is fitted: a band around the region (the front thing is still filmed there)
        ys, xs = np.nonzero(hard > 0)
        by0, by1 = max(0, ys.min() - 40), min(H, ys.max() + 70)
        bx0, bx1 = max(0, xs.min() - 120), W
        band = ((cv2.dilate(hard, np.ones((121, 81), np.uint8)) > 0) & (hard == 0))[by0:by1, bx0:bx1]
        cx0 = max(0, bx0 - 140)                      # the layer's crop reaches further left (it moves right)
        Pl_c, al_c = layer[0][by0:by1, cx0:bx1], al[by0:by1, cx0:bx1]
        shift_prev, gone = (0.0, 0.0), False
    for k in range(p["first"], p["last"] + 1):
        f = fill_flow(flow(gray_half(frames[k]), gR, fine=True), reg)
        Rw, _ = warp_full(R, f)
        img = frames[k].astype(np.float32) / 255
        r = min(1.0, (k - p["first"] + 1) / (ramp + 1)) if ramp else 1.0
        ak = a * r
        fill = Rw
        if layer is not None and not gone:
            # the shift (dx, dy) that best lines the carried layer up with frame k in the band, searched around the
            # previous frame's shift plus its step
            Rw_c = Rw[by0:by1, cx0:bx1]
            Lk = luma(img[by0:by1, bx0:bx1])
            front_k = _front(img[by0:by1, bx0:bx1], Rw[by0:by1, bx0:bx1], keep)
            best = None
            step = shift_prev[0] - (shifts[-2][0] if len(shifts) > 1 else 0.0)
            guess = shift_prev[0] + max(step, 0.0)
            for dx in np.arange(max(0.0, guess - 30), guess + 31, 1.0):
                for dy in np.arange(-6.0, 6.1, 2.0):
                    As = _shift(al_c, dx, dy)
                    Ls = luma(_shift(Pl_c, dx, dy) + (1 - As[..., None]) * Rw_c)[:, bx0 - cx0:]
                    wgt = band * np.clip(As[:, bx0 - cx0:] + front_k, 0, 1)
                    if wgt.sum() < 50:
                        continue
                    e = float((np.abs(Ls - Lk) * wgt).sum() / wgt.sum())
                    if best is None or e < best[0]:
                        best = (e, dx, dy)
            if best is not None:
                shift_prev = (float(best[1]), float(best[2]))
                As = _shift(layer[1], *shift_prev)
                if float((As * hard).sum()) < 20:
                    gone = True                      # it has left the region
                fill = Rw * (1 - As[..., None]) + _shift(layer[0], *shift_prev)
                shifts.append([round(best[1], 1), round(best[2], 1), round(best[0] * 255, 2)])
            else:
                gone = True
        elif keep and layer is None:
            ak = ak * (1 - _front(img, Rw, keep)[..., None])
        frames[k] = np.clip((img * (1 - ak) + fill * ak) * 255 + 0.5, 0, 255).astype(np.uint8)
        out.append(round(2 * float(np.median(np.hypot(*f[reg].T))), 1))
    return (out, shifts) if layer is not None else out


# ---------------------------------------------------------------- colour

def fit_colour(frame, key_full):
    """3x4 affine colour transform taking `frame` (float RGB) onto `key_full`, fitted on flow-aligned pixels at
    480x270 with Huber-weighted least squares, pulled gently toward identity."""
    sw, sh = 480, 270
    fs = cv2.resize(frame, (sw, sh), interpolation=cv2.INTER_AREA)
    ks = cv2.resize(key_full, (sw, sh), interpolation=cv2.INTER_AREA)
    g = lambda im: cv2.cvtColor(np.clip(im * 255 + .5, 0, 255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    f = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM).calc(g(ks), g(fs), None)
    gx, gy = np.meshgrid(np.arange(sw, dtype=np.float32), np.arange(sh, dtype=np.float32))
    fw = cv2.remap(fs, gx + f[..., 0], gy + f[..., 1], cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    m = 8
    X = fw[m:-m, m:-m].reshape(-1, 3).astype(np.float64)
    Y = ks[m:-m, m:-m].reshape(-1, 3).astype(np.float64)
    A = np.c_[X, np.ones(len(X))]
    I = np.vstack([np.eye(3), np.zeros((1, 3))])
    lam = 2e-3 * len(X)
    w = np.ones(len(X))
    M = I.copy()
    for _ in range(4):
        Aw = A * w[:, None]
        M = np.linalg.solve(A.T @ Aw + lam * np.eye(4), Aw.T @ Y + lam * I)
        r = np.abs(A @ M - Y).sum(1)
        c = max(np.median(r) * 1.5, 1e-3)
        w = np.where(r <= c, 1.0, c / r)
    return M.T.astype(np.float32)          # 3x4 for cv2.transform


def apply_colour(img, M):
    return np.clip(cv2.transform(img, M), 0.0, 1.0)


# ---------------------------------------------------------------- clips

def resolve(name_or_path, takes):
    """A take name in --takes, or a path; returns (name, path)."""
    if os.path.exists(name_or_path):
        path = os.path.abspath(name_or_path)
    else:
        path = os.path.join(takes, name_or_path + ("" if name_or_path.endswith(".mp4") else ".mp4"))
        if not os.path.exists(path):
            sys.exit("no such take: %s (not a file, nor %s)" % (name_or_path, path))
    return os.path.splitext(os.path.basename(path))[0], path


class Clip:
    def __init__(self, name, path, side, matrix="bt601", paints=(), even=False):
        self.name, self.path, self.side = name, path, side
        self.even = even        # frames already evenly timed (an engine render): no hitch retiming (step 5)
        t0 = time.time()
        self.raw, self.fps = decode(self.path, matrix)
        self.n = len(self.raw)
        self.keys = ("start", "mid") if side == "A" else ("mid", "end")
        self.src_size = probe(self.path)[:2]
        self.eb, self._masks, self.eb_span = [None] * self.n, {}, None
        self.c_smooth = None     # the earbud's smooth resting path (Join.floor_locked_track)
        self.c_rob = None        # the whole earbud's centre per frame (robust_centres)
        self.graded = None
        self.paints = []
        for p in paints:
            if not (0 <= p["first"] <= p["last"] < self.n and 0 <= p["ref"] < self.n):
                sys.exit("--paint %s: frames out of range (0-%d)" % (p, self.n - 1))
            res = paint_out(self.raw, p)
            p = dict(p, flow_px=res[0], carry_shift=res[1]) if isinstance(res, tuple) else dict(p, flow_px=res)
            self.paints.append(p)
        log("  %s %s: %d frames %.3g fps from %dx%d (%.1f s)%s" % (side, name, self.n, self.fps, *self.src_size,
                                                                  time.time() - t0,
                                                                  "  painted %s" % self.paints if self.paints else ""))

    def analyse(self, key_u8):
        grays = [gray_half(f) for f in self.raw]
        self.speed, self.gm, self.aff = motion_series(grays)    # per interval, px at 1920 per source frame
        # geometry against the first keyframe (FLUX's crop is a zoom of ~1.008, the others 1.0)
        k0 = cv2.cvtColor(cv2.resize(key_u8[self.keys[0]], (FW, FH), interpolation=cv2.INTER_AREA),
                          cv2.COLOR_RGB2GRAY).astype(np.float32) / 255
        f0 = grays[0].astype(np.float32) / 255
        warp = np.eye(2, 3, dtype=np.float32)
        try:
            _, warp = cv2.findTransformECC(k0, f0, warp, cv2.MOTION_AFFINE,
                                           (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 200, 1e-7), None, 5)
        except cv2.error:
            pass
        z = float(np.sqrt(abs(np.linalg.det(warp[:, :2]))))
        self.zoom = z if abs(z - 1) > 0.002 else 1.0
        self.geom = warp.tolist()
        # frozen tail
        last = self.n - 1
        while last > self.n // 2 and self.speed[last - 1] < 0.35:
            last -= 1
        self.last = last
        self.content_time()
        sp = self.speed[:self.last]
        self.arc = np.concatenate([[0.0], np.cumsum(sp + 1e-4)])           # by frame index, valid frames
        rate = sp / np.diff(self.tau[:self.last + 1])                       # px per content frame
        self.v_out = gaussian_filter1d(rate, 2.5, mode="nearest") * self.fps / FPS   # px per 24 fps frame

    def track(self, near=None):
        """The earbud's track through the valid frames (step 4) and its masks (lazily)."""
        first = seed_earbud(self.raw[0], near)
        self.eb = track_earbud(self.raw, self.aff, self.last, first) if first else [None] * (self.last + 1)
        self.eb += [None] * (self.n - len(self.eb))
        self._masks = {}
        seen = [i for i, r in enumerate(self.eb) if r is not None]
        self.eb_span = (seen[0], seen[-1]) if seen else None
        log("    earbud: %s" % ("frames %d-%d, size %d -> %d px, %d frames with more than one component"
                               % (seen[0], seen[-1], self.eb[seen[0]]["size"], self.eb[seen[-1]]["size"],
                                  sum(1 for i in seen if self.eb[i]["n"] > 1)) if seen else "not found"))

    def mask(self, i, kind="wide"):
        i = int(i)
        if not hasattr(self, "eb") or i < 0 or i >= self.n or self.eb[i] is None:
            return None
        if (i, kind) not in self._masks:
            if len(self._masks) > 90:
                self._masks.pop(next(iter(self._masks)))
            self._masks[(i, kind)] = earbud_mask(self.raw[i], self.eb[i], kind)
        return self._masks[(i, kind)]

    def track_shift(self, i, t, n):
        """The translation (px at 1920, sample offset) that puts frame n's earbud where its own track is at i + t,
        interpolated between the tracked centres of frames i and i + 1; None when the track is not trustworthy
        there (missing, or its main component jumped: a different blob or a big change of size). On a smoothed
        resting path (c_smooth) the path is trusted as it is."""
        a, b = (self.eb[i] if 0 <= i < self.n else None), (self.eb[i + 1] if 0 <= i + 1 < self.n else None)
        if a is None or b is None:
            return None
        jump = math.hypot(b["c"][0] - a["c"][0], b["c"][1] - a["c"][1])
        ratio = max(a["main_area"], b["main_area"]) / max(1, min(a["main_area"], b["main_area"]))
        smooth = self.c_smooth is not None and self.c_smooth[i] is not None and self.c_smooth[i + 1] is not None
        if not smooth and (ratio > 2.5 or jump > 1.5 * max(a["main_size"], b["main_size"]) + 40):
            return None
        self.robust_centres()
        # the whole earbud's centre (robust_centres) is what is matched: the largest component's centroid jumps
        # when Wan's bright core splits; on a resting path (c_smooth) the path by content time
        p = self.earbud_pos(i + t)
        c = self.c_rob[n]
        if p is None or c is None:
            ca, cb, c = a["c"], b["c"], self.eb[n]["c"]
            p = ((1 - t) * ca[0] + t * cb[0], (1 - t) * ca[1] + t * cb[1])
        return np.array([c[0] - p[0], c[1] - p[1]], np.float32)

    def robust_centres(self):
        """The whole earbud's centre per frame: its sprite matte's weighted centroid (c_rob), steadier than the
        largest component's centroid when the bright core splits."""
        if getattr(self, "c_rob", None) is not None:
            return
        self.c_rob = [None] * self.n
        for i in range(self.n):
            m = self.mask(i, "sprite") if self.eb[i] is not None else None
            if m is None or m.sum() < 5:
                continue
            ys, xs = np.nonzero(m > 0.02)
            w = m[ys, xs]
            self.c_rob[i] = (float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum()))

    def earbud_pos(self, x):
        """Where the whole earbud is at source position x (px at 1920): on the smooth resting path where there is
        one, else between the neighbouring frames' robust centres. None without the earbud."""
        self.robust_centres()
        i = int(math.floor(x))
        t = x - i
        if t < 1e-6 or i >= self.n - 1:
            i = min(i, self.n - 1)
            if self.c_smooth is not None and self.c_smooth[i] is not None:
                return self.c_smooth[i]
            return self.c_rob[i]
        for path in (self.c_smooth, self.c_rob):
            if path is not None and path[i] is not None and path[i + 1] is not None:
                return ((1 - t) * path[i][0] + t * path[i + 1][0], (1 - t) * path[i][1] + t * path[i + 1][1])
        return None

    def content_time(self):
        """Per frame content time in source-frame units (see step 5)."""
        d = self.speed[:max(self.last, 1)]
        if self.even:
            # an engine render's frames are exactly 1 / fps apart: its own timing is the truth (its slow head would
            # read as hitches and shift every frame by up to one, so all of them would be interpolated)
            self.hitch_ratio = np.ones(len(d))
            self.tau = np.arange(len(d) + 1, dtype=np.float64)
            return
        base = gaussian_filter1d(median_filter(d, size=7, mode="nearest"), 2.0, mode="nearest")
        eps = 0.3
        r = (d + eps) / (base + eps)
        r = np.where(np.abs(r - 1) < 0.06, 1.0, r)       # leave measurement noise alone (smooth takes stay put)
        r = np.clip(r, 0.25, 3.0)
        tau = np.concatenate([[0.0], np.cumsum(r)])
        self.tau = tau * (len(d) / tau[-1])
        self.hitch_ratio = r

    # position helpers (fractional frame index within the valid frames)
    def pos_at_tau(self, t):
        return float(np.interp(t, self.tau, np.arange(self.last + 1)))

    def tau_at(self, s):
        return float(np.interp(s, np.arange(self.last + 1), self.tau))

    def pos_at_arc(self, a):
        return float(np.interp(a, self.arc, np.arange(self.last + 1)))

    def arc_at(self, s):
        return float(np.interp(s, np.arange(self.last + 1), self.arc))

    def best_match(self, key_u8, first):
        """Index of the valid frame that best matches a keyframe among the first / last 20."""
        idx = range(0, min(20, self.last + 1)) if first else range(max(0, self.last - 19), self.last + 1)
        ks = cv2.resize(key_u8, (480, 270), interpolation=cv2.INTER_AREA).astype(np.int16)
        d = [np.abs(cv2.resize(self.raw[i], (480, 270), interpolation=cv2.INTER_AREA).astype(np.int16) - ks).mean()
             for i in idx]
        return list(idx)[int(np.argmin(d))]

    def fit_colours(self, key_u8):
        self.anchor = (0 if self.side == "A" else self.best_match(key_u8[self.keys[0]], True),
                       self.best_match(key_u8[self.keys[1]], False))
        self.M = []
        self.colour_shift = []
        for i, k in zip(self.anchor, self.keys):
            fr = self.raw[i].astype(np.float32) / 255
            M = fit_colour(fr, to_full(key_u8[k]))
            self.M.append(M)
            self.colour_shift.append([round(float(v) * 255, 2)
                                      for v in (apply_colour(fr, M) - fr).reshape(-1, 3).mean(0)])

    def colour_at(self, i):
        t0, t1 = self.tau_at(self.anchor[0]), self.tau_at(self.anchor[1])
        w = float(np.clip((self.tau_at(min(i, self.last)) - t0) / max(t1 - t0, 1e-6), 0, 1))
        return (1 - w) * self.M[0] + w * self.M[1]


# ---------------------------------------------------------------- the join

class Join:
    def __init__(self, A, B, key_u8, args):
        self.A, self.B, self.key = A, B, key_u8
        self.args = args
        self.E = to_full(key_u8["end"])
        self.gE = gray_half(self.E)
        self.cache = OrderedDict()
        self.flows = {}
        self.stats = dict(bridge_uncovered_px={}, morph_outside_px={}, earbud_source={})

    def clip(self, side):
        return self.A if side == "A" else self.B

    # source frames: zoomed (B of a FLUX pair), colour corrected, float 0..1, cached
    def frame(self, side, i):
        k = (side, i)
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        c = self.clip(side)
        img = c.raw[min(i, c.n - 1)].astype(np.float32) / 255
        img = apply_colour(img, c.colour_at(i))
        z = self.b_zoom(i) if side == "B" else 1.0
        if abs(z - 1) > 1e-5:
            # zoom in by z about the centre: output pixel y samples the source at c + (y - c) / z (inside the frame)
            cx, cy = (W - 1) / 2, (H - 1) / 2
            Mi = np.float32([[1 / z, 0, cx * (1 - 1 / z)], [0, 1 / z, cy * (1 - 1 / z)]])
            img = cv2.warpAffine(img, Mi, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                 borderMode=cv2.BORDER_REFLECT_101)
        self.cache[k] = img
        while len(self.cache) > 40:
            self.cache.popitem(last=False)
        return img

    def mask(self, side, i, kind="wide"):
        return self.clip(side).mask(i, kind)

    def gray(self, side, i):
        k = ("g", side, i)
        if k not in self.flows:
            self.flows[k] = gray_half(self.frame(side, i))
        return self.flows[k]

    def gc(self, side, i):
        """Half-res grey of the clean plate (the earbud inpainted away), for the flows."""
        k = ("gc", side, i)
        if k not in self.flows:
            c = self.clip(side)
            self.flows[k] = gray_half(self.clean(side, i)) if c.mask(i) is not None else self.gray(side, i)
        return self.flows[k]

    def fl(self, sa, i, sb, j, fine=False):
        """Flow between two source frames, measured on their clean plates (no earbud to drag it: an earbud moving
        on its own pulled DIS's field around it, ~100 px off on Wan's 2x cadence steps), and inside the inpainted
        holes, where the plates have nothing to hold it, filled in from the real floor around them."""
        k = (sa, i, sb, j, fine)
        if k not in self.flows:
            f = flow(self.gc(sa, i), self.gc(sb, j), fine)
            self.flows[k] = fill_flow(f, half_region(self.inpainted(sa, i), self.inpainted(sb, j)))
        return self.flows[k]

    def clean(self, side, i):
        """The source frame with its earbud (the hole mask: the earbud and a 5 px rim) inpainted away: what is
        interpolated and warped, so no copy of the earbud is ever carried by a flow (cached)."""
        k = ("clean", side, i)
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        img = self.frame(side, i)
        hole = self.inpainted(side, i)
        if hole is not None:
            ys, xs = np.nonzero(hole > 0.5)
            x0, x1 = max(0, xs.min() - 16), min(W, xs.max() + 17)
            y0, y1 = max(0, ys.min() - 16), min(H, ys.max() + 17)
            crop = np.clip(img[y0:y1, x0:x1] * 255 + 0.5, 0, 255).astype(np.uint8)
            img = img.copy()
            img[y0:y1, x0:x1] = cv2.inpaint(crop, (hole[y0:y1, x0:x1] > 0.5).astype(np.uint8), 7,
                                            cv2.INPAINT_TELEA).astype(np.float32) / 255
        self.cache[k] = img
        while len(self.cache) > 40:
            self.cache.popitem(last=False)
        return img

    def inpainted(self, side, i):
        """Exactly the pixels clean() inpaints (1.0), widened 2 px and feathered outward: what a blend must not
        trust in that plate. None without the earbud."""
        k = ("inp", side, i)
        if k not in self.flows:
            m = self.mask(side, i, "hole")
            if m is None:
                self.flows[k] = None
            else:
                hard = cv2.dilate((m > 0.02).astype(np.uint8), np.ones((3, 3), np.uint8)).astype(np.float32)
                soft = cv2.GaussianBlur(cv2.dilate(hard, np.ones((5, 5), np.uint8)), (0, 0), 1.2)
                self.flows[k] = np.maximum(hard, soft)
        return self.flows[k]

    def paste_earbud(self, out, side, n, v, k=None, how=""):
        """Paste source frame n's earbud (its sprite mask: the earbud and 3 px, from the real frame) into `out`,
        moved rigidly by one translation v (out(x) = frame(x + v))."""
        T = self.mask(side, n, "sprite")
        if T is None:
            return
        paste_shifted(out, self.frame(side, n), v, T)
        if k is not None:
            self.stats["earbud_source"][k] = "%s%d" % (side, n)
            self.stats.setdefault("earbud_shift", {})[k] = [how] + [round(float(x), 2) for x in v]

    def b_zoom(self, i):
        za = self.A.zoom
        if za == 1.0 or not hasattr(self, "Q"):
            return za if za != 1.0 else 1.0
        x = (i - self.Q) / max(self.zoom_end - self.Q, 1)
        return float(za + (1 - za) * smoothstep(x))

    def floor_locked_track(self, side, sigma=2.5):
        """Step 4c: the resting earbud's path (all of B). Two things would make the pasted earbud jump by up to 12-24
        px frame to frame: a centre tracked as the centroid of the largest bright component, because Wan's core keeps
        splitting into two and joining again (the centre jumps by 5-13 px each time); and B being a 30 fps take with
        2x cadence steps (hitches), which the paste would follow. So the centre is the whole earbud's (its sprite
        matte's weighted centroid, clip.c_rob, also what the paste moves), and the path is that centre as a smooth
        function of B's content time (the hitch-free clock, step 5): a local linear fit with Gaussian weights (sigma
        frames of content time), re-weighted twice against outliers, the frames where it touches the frame's edge left
        out of the fit. The floor's own flow under it was no help: on the treads' stripes it is off by 20-50 px on the
        cadence steps. Sets clip.c_smooth; returns the largest correction (px)."""
        c = self.clip(side)
        c.robust_centres()
        idx = [i for i in range(c.last + 1) if c.eb[i] is not None and c.c_rob[i] is not None]
        c.c_smooth = [None] * c.n
        if len(idx) < 4:
            return 0.0
        tau = np.array([c.tau_at(i) for i in idx])
        cs = np.array([c.c_rob[i] for i in idx], np.float64)
        edge = np.array([c.eb[i]["box"][0] <= 3 or c.eb[i]["box"][1] <= 3 or c.eb[i]["box"][2] >= W - 3
                         or c.eb[i]["box"][3] >= H - 3 for i in idx])
        rw = np.where(edge, 0.0, 1.0)
        fit = cs.copy()
        for _ in range(3):
            for n, t in enumerate(tau):
                w = np.exp(-0.5 * ((tau - t) / sigma) ** 2) * rw
                X = np.c_[np.ones(len(tau)), tau - t]
                Wm = X.T * w
                coef = np.linalg.lstsq(Wm @ X + 1e-6 * np.eye(2), Wm @ cs, rcond=None)[0]
                fit[n] = coef[0]
            r = np.hypot(*(cs - fit).T)
            sc = max(1.4826 * float(np.median(r[rw > 0])) if (rw > 0).any() else 1.0, 1.0)
            rw = np.where(edge, 0.0, 1.0 / (1.0 + (r / (2.5 * sc)) ** 2))
        for i, xy in zip(idx, fit):
            c.c_smooth[i] = (float(xy[0]), float(xy[1]))
        return float(np.max(np.hypot(*(cs - fit).T)))

    def bridge_earbud_path(self, plan):
        """The resting earbud's place on each bridge frame (output px before the overscan): a cubic Hermite in
        output frames from the last frame before the bridge (its place and its velocity there) to the first one
        after it, so the earbud's motion is continuous in place and speed through the handover, with no stall and
        catch-up; the plate under it hands over from A's floor to B's in the dissolve."""
        k0, k1 = self.k_bridge
        if k0 is None or k0 < 2 or k1 + 2 >= len(plan):
            return {}
        def pos(k):
            f = plan[k]
            if f["src"] not in ("A", "B"):
                return None
            return self.clip(f["src"]).earbud_pos(f["x"])
        pa, pa1, pb, pb1 = pos(k0 - 1), pos(k0 - 2), pos(k1 + 1), pos(k1 + 2)
        if None in (pa, pa1, pb, pb1):
            return {}
        pa, pa1, pb, pb1 = (np.array(v, np.float64) for v in (pa, pa1, pb, pb1))
        va, vb = pa - pa1, pb1 - pb
        n = (k1 + 1) - (k0 - 1)
        out = {}
        for k in range(k0, k1 + 1):
            u = (k - (k0 - 1)) / n
            h00, h10, h01, h11 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, \
                u ** 3 - u ** 2
            out[k] = tuple(h00 * pa + h10 * n * va + h01 * pb + h11 * n * vb)
        return out

    def plan(self):
        A, B, a = self.A, self.B, self.args
        p = a.seam_keep
        self.lock_px = self.floor_locked_track("B") if a.earbud_floor_lock else None
        vA_s, vB_s = A.v_out, B.v_out
        tau_a0 = a.a_start * A.fps                                # A's content time where the clip starts
        s_a0 = A.pos_at_tau(tau_a0)
        v_arrive = float(vA_s[A.last - 1])                       # A's speed into its last frame
        if a.a_moving:
            # A arrives at mid.png moving (the engine render glides on into B): that is no ease-out to replay, so A
            # plays at its own speed up to the bridge's A half (about --bridge-frames / 2 before its end), and B is
            # joined where its own ease-in first reaches A's arrival speed; only B's slower head is replayed faster
            iA = max(1, A.last - int(round(a.bridge_frames / 2)) - 2)
            jB = int(np.nonzero(vB_s >= min(v_arrive, p * vB_s.max()))[0][0])
        else:
            iA = int(np.nonzero(vA_s >= p * vA_s.max())[0][-1])
            jB = int(np.nonzero(vB_s >= p * vB_s.max())[0][0])
        if iA + 0.5 <= s_a0 + 2:
            sys.exit("--a-start %.2f s is past A's seam (A frame %d)" % (a.a_start, iA))
        sA, sB = iA + 0.5, jB + 0.5
        vA, vB = float(vA_s[iA]), float(vB_s[jB])
        d = 0.5 * (vA + vB) * a.bridge_frames / 2
        candP = range(int(math.ceil(sA)), A.last + 1)
        P = min(candP, key=lambda i: abs(A.arc[A.last] - A.arc[i] - d)) if len(candP) else A.last
        candQ = range(0, int(math.floor(sB)) + 1)
        Q = min(candQ, key=lambda j: abs(B.arc[j] - d))
        self.P, self.Q = P, Q
        self.zoom_end = B.last          # refined below once the end morph start is known
        # The bridge. Its path is a Hermite curve per pixel from P to Q (leaving P with A's motion, arriving at Q
        # with B's); its pictures are the footage between P and Q (A's last frames, B's first) moved onto that path,
        # each frame only by how far the curve cuts the corner at mid.png.
        # Every footage frame's place relative to P (C_k, half res) comes from chaining neighbour flows through A's
        # frame nearest mid.png and B's: small steps cannot slide along the stair treads, which a direct P -> Q
        # estimate did. The chain's end is refined by a direct estimate of what it leaves (Q warped back by the
        # chain, against P), spread along the footage.
        aj, bj = max(A.anchor[1], P), min(B.anchor[0], Q)
        steps = ([("A", i, "A", i + 1) for i in range(P, aj)] + [("A", aj, "B", bj)]
                 + [("B", j, "B", j + 1) for j in range(bj, Q)])
        C = np.zeros((FH, FW, 2), np.float32)
        foot, arcs = [("A", P, C)], [0.0]
        fb_err = np.zeros((FH, FW), np.float32)        # on P's grid: the worst forward-backward error of any step
        for sa, i, sb, j in steps:
            f = self.fl(sa, i, sb, j)
            if a.bridge_fb > 0:
                e = fb_error(f, self.fl(sb, j, sa, i))
                fb_err = np.maximum(fb_err, sample(e, C[..., 0], C[..., 1]))
            C = C + sample(f, C[..., 0], C[..., 1])
            foot.append((sb, j, C))
            arcs.append(arcs[-1] + 2 * float(np.median(np.hypot(f[..., 0], f[..., 1]))))
        gP, gQ = self.gc("A", P), self.gc("B", Q)
        Qw = np.clip(sample(gQ.astype(np.float32), C[..., 0], C[..., 1]), 0, 255).astype(np.uint8)
        R = _DIS_FINE.calc(gP, Qw, None)
        F = (R + sample(C, R[..., 0], R[..., 1])).astype(np.float32)
        # Where any step's flow fails its forward-backward check (the engine's and Wan's seat ends and far treads
        # disagree; occlusions at the panels' bases), a per-pixel warp tears the picture (melting panel bases and
        # kinked treads at the left). There every field of the bridge (the path, the tangents, each footage frame's
        # place) is replaced by a smooth fill from around it (normalized convolution), so each footage frame is moved
        # there by its own camera motion only and A's footage dissolves into B's without a two-way morph.
        self.bridge_bad = None
        self.bridge_fb_err = fb_err
        if a.bridge_fb > 0:
            fb_err = np.maximum(fb_err, fb_error(R, _DIS_FINE.calc(Qw, gP, None)))
            self.bridge_fb_err = fb_err
            m = cv2.morphologyEx((fb_err > a.bridge_fb).astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
            if a.bridge_fb_region > 0:
                # a small island that passes the check inside a mostly failing neighbourhood (the stairs' dark
                # carpet, the left seat ends) is failing too: its own per-pixel field next to the smooth fill
                # around it shears the far treads into 1-3 px Z-steps
                share = cv2.GaussianBlur(m.astype(np.float32), (0, 0), a.bridge_fb_region)
                m = np.maximum(m, (share > 0.5).astype(np.uint8))
            m = cv2.dilate(m, _ellipse(6))
            self.bridge_bad = np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), a.bridge_fb_feather) * 1.6,
                                      0, 1)
            F = smooth_in(F, self.bridge_bad)
        L_foot = max(arcs[-1], 1e-6)
        phi = np.array(arcs) / L_foot
        self.foot = []
        for (side, idx, Ck), ph in zip(foot, phi):
            Ck = smooth_in((Ck + ph * (F - C)).astype(np.float32), self.bridge_bad)
            self.foot.append(dict(side=side, idx=idx, C=Ck, inv=invert(Ck, 8), phi=float(ph), primary=True))
        # the handover: between A's last footage frame and B's first, where both are nearest mid.png
        ia = max(k for k, e in enumerate(self.foot) if e["side"] == "A")
        self.phi_h = 0.5 * (self.foot[ia]["phi"] + self.foot[ia + 1]["phi"])
        # more footage on either side (A before P, B after Q), only to fill what the bridge's warps need from beyond
        # the frame's edge: places chained the same way, from P backwards and from Q (refined) onwards
        Ce, ph_e = np.zeros((FH, FW, 2), np.float32), 0.0
        for i in range(P, max(P - a.fill_frames, 0), -1):
            f = self.fl("A", i, "A", i - 1)
            ph_e -= 2 * float(np.median(np.hypot(f[..., 0], f[..., 1]))) / L_foot
            Ce = Ce + sample(f, Ce[..., 0], Ce[..., 1])
            Cs = smooth_in(Ce, self.bridge_bad)
            self.foot.append(dict(side="A", idx=i - 1, C=Cs, inv=invert(Cs, 8), phi=ph_e, primary=False))
        Ce, ph_e = self.foot[len(foot) - 1]["C"].copy(), 1.0
        for j in range(Q, min(Q + a.fill_frames, B.last)):
            f = self.fl("B", j, "B", j + 1)
            ph_e += 2 * float(np.median(np.hypot(f[..., 0], f[..., 1]))) / L_foot
            Ce = Ce + sample(f, Ce[..., 0], Ce[..., 1])
            Cs = smooth_in(Ce, self.bridge_bad)
            self.foot.append(dict(side="B", idx=j + 1, C=Cs, inv=invert(Cs, 8), phi=ph_e, primary=False))
        D = 2 * float(np.median(np.hypot(F[..., 0], F[..., 1])))                 # px at 1920
        VP = self.fl("A", P, "A", P + 1) if P < A.last else self.fl("A", P - 1, "A", P)
        VQ = self.fl("B", Q, "B", Q + 1)
        def tangent(V):
            m = float(np.median(np.hypot(V[..., 0], V[..., 1])))
            return (V * (D / 2 / m)).astype(np.float32) if m > 0.1 else F.copy()
        self.F, self.TP, self.TQ = F, smooth_in(tangent(VP), self.bridge_bad), tangent(VQ)
        self.TQd = smooth_in(sample(self.TQ, F[..., 0], F[..., 1]), self.bridge_bad)   # B's motion where each P
        # pixel lands in Q
        self.angle_PQ = [float(np.degrees(np.arctan2(*np.median(V.reshape(-1, 2), 0)[::-1])))
                         for V in (VP, F, VQ)]
        # the bridge's length is the arc length of its own path, and u is spread along it so the bridge moves at
        # the window's speed throughout
        us = np.linspace(0, 1, 33)
        prev, arc_u = None, [0.0]
        for uu in us:
            cur = self.hermite_disp(uu)
            if prev is not None:
                arc_u.append(arc_u[-1] + 2 * float(np.median(np.hypot(*(cur - prev).reshape(-1, 2).T))))
            prev = cur
        self.bridge_u, self.bridge_arc = us, np.array(arc_u)
        D = float(self.bridge_arc[-1])
        LA1 = A.arc[P] - A.arc_at(sA)
        LB1 = B.arc_at(sB) - B.arc[Q]
        L = LA1 + D + LB1
        Wn = 2 * L / (vA + vB)                                   # window length in output frames
        TA = (A.tau_at(sA) - tau_a0) / A.fps                     # seconds of A before the window (native speed)
        TW = Wn / FPS
        TB = (B.tau[B.last] - B.tau_at(sB)) / B.fps              # seconds of B after it at native speed
        H0, Hn = a.hold_first, a.hold_frames
        # motion frames k = 0..Nm: A and the window at native speed; B fills the rest, played faster only if the
        # whole would run over --max-seconds (the tumble never is)
        n_aw = (TA + TW) * FPS
        n_b_native = TB * FPS
        budget = a.max_seconds * FPS - H0 - (Hn - 1) - 1         # Nm at most
        kappa = max(1.0, n_b_native / max(budget - n_aw, 1.0))
        if kappa > a.max_b_speedup:
            log("  WARNING: B would need x%.3f to fit %.2f s; capped at x%.2f, the clip runs over"
                % (kappa, a.max_seconds, a.max_b_speedup))
            kappa = a.max_b_speedup
        Nm = int(round(n_aw + n_b_native / kappa))
        T_end = Nm / FPS - TA - TW                               # seconds of output for B
        ramp = 0.5
        def b_time(x, K):                                        # B's native seconds after x output seconds
            # rate(x) = 1 + (K - 1) smoothstep(x / ramp), then K: the integral of smoothstep over [0, r] is
            # ramp (u^3 - u^4 / 2) with u = r / ramp
            r = min(x, ramp)
            u_ = r / ramp
            g = r + (K - 1) * ramp * (u_ ** 3 - u_ ** 4 / 2)
            if x > ramp:
                g += K * (x - ramp)
            return g
        lo, hi = 0.5, 3.0                                         # solve b_time(T_end, K) = TB
        for _ in range(60):
            K = 0.5 * (lo + hi)
            if b_time(T_end, K) < TB:
                lo = K
            else:
                hi = K
        K = 0.5 * (lo + hi)
        specs = []
        for k in range(Nm + 1):
            t = k / FPS
            if t < TA:
                specs.append(("A", A.pos_at_tau(tau_a0 + t * A.fps)))
            elif t < TA + TW:
                w = (t - TA) * FPS / Wn
                S = Wn * (vA * w + (vB - vA) * (w ** 3 - w ** 4 / 2))
                if S < LA1:
                    specs.append(("A", A.pos_at_arc(A.arc_at(sA) + S)))
                elif S < LA1 + D:
                    specs.append(("bridge", float(np.interp(S - LA1, self.bridge_arc, self.bridge_u))))
                else:
                    specs.append(("B", B.pos_at_arc(B.arc[Q] + S - LA1 - D)))
            else:
                bt = b_time(t - TA - TW, K) if k < Nm else TB
                specs.append(("B", B.pos_at_tau(B.tau_at(sB) + bt * B.fps)))
        # the end (--b-ease-out seconds): B's last stretch replayed by arc length along a cubic ease-out from the
        # speed it comes in with to rest on its last frame, so the picture slows steadily into the end morph (B's
        # 30 fps cadence left a +-0.4 px/frame wobble at 2 px/frame there, read as a speed bump)
        self.b_ease = None
        nE = int(round(a.b_ease_out * FPS))
        if a.b_ease_out > 0 and nE >= 4 and Nm - nE - 1 >= 0 and specs[Nm - nE - 1][0] == "B":
            kE0 = Nm - nE
            arc0 = B.arc_at(specs[kE0][1])
            v0 = arc0 - B.arc_at(specs[kE0 - 1][1])
            Lr = float(B.arc[B.last] - arc0)
            if Lr > 1.0 and v0 > 0:
                m0 = min(v0 * nE / Lr, 3.0)
                for k in range(kE0, Nm + 1):
                    u_ = (k - kE0) / nE
                    g = (-2 * u_ ** 3 + 3 * u_ ** 2) + m0 * (u_ ** 3 - 2 * u_ ** 2 + u_)
                    specs[k] = ("B", B.pos_at_arc(arc0 + Lr * g))
                self.b_ease = dict(first_motion_frame=kE0, frames=nE, arc_px=round(Lr, 1), speed_in=round(v0, 2),
                                   slope=round(m0, 3))
        Mn = min(a.morph_frames, Nm)
        alpha = [float((k - (Nm - Mn)) / Mn) if k > Nm - Mn else 0.0 for k in range(Nm + 1)]
        plan = [dict(src=specs[0][0], x=specs[0][1], alpha=0.0, held=True) for _ in range(H0)]
        plan += [dict(src=s, x=x, alpha=al) for (s, x), al in zip(specs, alpha)]
        plan += [dict(src="E", x=0.0, alpha=1.0) for _ in range(Hn - 1)]
        self.frames_plan = plan
        ks = [k for k, f in enumerate(plan) if f["src"] == "bridge"]
        self.k_bridge = (ks[0], ks[-1]) if ks else (None, None)
        self.bridge_eb = self.bridge_earbud_path(plan) if a.earbud_floor_lock else {}
        self.k_seam = min(range(len(plan)), key=lambda k: abs(plan[k]["x"] - self.phi_h) if plan[k]["src"] == "bridge"
                          else 9e9) if ks else None
        self.k_window = (H0 + int(math.ceil(TA * FPS)), H0 + int(math.floor((TA + TW) * FPS)))
        self.k_morph = H0 + Nm - Mn + 1
        self.k_hold = H0 + Nm
        if A.zoom != 1.0:   # B eases from A's zoom to 1.0 by the start of the end morph
            mstart = plan[self.k_morph]
            self.zoom_end = int(math.floor(mstart["x"])) if mstart["src"] == "B" else B.last
            self.cache.clear()
            self.flows = {k: v for k, v in self.flows.items() if "B" not in k[:3]}
        # where the paint-out lands in the output
        k_paint = [k for k, f in enumerate(plan) if f["src"] == "B" and any(
            pp["first"] - 1 < f["x"] < pp["last"] + 1 for pp in B.paints)]
        self.k_paint = (k_paint[0], k_paint[-1]) if k_paint else None
        # the overscan: a push-in about the centre around the bridge, just enough that no pixel its footage cannot
        # give stays in the picture (the corner the Hermite path cuts needs up to a few % beyond the footage's
        # edges; stitching that from other footage frames left torn lines along the edges), eased in and out
        self.zoom_k = {}
        need = [self.overscan_needed(plan[k]["x"]) for k in ks] if ks and a.overscan else []
        zpk = max(need) if need else 1.0
        if zpk > 1.0005:
            zpk = min(1 + (zpk - 1) * 1.08 + 0.002, a.overscan_max)     # past the cap the edge fill takes over
            kb0, kb1, rp = ks[0], ks[-1], a.overscan_ramp
            # the release after the bridge (--overscan-release, frames) is slower than the push-in: over B's still
            # head a release reads as a pull-back; stretched, it ends inside B's own move
            rr = a.overscan_release or rp
            for k in range(max(0, kb0 - rp), min(len(plan), kb1 + rr + 1)):
                w = (smoothstep((k - (kb0 - rp)) / rp) if k < kb0 else 1.0 if k <= kb1
                     else 1 - smoothstep((k - kb1) / rr))
                if w > 0:
                    self.zoom_k[k] = float(1 + (zpk - 1) * w)
        # the end morph's geometry (--morph-ease): the B frames' distance from dream_end.png (median flow length)
        # is r_k = (1 - tg_k) D_k on screen; tg is chosen so that r follows a cubic from the last frame before the
        # morph (its value and its rate) down to 0 at rest, so the picture keeps slowing into the hold instead of
        # the morph's own pull speeding it up again
        self.morph_tg = {}
        if a.morph_ease and Mn >= 3 and all(plan[k]["src"] == "B" for k in range(self.k_morph - 2, self.k_hold)):
            xs = [plan[k]["x"] for k in range(self.k_morph - 2, self.k_hold)]
            j0, j1 = max(0, int(math.floor(min(xs))) - 1), min(B.last, int(math.ceil(max(xs))) + 1)
            js = list(range(j0, j1 + 1))
            DB = [2 * float(np.median(np.hypot(*flow(self.gray("B", j), self.gE, fine=True).transpose(2, 0, 1))))
                  for j in js]
            Dx = lambda x: float(np.interp(x, js, DB))
            k0 = self.k_morph - 1
            L = self.k_hold - k0
            D0 = Dx(plan[k0]["x"])
            m0 = (Dx(plan[k0]["x"]) - Dx(plan[k0 - 1]["x"])) * L
            prev = 0.0
            for k in range(self.k_morph, self.k_hold):
                u_ = (k - k0) / L
                r = D0 * (2 * u_ ** 3 - 3 * u_ ** 2 + 1) + m0 * (u_ ** 3 - 2 * u_ ** 2 + u_)
                tg = float(np.clip(1 - max(r, 0.0) / max(Dx(plan[k]["x"]), 1e-3), 0, 1))
                prev = max(prev, tg)
                self.morph_tg[k] = prev
            self.morph_D = dict(B_frames=js, distance_px=[round(v, 2) for v in DB])
        # the push-in toward the earbud (--push-in Z,T0,T1,T2,T3 seconds): the picture is pushed in to Z between T0
        # and T1 (smoothstep), held, and let go between T2 and T3, about a point drawn toward the earbud (its place
        # smoothed over +-10 frames, 0.6 of the way from the centre, limited so the crop stays inside the frame and
        # inside the bridge's overscan crop). Merged with the overscan (the larger zoom wins). The 1080p frame has
        # the headroom: at 1.10 the 720p .ogv is still a downscale. The release is placed where B's own dolly is
        # strongest, so the radial motion never turns into a pull-back.
        self.zoom_o = {}
        self.push = None
        if a.push_in:
            vals = [float(v) for v in a.push_in.split(",")]
            Z, t0, t1, t2, t3 = vals[:5]
            fixed = vals[5:7] if len(vals) >= 7 else None     # X,Y: a zoom about that fixed point instead
            pos = []
            for k, f in enumerate(plan):
                q = None
                if f["src"] in ("A", "B"):
                    q = self.clip(f["src"]).earbud_pos(f["x"])
                elif f["src"] == "bridge":
                    q = self.bridge_eb.get(k)
                pos.append(q)
            seen = [k for k, q in enumerate(pos) if q is not None]
            cx, cy = (W - 1) / 2, (H - 1) / 2
            ex, ey, wt = np.zeros(len(plan)), np.zeros(len(plan)), np.zeros(len(plan))
            if seen:
                last = seen[-1]
                for k in range(len(plan)):
                    q = pos[k] if pos[k] is not None else pos[min(seen, key=lambda j: abs(j - k))]
                    ex[k], ey[k] = q
                    # after it has left (or before it is found), drawn back to the centre over a second
                    wt[k] = 1.0 if k <= last else max(0.0, 1 - (k - last) / FPS)
            ex = gaussian_filter1d(cx + (ex - cx) * wt, 10, mode="nearest")
            ey = gaussian_filter1d(cy + (ey - cy) * wt, 10, mode="nearest")
            for k in range(len(plan)):
                t = k / FPS
                w = float(smoothstep((t - t0) / max(t1 - t0, 1e-3)) * (1 - smoothstep((t - t2) / max(t3 - t2, 1e-3))))
                zp = 1 + (Z - 1) * w
                zo = self.zoom_k.get(k, 1.0)
                z = max(zp, zo)
                if z <= 1.0001:
                    continue
                self.zoom_k[k] = float(z)
                lx, ly = (W / 2) * (1 / zo - 1 / z) * 0.95, (H / 2) * (1 / zo - 1 / z) * 0.95
                if fixed:
                    # about a fixed point p (output p shows source p): the crop's centre is c + (p - c)(1 - 1/z),
                    # so the picture only grows about p and the crop never follows anything
                    self.zoom_o[k] = (float(np.clip((fixed[0] - cx) * (1 - 1 / z), -lx, lx)),
                                      float(np.clip((fixed[1] - cy) * (1 - 1 / z), -ly, ly)))
                    continue
                self.zoom_o[k] = (float(np.clip(0.6 * (ex[k] - cx), -lx, lx)), float(np.clip(0.6 * (ey[k] - cy), -ly, ly)))
            self.push = dict(zoom=Z, seconds=[t0, t1, t2, t3], about=fixed or "the earbud (0.6 of the way)")
        a_native = [(k, f["x"]) for k, f in enumerate(plan) if f["src"] == "A" and not f.get("held")]
        self.info = dict(seam_keep=p, a_moving=bool(a.a_moving), a_even=bool(A.even),
                         A_arrival_speed=round(v_arrive, 2), A_cut=sA, B_cut=sB, vA=round(vA, 2), vB=round(vB, 2),
                         P=P, Q=Q,
                         a_start_s=a.a_start, hold_first=H0,
                         A_native_speed_frames=[a_native[0][0], self.k_window[0] - 1] if a_native else None,
                         bridge_px=round(D, 1), A_tail_px=round(LA1, 1), B_head_px=round(LB1, 1),
                         window_frames=round(Wn, 1), A_speedup=1.0, B_speedup=round(K, 3),
                         B_native_seconds=round(TB, 3), B_output_seconds=round(T_end, 3),
                         motion_frames=Nm + 1, hold_frames=Hn, morph_frames=Mn, A_last_valid=A.last,
                         B_last_valid=B.last, direction_deg_A_chord_B=[round(v, 1) for v in self.angle_PQ],
                         handover_phi=round(self.phi_h, 3), dissolve=a.dissolve,
                         overscan_needed=[round(v, 4) for v in need], overscan_peak=round(zpk, 4),
                         overscan_frames=[min(self.zoom_k), max(self.zoom_k)] if self.zoom_k else None,
                         morph_tg={k: round(v, 3) for k, v in self.morph_tg.items()},
                         b_ease_out=self.b_ease, push_in=self.push,
                         zoom_peak=round(max(self.zoom_k.values()), 4) if self.zoom_k else 1.0,
                         morph_distance=getattr(self, "morph_D", None),
                         earbud_floor_lock_px=round(self.lock_px, 2) if self.lock_px is not None else None,
                         bridge_bad_share=round(float((self.bridge_bad > 0.5).mean()), 4)
                         if self.bridge_bad is not None else None,
                         A_zoom=round(A.zoom, 4), k_window=self.k_window, k_bridge=self.k_bridge,
                         k_seam=self.k_seam, k_morph=self.k_morph, k_hold=self.k_hold, k_paint=self.k_paint,
                         n_frames=len(plan), seconds=round(len(plan) / FPS, 3),
                         paint=[{k: v for k, v in pp.items()} for pp in B.paints + A.paints])
        return plan

    def hermite_disp(self, u):
        """Displacement of each P pixel at u on the bridge: x -> x + h10 TP + h01 F + h11 TQ (half res)."""
        u = float(u)
        h10, h01, h11 = u ** 3 - 2 * u ** 2 + u, -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
        return h10 * self.TP + h01 * self.F + h11 * self.TQd

    def bridge_primaries(self, u):
        """The footage frames a bridge frame at u is made of, with their weights: A's frame(s) at the same arc
        fraction (past A's last, that last one) and B's likewise, A's side handing over to B's in a dissolve of
        --dissolve of the bridge centred on the handover."""
        dis = self.args.dissolve
        wB = float(smoothstep((u - (self.phi_h - dis / 2)) / dis))
        prim = []
        for side, wside in (("A", 1 - wB), ("B", wB)):
            if wside < 1e-3:
                continue
            ent = [e for e in self.foot if e["side"] == side and e["primary"]]
            ph = [e["phi"] for e in ent]
            if u <= ph[0]:
                use = [(ent[0], 1.0)]
            elif u >= ph[-1]:
                use = [(ent[-1], 1.0)]
            else:
                j = int(np.searchsorted(ph, u, side="right")) - 1
                t = (u - ph[j]) / max(ph[j + 1] - ph[j], 1e-6)
                use = [(ent[j], 1 - t), (ent[j + 1], t)]
            prim += [(e, w * wside) for e, w in use if w * wside > 1e-3]
        return prim

    def overscan_needed(self, u):
        """The zoom about the centre that puts every pixel of a bridge frame its footage cannot give (the warp
        would sample beyond the footage's edge) outside the picture."""
        dP = self.hermite_disp(u)
        cover = np.zeros((H, W), np.float32)
        for e, _ in self.bridge_primaries(u):
            ek = sample(dP - e["C"], e["inv"][..., 0], e["inv"][..., 1])
            X, Y = coords_full(invert(ek, 6))
            cover = np.maximum(cover, inside(X, Y))
        ys, xs = np.nonzero(cover < 0.5)
        if not len(xs):
            return 1.0
        cx, cy = (W - 1) / 2, (H - 1) / 2
        return float(np.max(np.minimum(cx / np.maximum(np.abs(xs - cx), 1), cy / np.maximum(np.abs(ys - cy), 1))))

    def foot_render(self, e, dP):
        """One footage frame moved from where its pixels are (C_k) to their place dP: (image, soft inside-mask,
        warp confidence (half res), earbud mask on the output grid)."""
        ek = sample(dP - e["C"], e["inv"][..., 0], e["inv"][..., 1])     # on this frame's grid: where its pixels go
        b, r = invert(ek, 6, residual=True)
        img, v = warp_full(self.clean(e["side"], e["idx"]), b)
        return img, feather_inside(v), np.exp(-r ** 2).astype(np.float32), warp_mask_full(
            self.mask(e["side"], e["idx"], "sprite"), b), b

    def bridge_render(self, u, k=None):
        """Bridge frame at u. A's footage frame(s) at the same arc fraction (past A's last, that last one) and B's
        likewise, each moved onto the Hermite path; A's side hands over to B's in a dissolve of --dissolve of the
        bridge centred on the handover. Samples from beyond a frame's edge get no weight; what neither side covers
        comes from the nearest other footage frame that does (feathered); the earbud's mask takes the heaviest
        footage frame alone."""
        u = float(u)
        dP = self.hermite_disp(u)
        got = [(self.foot_render(e, dP), w, e) for e, w in self.bridge_primaries(u)]
        num = np.zeros((H, W, 3), np.float32)
        den = np.zeros((H, W), np.float32)
        cover = np.zeros((H, W), np.float32)
        for (img, v, conf, _, _), w, _ in got:
            c = w * (up(conf) + 0.02) * (v + 1e-4)
            num += c[..., None] * img
            den += c
            cover = np.maximum(cover, v)
        out = num / den[..., None]
        uncovered = 0
        if cover.min() < 0.999:
            # fill from the other footage frames, nearest first, until everything is covered
            used = {(e["side"], e["idx"]) for _, _, e in got}
            rest = sorted([e for e in self.foot if (e["side"], e["idx"]) not in used], key=lambda e: abs(e["phi"] - u))
            fnum = np.zeros((H, W, 3), np.float32)
            fden = np.zeros((H, W), np.float32)
            fcov = np.zeros((H, W), np.float32)
            need = cover < 0.999
            for rank, e in enumerate(rest[:12]):
                img, v, conf, _, _ = self.foot_render(e, dP)
                c = (0.25 ** rank) * (up(conf) + 0.02) * v * (1 - fcov)
                fnum += c[..., None] * img
                fden += c
                fcov = np.maximum(fcov, v)
                if fcov[need].min() >= 0.999:
                    break
            fill = fnum / np.maximum(fden, 1e-12)[..., None]
            have = fden > 1e-9
            gap = (cover < 1e-3) & ~have
            uncovered = int(gap.sum())
            fill = np.where(have[..., None], fill, out)      # last resort: the reflected samples of the sides
            out = cover[..., None] * out + (1 - cover[..., None]) * fill
        # the earbud: the footage is clean plates; the heaviest footage frame that has it gives it, pasted whole and
        # moved rigidly by one translation (the median of that frame's warp over it)
        withe = [g for g in got if g[0][3] is not None]
        if withe:
            top = max(withe, key=lambda g: g[1])
            target = self.bridge_eb.get(k) if k is not None else None
            if target is not None:
                # the earbud rests: it rides the bridge's own path at A's earbud (floor-locked to the plate), handing
                # over to B's resting path as the footage does (see bridge_earbud_path)
                def put(img, g, rec):
                    sc_ = self.clip(g[2]["side"])
                    sc_.robust_centres()
                    cn = sc_.c_rob[g[2]["idx"]] or sc_.eb[g[2]["idx"]]["c"]
                    self.paste_earbud(img, g[2]["side"], g[2]["idx"],
                                      np.array([cn[0] - target[0], cn[1] - target[1]], np.float32),
                                      k if rec else None, "bridge-path")
                # --earbud-xfade: while both sides' footage carries weight, A's earbud and B's are each pasted on
                # the same plate and cross-dissolved by the footage's own weights (the handover was one frame,
                # A107 -> B6: a 12 % smaller earbud and a crisper grille, a pop)
                sides = {}
                for g in withe:
                    sd = g[2]["side"]
                    if sd not in sides or g[1] > sides[sd][1]:
                        sides[sd] = g
                wsd = {sd: sum(g[1] for g in got if g[2]["side"] == sd) for sd in ("A", "B")}
                if self.args.earbud_xfade and len(sides) == 2 and min(wsd.values()) > 1e-3:
                    wb = wsd["B"] / (wsd["A"] + wsd["B"])
                    oa, ob = out.copy(), out.copy()
                    put(oa, sides["A"], top[2]["side"] == "A")
                    put(ob, sides["B"], top[2]["side"] == "B")
                    out = (1 - wb) * oa + wb * ob
                    self.stats.setdefault("earbud_xfade", {})[k] = round(float(wb), 3)
                else:
                    put(out, top, True)
            else:
                sel = cv2.resize(top[0][3], (FW, FH), interpolation=cv2.INTER_AREA) > 0.3
                if sel.any():
                    self.paste_earbud(out, top[2]["side"], top[2]["idx"], 2 * np.median(top[0][4][sel], 0), k,
                                      "bridge")
        if k is not None:
            self.stats["bridge_uncovered_px"][k] = uncovered
        return out

    def src_frame(self, side, s, k=None):
        """A source position s (fractional frame) as a picture (step 5): a real frame when s is one, else its two
        neighbours warped by their flow and blended. With the earbud in either: their clean plates are blended (an
        inpainted hole giving way to real floor from the other frame, or from i-1 / i+2), and the nearer real frame's
        earbud is pasted on top, moved rigidly along its own track."""
        c = self.clip(side)
        s = min(max(s, 0.0), float(c.last))
        i = int(math.floor(s))
        t = s - i
        if (c.c_smooth is not None and i < c.last and c.c_smooth[i] is not None and c.c_smooth[i + 1] is not None
                and c.eb[i] is not None and c.eb[i + 1] is not None):
            # a resting earbud on its floor-locked path: always the plate and the earbud pasted on that path, even
            # on a whole source frame (its own earbud there sits off the path by its tracking noise)
            t = min(max(t, 0.02), 0.98)
        elif t < 0.02 or i >= c.last:
            if k is not None and c.eb[i] is not None:
                self.stats["earbud_source"][k] = "%s%d" % (side, i)
            return self.frame(side, i)
        if t > 0.98:
            if k is not None and c.eb[i + 1] is not None:
                self.stats["earbud_source"][k] = "%s%d" % (side, i + 1)
            return self.frame(side, i + 1)
        f01, f10 = self.fl(side, i, side, i + 1), self.fl(side, i + 1, side, i)
        ft0 = -(1 - t) * t * f01 + t * t * f10
        ft1 = (1 - t) ** 2 * f01 - t * (1 - t) * f10
        m0 = sample(fb_mask(f01, f10), ft0[..., 0], ft0[..., 1])
        m1 = sample(fb_mask(f10, f01), ft1[..., 0], ft1[..., 1])
        has = c.eb[i] is not None or c.eb[i + 1] is not None
        # the earbud's frames are interpolated without it (clean plates), so no warped copy of it can exist
        get = self.clean if has else self.frame
        W0, v0 = warp_full(get(side, i), ft0)
        W1, v1 = warp_full(get(side, i + 1), ft1)
        if not has:
            return blend(W0, m0, 1 - t, W1, m1, t, v0=v0, v1=v1)
        # an inpainted hole gives way to real floor: first the other frame's, then, only where both neighbours had
        # the earbud, frame i-1's or i+2's, carried to this moment through the composed flows
        zero = np.zeros((H, W), np.float32)
        H0, H1 = self.inpainted(side, i), self.inpainted(side, i + 1)
        H0 = warp_mask_full(H0, ft0) if H0 is not None else zero
        H1 = warp_mask_full(H1, ft1) if H1 is not None else zero
        both = np.minimum(H0, H1)
        srcs = [(W0, (1 - t) * (up(m0) + 0.02) * (v0 + 1e-4) * (1 - 0.98 * H0)),
                (W1, t * (up(m1) + 0.02) * (v1 + 1e-4) * (1 - 0.98 * H1))]
        # each hole's rim beyond the sprite (3-9 px out) is real floor in its own frame; only the plate has it
        # inpainted. Where the neighbours' holes overlap (an earbud resting on the floor, or hopping between them)
        # nothing but inpainted plates was left there, and TELEA bled the dark carpet into the stripes: dark arcs and
        # notches around the earbud. The real frames' rims, carried by the floor flow, come back in by time weight.
        for j, ftj, wj, mj, vj in ((i, ft0, 1 - t, m0, v0), (i + 1, ft1, t, m1, v1)):
            Hj, Sj = self.inpainted(side, j), self.mask(side, j, "sprite")
            if Hj is not None and Sj is not None:
                ring = warp_mask_full(Hj * (1 - Sj), ftj)
                if ring.max() > 0.02:
                    srcs.append((warp_full(self.frame(side, j), ftj)[0], wj * (up(mj) + 0.02) * (vj + 1e-4) * ring))
        if both.max() > 0.02:
            for j, base, step in ((i - 1, ft0, (i, i - 1)), (i + 2, ft1, (i + 1, i + 2))):
                if 0 <= j <= c.last:
                    f = self.fl(side, step[0], side, step[1])
                    ftj = base + sample(f, base[..., 0], base[..., 1])
                    Wj, vj = warp_full(self.clean(side, j), ftj)
                    Hj = self.inpainted(side, j)
                    Hj = warp_mask_full(Hj, ftj) if Hj is not None else zero
                    srcs.append((Wj, 0.5 * both * vj * (1 - 0.98 * Hj)))
        num = np.zeros((H, W, 3), np.float32)
        den = np.zeros((H, W), np.float32)
        for Wj, a in srcs:
            num += a[..., None] * Wj
            den += a
        out = num / np.maximum(den, 1e-9)[..., None]
        if has:
            # the earbud: the nearer real frame's, pasted whole and moved rigidly (one translation) to where its own
            # track is at this moment, so it keeps its exact shape and is never blended. The dense flow is not
            # trusted for it: on the treads' stripes and the flat carpet its aperture errors reach ~100 px on Wan's
            # 2x cadence steps (harmless for the background, fatal for a small object).
            n, ftn = (i, ft0) if t < 0.5 else (i + 1, ft1)
            if c.eb[n] is None:
                n, ftn = (i + 1, ft1) if n == i else (i, ft0)
            v, how = c.track_shift(i, t, n), "track"
            if v is None:
                Mw = warp_mask_full(self.mask(side, n, "sprite"), ftn)
                sel = cv2.resize(Mw, (FW, FH), interpolation=cv2.INTER_AREA) > 0.3
                v, how = (2 * np.median(ftn[sel], 0) if sel.any() else np.zeros(2, np.float32)), "flow"
            self.paste_earbud(out, side, n, v, k, how)
        return out

    def end_render(self, img, a, k=None):
        """The end morph at a in (0, 1]: the B frame and dream_end.png warped toward each other (geometry eases in
        first, the picture follows); a sample from beyond its frame's edge gets no weight."""
        tg = self.morph_tg.get(k, float(smoothstep(min(1.0, a / 0.8)))) if k is not None else \
            float(smoothstep(min(1.0, a / 0.8)))
        tp = float(smoothstep((a - 0.2) / 0.8))
        g = gray_half(img)
        f0E, fE0 = flow(g, self.gE, fine=True), flow(self.gE, g, fine=True)
        ft0 = -(1 - tg) * tg * f0E + tg * tg * fE0
        ft1 = (1 - tg) ** 2 * f0E - tg * (1 - tg) * fE0
        m0 = sample(fb_mask(f0E, fE0), ft0[..., 0], ft0[..., 1])
        m1 = sample(fb_mask(fE0, f0E), ft1[..., 0], ft1[..., 1])
        W0, v0 = warp_full(img, ft0)
        W1, v1 = warp_full(self.E, ft1)
        v0, v1 = feather_inside(v0), feather_inside(v1)
        if k is not None:
            self.stats["morph_outside_px"][k] = [int((v0 < 1e-3).sum()), int((v1 < 1e-3).sum()),
                                                 round(2 * float(np.median(np.hypot(f0E[..., 0], f0E[..., 1]))), 2)]
        return blend(W0, m0 + 0.3, 1 - tp, W1, m1 + 0.3, tp, v0=v0, v1=v1)

    def render(self, spec, k=None):
        s = spec["src"]
        if s == "E":
            return self.E
        al = spec["alpha"]
        if al >= 0.999:
            return self.E
        if s == "bridge":
            img = self.bridge_render(spec["x"], k)
        else:
            img = self.src_frame(s, spec["x"], k)
        if al > 0:
            img = self.end_render(img, al, k)
        return img

    def bridge_detail(self, sigma=1.5, amax=1.5):
        """--bridge-detail: the bridge frames' fine detail back to the level of the frames on either side. Where
        A's picture dissolves into B's (two different renders of the floor, the panels' grain, the dust), their fine
        textures do not line up and average out: detail() fell from ~105 to ~86 for five frames (out 107-111), a
        focus dip right at the handover. Each bridge frame gets the unsharp mask (Gaussian sigma px, amount found by
        bisection, at most amax) that brings its detail() to the line between the frame before the bridge and the
        one after it. Returns {k: picture} for those frames (k0 - 1 .. k1 + 1) and records the amounts."""
        k0, k1 = self.k_bridge
        pics = {k: self.render(self.frames_plan[k], k) for k in range(k0 - 1, k1 + 2)}
        u8 = lambda im: np.clip(im * 255 + 0.5, 0, 255).astype(np.uint8)
        d = {k: detail(u8(im)) for k, im in pics.items()}
        lo, hi = d[k0 - 1], d[k1 + 1]
        rec = {}
        for k in range(k0, k1 + 1):
            target = lo + (hi - lo) * (k - k0 + 1) / (k1 - k0 + 2)
            if d[k] >= 0.98 * target:
                rec[k] = [0.0, round(d[k], 1), round(d[k], 1), round(target, 1)]
                continue
            im = pics[k]
            hp = im - cv2.GaussianBlur(im, (0, 0), sigma)
            a0, a1 = 0.0, amax
            for _ in range(12):
                mid = 0.5 * (a0 + a1)
                if detail(u8(im + mid * hp)) < target:
                    a0 = mid
                else:
                    a1 = mid
            amt = 0.5 * (a0 + a1)
            pics[k] = np.clip(im + amt * hp, 0, 1).astype(np.float32)
            rec[k] = [round(amt, 3), round(d[k], 1), round(detail(u8(pics[k])), 1), round(target, 1)]
        self.stats["bridge_detail"] = dict(sides=[round(lo, 1), round(hi, 1)],
                                           amount_before_after_target=rec)
        return pics

    def frames(self):
        rng = np.random.default_rng(7)
        dither = ((rng.random((H, W, 1), np.float32) - rng.random((H, W, 1), np.float32)) / 255.0)
        held = None
        ready = {}
        for k, spec in enumerate(self.frames_plan):
            if spec.get("held") and held is not None:
                yield held
                continue
            if (self.args.bridge_detail and self.k_bridge[0] is not None and k == self.k_bridge[0] - 1
                    and not ready):
                ready = self.bridge_detail()
            img = ready.pop(k) if k in ready else self.render(spec, k)
            z = self.zoom_k.get(k, 1.0)
            if z > 1.0001:
                cx, cy = (W - 1) / 2, (H - 1) / 2
                ox, oy = self.zoom_o.get(k, (0.0, 0.0))
                Mi = np.float32([[1 / z, 0, cx * (1 - 1 / z) + ox], [0, 1 / z, cy * (1 - 1 / z) + oy]])
                img = cv2.warpAffine(img, Mi, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                     borderMode=cv2.BORDER_REFLECT_101)
            if spec["src"] == "E" or spec["alpha"] >= 0.999:
                out = np.clip(img * 255 + 0.5, 0, 255).astype(np.uint8)
            else:
                out = np.clip(img * 255 + 0.5 + dither * 255 * 0.5, 0, 255).astype(np.uint8)
            if spec.get("held"):
                held = out
            yield out
            if k % 40 == 0 and len(self.flows) > 400:
                # keep the flow cache to what is still ahead (source frames only move forward)
                self.flows = {kk: v for kk, v in list(self.flows.items())[-200:]}


# ---------------------------------------------------------------- measurement

def angle(tx, ty):
    return math.degrees(math.atan2(ty, tx))


def hitch_stats(speed, floor=1.5):
    ref = median_filter(speed, size=7, mode="nearest")
    m = speed > floor
    if m.sum() < 5:
        return dict(std=None, max=None)
    r = speed[m] / np.maximum(ref[m], 1e-3) - 1
    return dict(std=round(float(np.std(r)), 3), max=round(float(np.max(np.abs(r))), 3),
                n_over_25pct=int(np.sum(np.abs(r) > 0.25)))


def track_velocity(frames):
    """Per interval, the median displacement (px at 1920) of corner features tracked to the next frame (KLT,
    kept only when tracking back lands within 0.5 px). Corners have no aperture problem, unlike dense flow on the
    stair treads, so this is the measure of the camera's direction and of its changes."""
    g = [cv2.cvtColor(f, cv2.COLOR_RGB2GRAY) for f in frames]
    V = []
    for a, b in zip(g[:-1], g[1:]):
        p = cv2.goodFeaturesToTrack(a, 800, 0.01, 12, blockSize=7)
        if p is None:
            V.append((0.0, 0.0))
            continue
        q, st, _ = cv2.calcOpticalFlowPyrLK(a, b, p, None, winSize=(31, 31), maxLevel=4)
        r, st2, _ = cv2.calcOpticalFlowPyrLK(b, a, q, None, winSize=(31, 31), maxLevel=4)
        ok = (st[:, 0] == 1) & (st2[:, 0] == 1) & (np.hypot(*(r - p)[:, 0].T) < 0.5)
        V.append(tuple(np.median((q - p)[ok, 0], 0)) if ok.sum() >= 10 else (0.0, 0.0))
    return np.array(V, np.float64)


def seam_stats(sp, V, ks, lo_clip, hi_clip):
    """Continuity around frame ks. Speed is the dense motion per frame (it includes the dolly's zoom, which the
    tracked corners' median vector does not); direction and acceleration come from the tracked corners V.
    Accelerations are compared with the clip's own (frames lo_clip..hi_clip)."""
    acc = np.hypot(*np.diff(V, axis=0).T)
    before, after = sp[max(0, ks - 14):max(1, ks - 7)].mean(), sp[ks + 7:ks + 14].mean()
    vb, va = V[max(0, ks - 14):max(1, ks - 7)].mean(0), V[ks + 7:ks + 14].mean(0)
    near = sp[max(0, ks - 6):ks + 7]
    ang = [angle(*v) for v in V[max(0, ks - 10):ks + 10]]
    mv = np.hypot(*V[max(0, ks - 10):ks + 10].T) > 1.0
    dang = [abs((b2 - a2 + 180) % 360 - 180) for a2, b2, m1, m2 in zip(ang[:-1], ang[1:], mv[:-1], mv[1:]) if m1 and m2]
    clip_acc = acc[lo_clip:hi_clip]
    win = sp[max(0, ks - 24):ks + 24]
    return dict(
        speed_before=round(float(before), 2), speed_after=round(float(after), 2),
        speed_min_over_neighbours=round(float(near.min() / max(0.5 * (before + after), 1e-3)), 2),
        speed_min_over_peak=round(float(sp[lo_clip:hi_clip][max(0, ks - 24 - lo_clip):ks + 24 - lo_clip].min()
                                        / max(sp[lo_clip:hi_clip].max(), 1e-3)), 2),
        stall_frames_under_25pct=int(np.sum(win < 0.25 * win.max())),
        accel_max=round(float(acc[max(0, ks - 10):ks + 10].max()), 2),
        accel_clip_median=round(float(np.median(clip_acc)), 2), accel_clip_p95=round(float(np.percentile(clip_acc, 95)), 2),
        dir_turn_deg=round(abs((angle(*va) - angle(*vb) + 180) % 360 - 180), 1),
        dir_step_max_deg=round(float(max(dang)) if dang else 0.0, 1))


EB_RMS_MAX = 12.0     # levels: an earbud copied rigidly from its source frame matches it to ~2-8 (h264, dither)


def earbud_residual(out_u8, src_u8, rec, centre, R=60):
    """How well the source frame's earbud (its own pixels, eroded 1 px; both pictures blurred sigma 1.2 so sub-pixel
    placement does not count) matches the output near `centre`, at the best whole-pixel offset: RMS difference in
    levels and the offset. A rigid copy scores a few levels; a bent, smeared, doubled or ghosted earbud scores tens.
    The output is padded (reflected) so an earbud at the frame's edge is still found."""
    bx = rec["box"]
    pad = 30
    x0, y0 = max(0, int(bx[0]) - pad), max(0, int(bx[1]) - pad)
    x1, y1 = min(W, int(bx[2]) + pad), min(H, int(bx[3]) + pad)
    tpl = cv2.GaussianBlur(src_u8[y0:y1, x0:x1].astype(np.float32), (0, 0), 1.2)
    m = cv2.erode(earbud_pixels(src_u8[y0:y1, x0:x1], rec, x0, y0).astype(np.uint8), _ellipse(1))
    if m.sum() < 10:
        return None, None
    P = R + max(tpl.shape) + 4
    big = cv2.copyMakeBorder(out_u8, P, P, P, P, cv2.BORDER_REFLECT_101)
    ox, oy = centre[0] - (rec["c"][0] - x0) + P, centre[1] - (rec["c"][1] - y0) + P   # tpl's corner, padded coords
    sx0, sy0 = int(max(0, ox - R)), int(max(0, oy - R))
    sx1, sy1 = int(min(big.shape[1], ox + tpl.shape[1] + R)), int(min(big.shape[0], oy + tpl.shape[0] + R))
    if sx1 - sx0 < tpl.shape[1] or sy1 - sy0 < tpl.shape[0]:
        return None, None
    search = cv2.GaussianBlur(big[sy0:sy1, sx0:sx1].astype(np.float32), (0, 0), 1.2)
    res = cv2.matchTemplate(search, tpl, cv2.TM_SQDIFF, mask=m)
    mn, _, loc, _ = cv2.minMaxLoc(res)
    return round(math.sqrt(max(mn, 0) / (3 * m.sum())), 2), (sx0 + loc[0] - P - x0, sy0 + loc[1] - P - y0)


def earbud_check(frames, aff, J):
    """Track the earbud through the output and compare it, frame by frame, with the source frame its pixels came
    from (Join.stats["earbud_source"]). A frame fails when that frame's earbud, matched into the output, differs by
    over EB_RMS_MAX (earbud_residual; not counted for an earbud partly beyond the frame's edge), when the output's
    earbud-like area is over 1.4x the source's (+30 px: a ghost or a double adds area), or when the output loses it
    while the source shows it inside the frame. Also how evenly it moves: its centre's speed and acceleration."""
    H0 = J.args.hold_first
    n = len(frames)
    cx, cy = (W - 1) / 2, (H - 1) / 2

    def source_rec(k):
        src = J.stats["earbud_source"].get(k) or (J.stats["earbud_source"].get(H0) if k < H0 else None)
        return src, ((J.A if src[0] == "A" else J.B).eb[int(src[1:])] if src else None)

    # the output's own track, from its first frame, re-seeded next to the source's earbud wherever it was lost while
    # the plan says a source frame with the earbud is shown (a take whose earbud stops looking like one loses it)
    recs = [None] * n
    k = 0
    while k < n:
        src, sr = source_rec(k)
        if recs[k] is None and (k == 0 or sr is not None):
            near = None
            if sr is not None:
                z = J.zoom_k.get(k, 1.0)
                ox, oy = J.zoom_o.get(k, (0.0, 0.0))
                near = (cx + (sr["c"][0] - cx - ox) * z, cy + (sr["c"][1] - cy - oy) * z)
            first = seed_earbud(frames[k], near)
            if first is not None:
                seg = track_earbud(frames[k:], aff[k:], n - 1 - k, first)
                got = [j for j, r in enumerate(seg) if r is not None]
                for j in got:
                    recs[k + j] = seg[j]
                k += got[-1] + 1
                continue
        k += 1
    if not any(r is not None for r in recs):
        return dict(found=False), []
    rows, fails = [], []
    for k, r in enumerate(recs):
        src, sr = source_rec(k)
        if r is None and sr is None:
            continue
        row = dict(k=k, src=src, n=r["n"] if r else 0, area=r["area"] if r else 0,
                   src_n=sr["n"] if sr else 0, src_area=sr["area"] if sr else 0,
                   c=[round(v, 1) for v in r["c"]] if r else None, size=r["size"] if r else None, rms=None)
        bad = []
        if sr is not None:
            # the source frame as it went into the join (colour corrected), its earbud matched into the output (with
            # the overscan around the bridge undone first, so both are at one scale)
            img = np.clip(J.frame(src[0], int(src[1:])) * 255 + 0.5, 0, 255).astype(np.uint8)
            centre = r["c"] if r is not None else sr["c"]
            fr, z = frames[k], J.zoom_k.get(k, 1.0)
            if z > 1.0001:
                cx, cy = (W - 1) / 2, (H - 1) / 2
                ox, oy = J.zoom_o.get(k, (0.0, 0.0))
                # out(x) at c + o + (x - c) / z: the source's x is at c + (x - c - o) z in the output
                Mf = np.float32([[z, 0, cx * (1 - z) - z * ox], [0, z, cy * (1 - z) - z * oy]])
                fr = cv2.warpAffine(fr, Mf, (W, H), flags=cv2.INTER_CUBIC | cv2.WARP_INVERSE_MAP,
                                    borderMode=cv2.BORDER_REFLECT_101)
                centre = (cx + (centre[0] - cx) / z + ox, cy + (centre[1] - cy) / z + oy)
            row["rms"], row["offset"] = earbud_residual(fr, img, sr, centre)
            row["zoom"] = round(z, 4)
            # an earbud partly beyond the frame's edge (leaving it) cannot be matched whole: noted, not failed
            ob = r["box"] if r is not None else sr["box"]
            row["at_edge"] = bool(ob[0] <= 3 or ob[1] <= 3 or ob[2] >= W - 3 or ob[3] >= H - 3)
            if row["rms"] is not None and row["rms"] > EB_RMS_MAX and not row["at_edge"]:
                bad.append("earbud differs from %s's: rms %.1f levels" % (src, row["rms"]))
        if r is not None and sr is not None:
            if r["area"] > 1.4 * sr["area"] + 30:
                bad.append("area %d > 1.4 x %d" % (r["area"], sr["area"]))
        elif sr is not None and r is None:
            # the source's earbud at the frame's edge can leave a frame early; only a loss inside the frame counts
            bx = sr["box"]
            if bx[0] > 4 and bx[1] > 4 and bx[2] < W - 4 and bx[3] < H - 4:
                bad.append("lost (source has it)")
        row["bad"] = bad
        if bad:
            fails.append(k)
        rows.append(row)
    # how evenly the earbud moves on screen: its centre's speed and acceleration (px per frame, per frame^2) over
    # the frames where the output track keeps the same blob (a big change of size means the group changed)
    cs = [(k, recs[k]["c"], recs[k]["main_area"]) for k in range(len(recs)) if recs[k] is not None]
    acc, spd = [], []
    for a, b, c in zip(cs[:-2], cs[1:-1], cs[2:]):
        if c[0] == a[0] + 2 and max(a[2], b[2], c[2]) <= 2 * min(a[2], b[2], c[2]):
            acc.append(math.hypot(c[1][0] - 2 * b[1][0] + a[1][0], c[1][1] - 2 * b[1][1] + a[1][1]))
            spd.append(math.hypot(c[1][0] - b[1][0], c[1][1] - b[1][1]))
    rms = [r["rms"] for r in rows if r.get("rms") is not None]
    summary = dict(found=True, frames_tracked=len(cs), first=cs[0][0] if cs else None, last=cs[-1][0] if cs else None,
                   failed_frames=fails, n_failed=len(fails),
                   rms_vs_source_median_p95_max=[round(float(np.median(rms)), 2), round(float(np.percentile(rms, 95)), 2),
                                                 round(float(np.max(rms)), 2)] if rms else None,
                   centre_speed_px_median_p95=[round(float(np.median(spd)), 2), round(float(np.percentile(spd, 95)), 2)]
                   if spd else None,
                   centre_accel_px_median_p95=[round(float(np.median(acc)), 2), round(float(np.percentile(acc, 95)), 2)]
                   if acc else None)
    return summary, rows


def measure(path, J, key_u8):
    """Decode the written mp4 and measure it (see step 12)."""
    frames, fps = decode(path, matrix="bt709")
    sp, _, aff = motion_series([gray_half(f) for f in frames])
    V = track_velocity(frames)
    n = len(frames)
    hold = J.args.hold_frames
    res = dict(frames=n, seconds=round(n / fps, 3),
               start_mad=round(mad_at_key(frames[0], key_u8["start"]), 2),
               end_mad=round(mad_at_key(frames[-1], key_u8["end"]), 2),
               hold_mad_max=round(max(mad_at_key(f, key_u8["end"]) for f in frames[-hold:]), 2),
               hitch=hitch_stats(sp[J.args.hold_first:J.k_morph]))
    if J.A.zoom != 1.0:   # the same at the keyframe's framing (FLUX's frame is J.A.zoom closer)
        z = J.A.zoom
        k = cv2.resize(key_u8["start"], None, fx=z, fy=z, interpolation=cv2.INTER_LANCZOS4)
        y0, x0 = (k.shape[0] - KH) // 2, (k.shape[1] - KW) // 2
        res["start_mad_at_flux_framing"] = round(mad_at_key(frames[0], k[y0:y0 + KH, x0:x0 + KW]), 2)
    ks = J.k_seam
    if ks is not None:
        res["seam"] = dict(frame=ks, time=round(ks / FPS, 2), bridge_frames=list(J.k_bridge),
                           window_frames=list(J.k_window),
                           **seam_stats(sp, V, ks, J.args.hold_first + 12, J.k_morph),
                           track_velocity=[[round(float(a), 2), round(float(b), 2)] for a, b in V[ks - 12:ks + 12]])
        # the same numbers for a straight cut at the frames that best match mid.png (A's anchor -> B's anchor),
        # each clip at its native timing (velocities per 24 fps frame)
        A, B = J.A, J.B
        a1, b0 = A.anchor[1], B.anchor[0]
        va = track_velocity(A.raw[max(0, a1 - 30):a1 + 1]) * A.fps / FPS
        vb = track_velocity(B.raw[b0:b0 + 31]) * B.fps / FPS
        vj = track_velocity(np.stack([A.raw[a1], B.raw[b0]]))
        sj, _, _ = motion_series([gray_half(A.raw[a1]), gray_half(B.raw[b0])])
        spc = np.r_[A.speed[max(0, a1 - 30):a1] * A.fps / FPS, sj, B.speed[b0:b0 + 30] * B.fps / FPS]
        ref = seam_stats(spc, np.r_[va, vj, vb], len(va), 0, len(spc))
        res["straight_cut_reference"] = dict(A_frame=int(a1), B_frame=int(b0), **{
            k: ref[k] for k in ("speed_before", "speed_after", "speed_min_over_neighbours", "stall_frames_under_25pct",
                                "accel_max", "dir_turn_deg", "dir_step_max_deg")})
    res["earbud"], eb_rows = earbud_check(frames, aff, J)
    res["bridge_uncovered_px"] = J.stats["bridge_uncovered_px"]
    res["morph_outside_px_B_E_flow"] = J.stats["morph_outside_px"]
    if "bridge_detail" in J.stats:
        res["bridge_detail"] = J.stats["bridge_detail"]
    res["speed"] = [round(float(v), 2) for v in sp]
    res["track_velocity"] = [[round(float(a), 2), round(float(b), 2)] for a, b in V]
    return res, frames, eb_rows


# ---------------------------------------------------------------- sheets

def text(img, s, org, scale=0.6, col=(255, 255, 255), th=1):
    # a dark outline drawn at the same thickness (a thicker stroke would also widen OpenCV's glyph advance)
    for dx, dy in ((-1, -1), (1, -1), (-1, 1), (1, 1), (0, 2), (2, 0)):
        cv2.putText(img, s, (org[0] + dx, org[1] + dy), cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), th, cv2.LINE_AA)
    cv2.putText(img, s, org, cv2.FONT_HERSHEY_SIMPLEX, scale, col, th, cv2.LINE_AA)


def tag_of(J, k):
    spec = J.frames_plan[k]
    tag = {"A": "A%.1f" % spec["x"], "B": "B%.1f" % spec["x"], "bridge": "br u=%.2f" % spec["x"],
           "E": "hold"}[spec["src"]]
    if spec.get("held"):
        tag = "held " + tag
    if spec["alpha"] > 0 and spec["src"] != "E":
        tag += " m%.2f" % spec["alpha"]
    return tag


def bar(Wd, s, h=30):
    b = np.full((h, Wd, 3), 24, np.uint8)
    text(b, s, (12, 21), 0.55)
    return b


def grid_rows(tiles, cols, width=None):
    """Rows of `cols` tiles (the last padded with black), each padded on the right to `width` if given."""
    while len(tiles) % cols:
        tiles.append(np.zeros_like(tiles[0]))
    rows = [np.hstack(tiles[r:r + cols]) for r in range(0, len(tiles), cols)]
    if width:
        rows = [np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 24, np.uint8)]) if r.shape[1] < width
                else r for r in rows]
    return rows


def contact_sheet(dst, name, frames, J, m, key_u8):
    TW_, TH_ = 320, 180
    cols = 8
    Wd = TW_ * cols
    rows = []
    head = np.full((96, Wd, 3), 24, np.uint8)
    eb = m.get("earbud", {})
    text(head, "%s   %.2f s  %d frames @24   start MAD %.2f   end MAD %.2f (last %d frames = dream_end.png)   "
         "A x1.0, B x%.3f   hitch scatter %.3f   earbud checks failed: %s" % (
             name, m["seconds"], m["frames"], m["start_mad"], m["end_mad"], J.args.hold_frames,
             J.info["B_speedup"], m["hitch"]["std"] or 0, eb.get("n_failed")), (12, 28), 0.62)
    sm, sc = m.get("seam", {}), m.get("straight_cut_reference", {})
    text(head, "seam @ %.2f s: speed %.1f -> %.1f px/frame, min/neighbours %.2f, min/peak %.2f, max accel (tracked "
         "corners) %.2f px/f2 (clip median %.2f, p95 %.2f), turn %.0f deg, max step %.0f deg, stall frames %d" % (
             sm.get("time", 0), sm.get("speed_before", 0), sm.get("speed_after", 0),
             sm.get("speed_min_over_neighbours", 0), sm.get("speed_min_over_peak", 0), sm.get("accel_max", 0),
             sm.get("accel_clip_median", 0), sm.get("accel_clip_p95", 0), sm.get("dir_turn_deg", 0),
             sm.get("dir_step_max_deg", 0), sm.get("stall_frames_under_25pct", 0)), (12, 56), 0.5, (200, 220, 255))
    text(head, "straight cut at the mid.png frames (A %s -> B %s), for reference: speed %.1f -> %.1f, min/neighbours "
         "%.2f, stall frames %d, max accel %.2f, turn %.0f deg, max step %.0f deg" % (
             sc.get("A_frame"), sc.get("B_frame"), sc.get("speed_before", 0), sc.get("speed_after", 0),
             sc.get("speed_min_over_neighbours", 0), sc.get("stall_frames_under_25pct", 0), sc.get("accel_max", 0),
             sc.get("dir_turn_deg", 0), sc.get("dir_step_max_deg", 0)), (12, 82), 0.5, (170, 170, 170))
    rows.append(head)
    # motion graph: dense-flow speed (blue), tracked-corner velocity x (orange) and y (green)
    gh = 240
    g = np.full((gh, Wd, 3), 16, np.uint8)
    sp = np.array(m["speed"])
    V = np.array(m["track_velocity"])
    n = len(sp) + 1
    X = lambda k: int(40 + (Wd - 60) * k / max(n - 1, 1))
    vmax = max(sp.max(), V.max()) * 1.1 + 1
    vmin = min(0.0, V.min() * 1.1)
    Y = lambda v: int(gh - 25 - (gh - 45) * (v - vmin) / (vmax - vmin))
    k0, k1 = J.k_window
    cv2.rectangle(g, (X(k0), 10), (X(k1), gh - 25), (45, 45, 70), -1)
    if J.k_bridge[0] is not None:
        cv2.rectangle(g, (X(J.k_bridge[0]), 10), (X(J.k_bridge[1]), gh - 25), (70, 50, 90), -1)
    if J.k_paint:
        cv2.rectangle(g, (X(J.k_paint[0]), 10), (X(J.k_paint[1]), gh - 25), (80, 60, 30), -1)
    cv2.rectangle(g, (X(J.k_morph), 10), (X(J.k_hold), gh - 25), (40, 70, 50), -1)
    cv2.rectangle(g, (X(J.k_hold), 10), (X(n - 1), gh - 25), (30, 90, 40), -1)
    if J.args.hold_first:
        cv2.rectangle(g, (X(0), 10), (X(J.args.hold_first), gh - 25), (60, 60, 60), -1)
    for sec in range(0, int(n / FPS) + 1):
        cv2.line(g, (X(sec * FPS), gh - 25), (X(sec * FPS), gh - 20), (160, 160, 160), 1)
        text(g, "%ds" % sec, (X(sec * FPS) - 8, gh - 5), 0.45)
    for v in range(int(math.floor(vmin / 5)) * 5, int(vmax) + 1, 5):
        cv2.line(g, (36, Y(v)), (Wd - 20, Y(v)), (60, 60, 60) if v == 0 else (36, 36, 36), 1)
        text(g, str(v), (6, Y(v) + 4), 0.4)
    for series, col in ((sp, (90, 200, 255)), (V[:, 0], (255, 170, 60)), (V[:, 1], (120, 230, 120))):
        pts = np.array([[X(k + 0.5), Y(v)] for k, v in enumerate(series)], np.int32)
        cv2.polylines(g, [pts], False, col, 2, cv2.LINE_AA)
    text(g, "px per frame at 1920: blue dense-flow speed, orange / green tracked-corner velocity x / y     "
         "[shaded: first-frame hold (grey), seam window, bridge (purple), paint-out (brown), end morph, hold]",
         (50, 26), 0.5)
    rows.append(g)
    def thumb(k, label=None):
        t = cv2.resize(frames[k], (TW_, TH_), interpolation=cv2.INTER_AREA).copy()
        text(t, label or "%d  %.2fs  %s" % (k, k / FPS, tag_of(J, k)), (6, 18), 0.45)
        return t
    ks = list(range(0, len(frames), 6))
    if ks[-1] != len(frames) - 1:
        ks.append(len(frames) - 1)
    rows += grid_rows([thumb(k) for k in ks], cols)
    rows.append(bar(Wd, "seam: consecutive frames around the handover (full-frame thumbnails)"))
    if J.k_seam is not None:
        sk = [min(max(J.k_seam - 4 + i, 0), len(frames) - 1) for i in range(8)]
        rows.append(np.hstack([thumb(k) for k in sk]))
    rows.append(bar(Wd, "first frame | round2/start.png | |diff| x4      last frame | final/dream_end.png | |diff| x4"))
    def kt(img_u8, lab):
        t = cv2.resize(img_u8, (TW_, TH_), interpolation=cv2.INTER_AREA).copy()
        text(t, lab, (6, 18), 0.45)
        return t
    def diff(a, k):
        s = cv2.resize(a, (KW, KH), interpolation=cv2.INTER_AREA).astype(np.int16)
        return np.clip(np.abs(s - k.astype(np.int16)) * 4, 0, 255).astype(np.uint8)
    rows.append(np.hstack([kt(frames[0], "first"), kt(key_u8["start"], "start.png"),
                           kt(diff(frames[0], key_u8["start"]), "MAD %.2f" % m["start_mad"]),
                           np.zeros((TH_, TW_, 3), np.uint8),
                           kt(frames[-1], "last"), kt(key_u8["end"], "dream_end.png"),
                           kt(diff(frames[-1], key_u8["end"]), "MAD %.2f" % m["end_mad"]),
                           np.zeros((TH_, TW_, 3), np.uint8)]))
    cv2.imwrite(dst, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR))


def crop_at(img, cx, cy, w, h):
    x0 = int(np.clip(round(cx - w / 2), 0, W - w))
    y0 = int(np.clip(round(cy - h / 2), 0, H - h))
    return img[y0:y0 + h, x0:x0 + w].copy()


def tumble_sheet(dst, name, frames, J, eb_rows):
    """Every frame while the earbud is in view: a 1:1 crop around it (200x140), labelled with its frame, time,
    source, component count / area (output | source frame); a red border marks a failed check."""
    rows_by_k = {r["k"]: r for r in eb_rows}
    ks = sorted(rows_by_k)
    if not ks:
        return
    cw, ch, cols = 200, 140, 12
    tiles = []
    last_c = None
    for k in range(ks[0], ks[-1] + 1):
        r = rows_by_k.get(k)
        c = r["c"] if r and r["c"] else last_c
        if c is None:
            continue
        last_c = c
        t = crop_at(frames[k], c[0], c[1] + 10, cw, ch)
        if r and r["bad"]:
            cv2.rectangle(t, (0, 0), (cw - 1, ch - 1), (255, 40, 40), 3)
        text(t, "%d %.2fs" % (k, k / FPS), (4, 14), 0.4)
        text(t, tag_of(J, k), (4, 29), 0.37, (210, 210, 255))
        if r:
            text(t, "%d/%dpx | %s %d/%dpx%s" % (r["n"], r["area"], r["src"] or "-", r["src_n"], r["src_area"],
                                               "  rms %.1f" % r["rms"] if r.get("rms") is not None else ""),
                 (4, ch - 6), 0.33, (255, 230, 150))
        tiles.append(t)
    Wd = cw * cols
    head = bar(Wd, "%s: the earbud in every frame %d-%d at 1:1 (crop 200x140 on its tracked centre); label: frame, "
               "time, plan source; output components/area | source frame components/area, rms vs that frame's earbud"
               % (name, ks[0], ks[-1]))
    cv2.imwrite(dst, cv2.cvtColor(np.vstack([head] + grid_rows(tiles, cols, Wd)), cv2.COLOR_RGB2BGR))


def edge_strips(frames, J, ks, x0, x1, y0, y1, sc, label_rows=True):
    tiles = []
    for k in ks:
        t = cv2.resize(frames[k][y0:y1, x0:x1], None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA).copy()
        if label_rows:
            text(t, str(k), (3, 14), 0.42)
        tiles.append(t)
    return tiles


def seam_sheet(dst, name, frames, J, eb_rows):
    if J.k_bridge[0] is None:
        return
    ks = list(range(max(0, J.k_bridge[0] - 8), min(len(frames), J.k_bridge[1] + 9)))
    TW_, TH_, cols = 320, 180, 8
    Wd = TW_ * cols
    rows = [bar(Wd, "%s seam: frames %d-%d (bridge %d-%d, handover ~%d); thumbnails, then the right and left 200 px "
                "at half scale, then the earbud at 1:1" % (name, ks[0], ks[-1], J.k_bridge[0], J.k_bridge[1],
                                                           J.k_seam))]
    th = []
    for k in ks:
        t = cv2.resize(frames[k], (TW_, TH_), interpolation=cv2.INTER_AREA).copy()
        text(t, "%d %.2fs %s" % (k, k / FPS, tag_of(J, k)), (5, 16), 0.42)
        unc = J.stats["bridge_uncovered_px"].get(k)
        if unc:
            text(t, "uncovered %d px" % unc, (5, TH_ - 8), 0.42, (255, 120, 120))
        th.append(t)
    rows += grid_rows(th, cols)
    for lab, x0 in (("right edge, x 1720-1920", W - 200), ("left edge, x 0-200", 0)):
        rows.append(bar(Wd, lab))
        strips = edge_strips(frames, J, ks, x0, x0 + 200, 0, H, 0.5)
        per = Wd // 100
        rows += grid_rows(strips, per, Wd)
    rb = {r["k"]: r for r in eb_rows}
    cs = [rb[k]["c"] for k in ks if k in rb and rb[k]["c"]]
    if cs:
        rows.append(bar(Wd, "the earbud at 1:1 (160x120)"))
        tiles = []
        last = cs[0]
        for k in ks:
            c = rb[k]["c"] if k in rb and rb[k]["c"] else last
            last = c
            t = crop_at(frames[k], c[0], c[1] + 8, 160, 120)
            text(t, str(k), (3, 14), 0.42)
            tiles.append(t)
        rows += grid_rows(tiles, Wd // 160, Wd)
    cv2.imwrite(dst, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR))


def end_sheet(dst, name, frames, J):
    k0 = min(J.k_paint[0] - 4 if J.k_paint else J.k_morph - 12, J.k_morph - 12)
    ks = list(range(max(0, k0), len(frames)))
    TW_, TH_, cols = 320, 180, 8
    Wd = TW_ * cols
    rows = [bar(Wd, "%s end: frames %d-%d (paint-out %s, morph from %d, hold from %d); thumbnails, the right and left "
                "200 px at half scale, the bottom 40 rows at half scale" % (
                    name, ks[0], ks[-1], "%d-%d" % J.k_paint if J.k_paint else "none", J.k_morph, J.k_hold))]
    th = []
    for k in ks:
        t = cv2.resize(frames[k], (TW_, TH_), interpolation=cv2.INTER_AREA).copy()
        text(t, "%d %.2fs %s" % (k, k / FPS, tag_of(J, k)), (5, 16), 0.42)
        th.append(t)
    rows += grid_rows(th, cols)
    for lab, x0 in (("right edge, x 1720-1920 (the paint-out)", W - 200), ("left edge, x 0-200", 0)):
        rows.append(bar(Wd, lab))
        rows += grid_rows(edge_strips(frames, J, ks, x0, x0 + 200, 0, H, 0.5), Wd // 100, Wd)
    rows.append(bar(Wd, "bottom 40 rows, full width at half scale (frame number at the left)"))
    for k in ks[-(J.k_hold - J.k_morph + 8):]:
        s = cv2.resize(frames[k][H - 40:H], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
        s = np.hstack([np.full((20, 60, 3), 24, np.uint8), s])
        text(s, str(k), (4, 15), 0.42)
        pad = np.full((20, Wd - s.shape[1], 3), 24, np.uint8)
        rows.append(np.hstack([s, pad]))
    cv2.imwrite(dst, cv2.cvtColor(np.vstack(rows), cv2.COLOR_RGB2BGR))


# ---------------------------------------------------------------- conform report

def conform_report(clips, key_u8, args):
    """Hitch scatter of each clip conformed to 24 fps three ways: frame selection (ffmpeg fps=24), ffmpeg
    minterpolate mci, and this script's content-time retime (Clip.content_time + Join.src_frame)."""
    out = {}
    for c in clips:
        r = {}
        w, h, fps = probe(c.path)
        crop = "crop=%d:%d:0:%d," % (w, round(w * 9 / 16), (h - round(w * 9 / 16)) // 2) if h != round(w * 9 / 16) else ""
        variants = {"native": ""} if abs(fps - FPS) < 0.01 else {"select (fps=24)": "fps=24,"}
        if abs(fps - FPS) > 0.01:
            variants["minterpolate mci"] = "minterpolate=fps=24:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,"
        for label, vf in variants.items():
            full = crop + vf + "scale=%d:%d:flags=area:in_color_matrix=bt601:in_range=tv:out_range=pc,format=gray" % (FW, FH)
            p = subprocess.run(["ffmpeg", "-v", "error", "-i", c.path, "-an", "-vf", full, "-f", "rawvideo", "-"],
                               capture_output=True)
            g = np.frombuffer(p.stdout, np.uint8).reshape(-1, FH, FW)
            sp, _, _ = motion_series(list(g))
            r[label] = dict(frames=len(g), **hitch_stats(sp))
        J = Join(c, c, key_u8, args)
        n_out = int(round(c.tau[c.last] / c.fps * FPS))
        grays = [gray_half(J.src_frame(c.side, c.pos_at_tau(k * c.fps / FPS))) for k in range(n_out + 1)]
        sp, _, _ = motion_series(grays)
        r["content-time retime (this script)"] = dict(frames=len(grays), **hitch_stats(sp))
        out[c.name] = r
        log("  conform %s: %s" % (c.name, json.dumps(r)))
    return out


# ---------------------------------------------------------------- main

def matte_swap(J, A, args):
    """--earbud-matte (step 4b, dream_matte.py): after the plan, clip A's frames get the earbud from the engine's
    passes in place of --earbud-grade's. The plan (the seam, the bridge, B's timing) is made exactly as before, on the
    frames as --earbud-grade left them, so nothing is re-timed; then the composite (on the frames before that grade)
    replaces them in place, the caches that hold A's pictures, plates and earbud mattes are emptied (the flows, the
    floor's motion, are kept), and each record's earbud-like area is taken from the new frame (the earbud check
    compares the output's with it)."""
    import dream_matte
    spec = args.earbud_matte.split(",")
    matte = dream_matte.Matte(spec[0], flip=args.earbud_flip or None, n=A.n)
    kw = dict(zip(("target", "gamma", "chroma"), (float(v) for v in spec[1:])))
    new = A.raw_pre_grade
    rec = dream_matte.apply_to_clip(new, list(range(A.n)), matte, A.soften["sigma"] if A.soften else None, log=log,
                                    **kw)
    A.raw[:] = new
    del A.raw_pre_grade
    _PIX.clear()
    A._masks = {}
    for key in [k for k in J.cache if k[0] == "A" or (len(k) == 3 and k[1] == "A")]:
        del J.cache[key]
    for key in [k for k in J.flows if len(k) == 3 and k[1] == "A"]:
        del J.flows[key]
    for i, r in enumerate(A.eb):
        if r is not None:
            g2 = seed_earbud(A.raw[i], r["c"])
            r["area"] = max(r.get("area_ungraded", r["area"]), int(g2["area"])) if g2 else r["area"]
    return rec


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--a", nargs="*", help="A clips: names in --takes (without .mp4) or paths; default all A_*.mp4")
    ap.add_argument("--b", nargs="*", help="B clips: names or paths; default all B_*.mp4")
    ap.add_argument("--takes", default=TAKES)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--name", help="output name for a single pair (default <A>+<B>)")
    ap.add_argument("--matrix-a", default="bt601", help="Y'CbCr matrix the A source was encoded with")
    ap.add_argument("--matrix-b", default="bt601")
    ap.add_argument("--paint", action="append", default=[],
                    help="SIDE:FIRST-LAST:REGION[:REF] paint a region (X0,Y0,X1,Y1 or polygon x,y,...) out of "
                         "a run of source frames (step 2)")
    ap.add_argument("--no-presets", action="store_true", help="skip PAINT_PRESETS (per-take paint-outs)")
    ap.add_argument("--earbud-seed", help="x,y (1920x1080) of the earbud in A's first frame, if not the largest blob")
    ap.add_argument("--a-start", type=float, default=0.0, help="seconds of A to skip at its start")
    ap.add_argument("--hold-first", type=int, default=6, help="frames the first frame is held (under DREAM_IN)")
    ap.add_argument("--seam-keep", type=float, default=0.7,
                    help="replay A's ease-out / B's ease-in below this share of the clip's peak speed")
    ap.add_argument("--a-even", action="store_true",
                    help="A's frames are evenly timed already (an engine render): no hitch retiming; at 24 fps A "
                         "then plays frame for frame, nothing interpolated")
    ap.add_argument("--a-moving", action="store_true",
                    help="A arrives at mid.png moving (no ease-out): A plays at its own speed up to the bridge and B "
                         "is joined where its ease-in reaches A's arrival speed")
    ap.add_argument("--bridge-frames", type=float, default=10, help="nominal length of the Hermite bridge")
    ap.add_argument("--dissolve", type=float, default=0.3, help="A -> B dissolve, as a share of the bridge")
    ap.add_argument("--fill-frames", type=int, default=10, help="extra footage frames on each side for edge fills")
    ap.add_argument("--overscan", type=int, default=1, help="1: push in around the bridge so no uncovered edge shows")
    ap.add_argument("--overscan-ramp", type=int, default=14, help="frames the push-in eases in and out over")
    ap.add_argument("--overscan-max", type=float, default=1.06, help="the most the push-in may zoom")
    ap.add_argument("--overscan-release", type=int, default=0,
                    help="frames the push-in is released over after the bridge (0: --overscan-ramp)")
    ap.add_argument("--bridge-fb", type=float, default=0.0,
                    help="smooth the bridge's fields where a step's forward-backward error is over this (half-res "
                         "px; 0: off)")
    ap.add_argument("--bridge-fb-region", type=float, default=0.0,
                    help="with --bridge-fb: half-res px; a passing island inside a neighbourhood (Gaussian of this "
                         "sigma) that mostly fails is failing too (0: off)")
    ap.add_argument("--bridge-fb-feather", type=float, default=3.0,
                    help="with --bridge-fb: half-res px, the failing region's soft edge (sigma)")
    ap.add_argument("--bridge-detail", action="store_true",
                    help="restore the bridge frames' fine detail (lost in the dissolve of two different pictures) "
                         "to the level of the frames on either side")
    ap.add_argument("--b-ease-out", type=float, default=0.0,
                    help="seconds: B's last stretch replayed by arc length along a smooth ease-out (0: off)")
    ap.add_argument("--push-in", default="",
                    help="Z,T0,T1,T2,T3[,X,Y]: push in to Z toward the earbud (or about the fixed point X,Y) between T0 "
                         "and T1 s, let go between T2 and T3 s")
    ap.add_argument("--morph-ease", action="store_true",
                    help="the end morph's geometry keeps the picture slowing into the hold (no speed bump)")
    ap.add_argument("--a-soften", action="store_true",
                    help="blur A's frames down to the keyframes' detail level (an engine render's CG crispness)")
    ap.add_argument("--earbud-grade", default="",
                    help="TARGET,GMAX,DESAT[,COOL]: lift the earbud's highlights to TARGET levels in the shade (e.g. "
                         "218,2.4,0.5,1); COOL takes a cool cast (bluer than its body) out; both clips")
    ap.add_argument("--earbud-matte", default="",
                    help="NAME[,TARGET,GAMMA,CHROMA]: clip A's earbud from the engine's passes tools/out/dream/engine/"
                         "NAME{,_plate,_white,_black} (dream_matte.py), graded on its true matte (e.g. clipA_mb16); "
                         "--earbud-grade is then B's only")
    ap.add_argument("--earbud-flip", default="",
                    help="NAME: the passes of flip.py's re-posed track for the frames it changes (e.g. clipA_mb16f)")
    ap.add_argument("--earbud-xfade", action="store_true",
                    help="on the bridge, cross-dissolve A's resting earbud into B's by the footage's weights")
    ap.add_argument("--earbud-floor-lock", action="store_true",
                    help="B's resting earbud follows the floor's motion (no twitch), and the bridge's follows its "
                         "path")
    ap.add_argument("--morph-frames", type=int, default=12, help="frames over which the end is pulled onto "
                                                                    "dream_end.png")
    ap.add_argument("--hold-frames", type=int, default=8, help="frames of dream_end.png at the end")
    ap.add_argument("--max-seconds", type=float, default=8.5)
    ap.add_argument("--max-b-speedup", type=float, default=1.25)
    ap.add_argument("--crf", type=int, default=12)
    ap.add_argument("--conform-report", action="store_true")
    ap.add_argument("--no-sheets", action="store_true")
    args = ap.parse_args()
    takes = os.path.abspath(args.takes)
    os.makedirs(args.out, exist_ok=True)
    names = sorted(f[:-4] for f in os.listdir(takes) if f.endswith(".mp4")) if os.path.isdir(takes) else []
    As = [resolve(x, takes) for x in (args.a or [n for n in names if n.startswith("A_")])]
    Bs = [resolve(x, takes) for x in (args.b or [n for n in names if n.startswith("B_")])]
    if not As or not Bs:
        sys.exit("need at least one A and one B clip")
    paints = [parse_paint(s) for s in args.paint]
    key_u8 = {k: load_key(k) for k in KEYS}
    seed = tuple(float(v) for v in args.earbud_seed.split(",")) if args.earbud_seed else None
    log("decoding and analysing")
    clips = {}
    for side, lst, matrix in (("A", As, args.matrix_a), ("B", Bs, args.matrix_b)):
        for n, path in lst:
            mine = [p for p in paints if p["side"] == side]
            if not mine and not args.no_presets and n in PAINT_PRESETS:
                mine = [parse_paint(x) for x in PAINT_PRESETS[n]]
                log("  %s: preset %s" % (n, PAINT_PRESETS[n]))
            c = Clip(n, path, side, matrix, mine, even=args.a_even and side == "A")
            c.soften = None
            if side == "A" and args.a_soften:
                c.soften = soften_to_keys(c.raw, key_u8, c.keys)
                log("    softened to the keyframes' detail %s: sigma max %.2f px, detail %s -> %s" % (
                    c.soften["target"], max(c.soften["sigma"]), c.soften["detail_before"][::12],
                    c.soften["detail_after"][::12]))
            c.analyse(key_u8)
            c.fit_colours(key_u8)
            clips[(side, n)] = c
            log("    zoom %.4f, last valid frame %d/%d, colour shifts at %s: %s, hitch ratio range %.2f-%.2f" % (
                c.zoom, c.last, c.n - 1, c.anchor, c.colour_shift, c.hitch_ratio.min(), c.hitch_ratio.max()))
    grade = [float(v) for v in args.earbud_grade.split(",")] if args.earbud_grade else None
    for (side, n), c in clips.items():
        if side == "A":
            c.track(seed)
            if args.earbud_matte:
                c.raw_pre_grade = c.raw.copy()    # what the matte composite starts from (after the plan)
            if grade:
                c.graded = earbud_grade(c, *grade)
                log("    earbud graded: gain %s" % {k: v[0] for k, v in list(c.graded.items())[::8]})
    report = dict(clips={}, joins={})
    if args.conform_report:
        report["conform"] = conform_report([clips[("A", n)] for n, _ in As] + [clips[("B", n)] for n, _ in Bs],
                                           key_u8, args)
    for an, _ in As:
        A = clips[("A", an)]
        ends = [r for r in A.eb[:A.last + 1] if r is not None]
        for bn, _ in Bs:
            B = clips[("B", bn)]
            B.track(ends[-1]["c"] if ends else None)   # B's earbud: next to where A's track ends
            if grade and B.graded is None:
                B.graded = earbud_grade(B, *grade)
                log("    earbud graded: gain %s" % {k: v[0] for k, v in list(B.graded.items())[::4]})
            name = args.name if args.name and len(As) * len(Bs) == 1 else "%s+%s" % (an, bn)
            t0 = time.time()
            J = Join(A, B, key_u8, args)
            J.plan()
            log("%s: plan %s" % (name, json.dumps(J.info)))
            if args.earbud_matte:
                A.graded = matte_swap(J, A, args)
            dst = os.path.join(args.out, name + ".mp4")
            encode(J.frames(), len(J.frames_plan), dst, args.crf)
            m, frames, eb_rows = measure(dst, J, key_u8)
            if not args.no_sheets:
                contact_sheet(os.path.join(args.out, name + ".png"), name, frames, J, m, key_u8)
                tumble_sheet(os.path.join(args.out, name + "_tumble.png"), name, frames, J, eb_rows)
                seam_sheet(os.path.join(args.out, name + "_seam.png"), name, frames, J, eb_rows)
                end_sheet(os.path.join(args.out, name + "_end.png"), name, frames, J)
            m["plan"] = J.info
            m["sources"] = dict(A=A.path, B=B.path)
            m["earbud_rows"] = eb_rows
            m["earbud_source"] = J.stats["earbud_source"]
            m["earbud_shift"] = J.stats.get("earbud_shift", {})
            m["earbud_xfade"] = J.stats.get("earbud_xfade", {})
            m["a_soften"] = A.soften
            m["earbud_grade"] = dict(A=A.graded, B=B.graded)
            m["earbud_floor_locked"] = dict(B=B.c_smooth)
            with open(os.path.join(args.out, name + ".json"), "w") as f:
                json.dump(m, f, indent=1)
            report["joins"][name] = {k: v for k, v in m.items()
                                     if k not in ("speed", "track_velocity", "earbud_rows", "earbud_source",
                                                  "earbud_shift", "a_soften", "earbud_grade",
                                                  "earbud_floor_locked")}
            log("  -> %s  %.2f s, start MAD %.2f, end MAD %.2f, earbud %s, seam %s (%.0f s)" % (
                dst, m["seconds"], m["start_mad"], m["end_mad"], m["earbud"],
                {k: v for k, v in m.get("seam", {}).items() if k != "track_velocity"}, time.time() - t0))
            del J, frames
    for (side, n), c in clips.items():
        report["clips"]["%s:%s" % (side, n)] = dict(
            path=c.path, fps=c.fps, src=c.src_size, zoom=round(c.zoom, 4), last_valid=c.last,
            colour_anchor_frames=c.anchor, colour_shift_rgb=c.colour_shift, paint=c.paints,
            earbud_span=getattr(c, "eb_span", None),
            speed=[round(float(v), 2) for v in c.speed], content_time=[round(float(v), 3) for v in c.tau])
    with open(os.path.join(args.out, "report.json" if len(As) * len(Bs) > 1 else
                           (args.name or "%s+%s" % (As[0][0], Bs[0][0])) + ".report.json"), "w") as f:
        json.dump(report, f, indent=1)


if __name__ == "__main__":
    main()
