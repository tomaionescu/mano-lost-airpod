"""Any video ffmpeg reads -> Ogg Theora (.ogv, no audio) for Godot 4.7's VideoStreamTheora.

usage: python3.11 tools/video/to_ogv.py in.mp4 out.ogv [--quality 48] [--keyint 64] [--size 1280x720]
                                         [--keyframe-at N[,N...]] [--in-matrix bt709] [--no-check]

--keyframe-at makes those frames (0-based) keyframes besides the regular interval (theora_enc's forced keyframes):
the dream's end hold starts on one, so its picture does not change when a later regular keyframe lands in it.

An ffmpeg built without libtheora silently writes VP8 for `ffmpeg x.mp4 x.ogv`, which Godot can't play. So ffmpeg only
decodes (to YUV4MPEG2 4:2:0) and tools/video/theora_enc.c, linked against Homebrew's libtheora and libogg, encodes.
The encoder is built into tools/out/theora_enc on first use (Command Line Tools clang, called directly rather than
through the xcrun shim).

Colour: Theora players (Godot's too) decode with the BT.601 matrix, limited range, and the mp4s here are BT.709
(--in-matrix for one that is not). The picture is first scaled, if --size asks, in Y'CbCr with lanczos, then
re-matrixed by ffmpeg's `colorspace` filter (709 -> 601 matrix only: same primaries and transfer, limited range,
Floyd-Steinberg dither). swscale's own in_color_matrix/out_color_matrix re-matrix is not used: it darkens the picture
by 1.7/0.4/2.0 RGB levels at 1080p and 3.7/1.7/3.6 at 720p (a step at main.gd's dissolve into the live shot). The
colour check below measures the offset.

Checks (unless --no-check), printed and returned as JSON with --json:
  - ffprobe: one stream, codec_name theora, and the frames it decodes;
  - keyframes: every video packet's frame type (a data packet's second bit), so --keyframe-at is verified;
  - the Ogg itself: header packets, video packets, zero-length ones (a Theora "drop/duplicate" packet, which some
    decoders, ffmpeg's included, count as no frame: the last packet of a clip that ends on a still hold can be one),
    and the frame count from the last page's granule position, against the source's frame count;
  - colour: every frame's mean R, G, B decoded from the .ogv (601) against the source decoded as --in-matrix at the
    same size; the largest per-frame and the whole-clip offsets must stay under 0.5 levels (8-bit), else exit 1.
"""
import argparse, json, os, struct, subprocess, sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SRC = os.path.join(ROOT, "tools", "video", "theora_enc.c")
ENC = os.path.join(ROOT, "tools", "out", "theora_enc")
CLANG = "/Library/Developer/CommandLineTools/usr/bin/clang"
SDK = "/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk"
BREW = "/opt/homebrew"
COLOUR_TOLERANCE = 0.5      # levels of 255, per channel


def build():
    if os.path.exists(ENC) and os.path.getmtime(ENC) >= os.path.getmtime(SRC):
        return
    os.makedirs(os.path.dirname(ENC), exist_ok=True)
    libs = [os.path.join(BREW, "lib", n) for n in ("libtheoraenc.a", "libtheoradec.a", "libogg.a")]
    cmd = [CLANG, "-O2", "-Wall", "-isysroot", SDK, "-I" + os.path.join(BREW, "include"), "-o", ENC, SRC] + libs
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("building theora_enc failed:\n" + r.stderr)


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                        "stream=codec_type,codec_name,width,height,r_frame_rate,nb_read_frames:format=duration,size",
                        "-of", "json", path], capture_output=True, text=True)
    return json.loads(r.stdout or "{}")


def ffmpeg_filter(size, in_matrix):
    """The decode chain: optional lanczos scale (in Y'CbCr), then a 709 -> 601 matrix change by `colorspace`."""
    vf = []
    if size:
        vf.append("scale=%d:%d:flags=lanczos+accurate_rnd+full_chroma_int" % size)
    space = {"bt709": "bt709", "bt601": "bt470bg", "bt470bg": "bt470bg", "smpte170m": "smpte170m"}[in_matrix]
    if space != "bt470bg":
        vf.append("colorspace=ispace=%s:space=bt470bg:itrc=bt709:trc=bt709:iprimaries=bt709:primaries=bt709:"
                  "irange=tv:range=tv:format=yuv420p:dither=fsb:fast=0" % space)
    vf.append("format=yuv420p")
    return ",".join(vf)


def ogg_theora(path):
    """Parse an Ogg Theora file: header and video packet counts, zero-length video packets (their indices), the
    keyframe granule shift and the frame count from the last page's granule position."""
    data = open(path, "rb").read()
    pos, cur, packets, last_gp, first = 0, 0, [], None, 0
    while pos < len(data):
        if data[pos:pos + 4] != b"OggS":
            raise ValueError("%s: lost Ogg sync at byte %d" % (path, pos))
        gp = struct.unpack("<q", data[pos + 6:pos + 14])[0]
        nseg = data[pos + 26]
        segs = data[pos + 27:pos + 27 + nseg]
        body = pos + 27 + nseg
        off = body
        for s in segs:
            if cur == 0:
                first = off          # where the packet starts (a packet may continue over the next pages)
            cur += s
            off += s
            if s < 255:
                packets.append((first, cur))
                cur = 0
        if gp != -1:
            last_gp = gp
        pos = body + sum(segs)
    heads = packets[:3]                   # identification, comment, setup (the first is alone on page 1)
    ident = data[heads[0][0]:heads[0][0] + heads[0][1]]
    if ident[1:7] != b"theora":
        raise ValueError("%s: not a Theora stream" % path)
    vmaj, vmin, vrev = ident[7], ident[8], ident[9]
    v = struct.unpack(">H", ident[40:42])[0]
    shift = (v >> 5) & 31
    video = packets[len(heads):]
    zero = [i for i, p in enumerate(video) if p[1] == 0]
    keys = [i for i, p in enumerate(video) if p[1] > 0 and not (data[p[0]] & 0x80) and not (data[p[0]] & 0x40)]
    frames = None
    if last_gp is not None:
        frames = (last_gp >> shift) + (last_gp & ((1 << shift) - 1))
        if (vmaj, vmin, vrev) < (3, 2, 1):        # before 3.2.1 the granule position is zero-based
            frames += 1
    return dict(version="%d.%d.%d" % (vmaj, vmin, vrev), header_packets=len(heads), video_packets=len(video),
                zero_length_packets=zero, keyframes=keys, granule_shift=shift, frames_from_granulepos=frames)


def frame_means(path, size, matrix):
    """Per-frame mean R, G, B (0-255, full range) of a video decoded with `matrix`, limited range, at `size`, and
    each frame's 64x36 thumbnail (to tell a repeated frame)."""
    w, h = size
    vf = "scale=%d:%d:flags=lanczos+accurate_rnd+full_chroma_int:in_color_matrix=%s:in_range=tv:out_range=pc," \
         "format=rgb24" % (w, h, matrix)
    # passthrough: one output frame per decoded frame (by default ffmpeg would fill a skipped packet's slot itself)
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-an", "-vf", vf, "-fps_mode", "passthrough",
                          "-f", "rawvideo", "-"], stdout=subprocess.PIPE)
    out, thumbs, n = [], [], w * h * 3
    while True:
        buf = p.stdout.read(n)
        if len(buf) < n:
            break
        f = np.frombuffer(buf, np.uint8).reshape(h, w, 3)
        out.append(f.reshape(-1, 3).mean(0))
        thumbs.append(f[::h // 36, ::w // 64].astype(np.float32)[:36, :64])
    p.wait()
    return np.array(out), thumbs


def check(src, dst, size, in_matrix, n_src, want_keys=()):
    info = probe(dst)
    streams = info.get("streams", [])
    if [s.get("codec_name") for s in streams] != ["theora"]:
        sys.exit("%s: expected one theora stream, got %s" % (dst, streams))
    s = streams[0]
    og = ogg_theora(dst)
    w, h = int(s["width"]), int(s["height"])
    a, ta = frame_means(src, (w, h), in_matrix)
    # ffmpeg's decoder gives no frame for a zero-length packet; a Theora player (libtheora's TH_DUPFRAME, Godot)
    # shows the previous one again: put it back so the frames line up
    b, _ = frame_means(dst, (w, h), "bt601")
    b = list(b)
    for i in og["zero_length_packets"]:
        if i <= len(b):
            b.insert(i, b[i - 1])
    b = np.array(b)
    n = min(len(a), len(b))
    d = b[:n] - a[:n]
    # a zero-length packet must stand for a frame that repeats the one before it in the source
    dups = {i: round(float(np.abs(ta[i] - ta[i - 1]).mean()), 3) for i in og["zero_length_packets"] if 0 < i < len(ta)}
    res = dict(size=[w, h], fps=s["r_frame_rate"], seconds=round(float(info["format"]["duration"]), 3),
               mb=round(int(info["format"]["size"]) / 1e6, 2), frames_source=n_src,
               frames_ffprobe=int(s.get("nb_read_frames") or 0), ogg=og, zero_length_vs_previous_source_frame=dups,
               colour=dict(frames_compared=n, mean_offset_rgb=[round(float(v), 3) for v in d.mean(0)],
                           max_frame_offset_rgb=[round(float(v), 3) for v in np.abs(d).max(0)],
                           source_mean_rgb=[round(float(v), 2) for v in a[:n].mean(0)]))
    ok_frames = (og["frames_from_granulepos"] == n_src and og["video_packets"] == n_src
                 and len(dups) == len(og["zero_length_packets"]) and all(v < 0.5 for v in dups.values()))
    ok_colour = float(np.abs(d).max()) < COLOUR_TOLERANCE
    res["ok"] = dict(frames=ok_frames, colour=ok_colour)
    if want_keys:
        res["keyframes_wanted"] = list(want_keys)
        res["ok"]["keyframes"] = all(k in og["keyframes"] for k in want_keys)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("--quality", type=int, default=48, help="Theora quality 0..63")
    ap.add_argument("--keyint", type=int, default=64, help="frames between keyframes")
    ap.add_argument("--keyframe-at", default="", help="N[,N...]: frames (0-based) that must be keyframes too")
    ap.add_argument("--size", help="WxH: scale (lanczos) before encoding, e.g. 1280x720")
    ap.add_argument("--in-matrix", default="bt709", help="the source's Y'CbCr matrix (bt709, bt601)")
    ap.add_argument("--no-check", action="store_true")
    ap.add_argument("--json", help="also write the checks to this file")
    a = ap.parse_args()
    size = tuple(int(v) for v in a.size.lower().split("x")) if a.size else None
    build()
    vf = ffmpeg_filter(size, a.in_matrix)
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.src, "-an", "-vf", vf, "-f", "yuv4mpegpipe", "-"],
                           stdout=subprocess.PIPE)
    want = [int(v) for v in a.keyframe_at.split(",") if v.strip()]
    enc = subprocess.run([ENC, a.dst, str(a.quality), str(a.keyint)] + ([",".join(map(str, want))] if want else []),
                         stdin=dec.stdout, capture_output=True, text=True)
    dec.stdout.close()
    if dec.wait() != 0 or enc.returncode != 0:
        sys.exit("conversion failed: " + enc.stderr)
    n_enc = int(enc.stderr.split("theora_enc: ")[1].split(" frames")[0]) if "theora_enc: " in enc.stderr else None
    if a.no_check:
        info = probe(a.dst)
        s = info["streams"][0]
        print("%s: theora %sx%s, %d frames encoded, %.2f s, %.1f MB" % (a.dst, s["width"], s["height"], n_enc or -1,
              float(info["format"]["duration"]), int(info["format"]["size"]) / 1e6))
        return
    res = check(a.src, a.dst, size, a.in_matrix, n_enc, want)
    res["frames_encoded"] = n_enc
    res["filter"] = vf
    og, col = res["ogg"], res["colour"]
    print("%s: theora %dx%d %s fps, %.2f s, %.1f MB, quality %d" % (a.dst, *res["size"], res["fps"], res["seconds"],
                                                                    res["mb"], a.quality))
    print("  frames: %d encoded, %d video packets, granulepos says %s (%.3f s at %s fps); ffprobe decodes %d"
          % (n_enc, og["video_packets"], og["frames_from_granulepos"],
             og["frames_from_granulepos"] / eval(res["fps"]), res["fps"], res["frames_ffprobe"]))
    print("  keyframes at %s%s" % (og["keyframes"], "" if not want else "; wanted %s: %s" % (
        want, "yes" if res["ok"]["keyframes"] else "NO")))
    if og["zero_length_packets"]:
        print("  zero-length (duplicate-frame) packets at %s: the source frame there differs from the one before by "
              "%s levels (a still hold); ffmpeg skips them, libtheora/Godot repeat the previous frame"
              % (og["zero_length_packets"], list(res["zero_length_vs_previous_source_frame"].values())))
    print("  colour vs source (%s): mean offset R %+.3f G %+.3f B %+.3f, worst frame %.3f / %.3f / %.3f levels"
          % (a.in_matrix, *col["mean_offset_rgb"], *col["max_frame_offset_rgb"]))
    if a.json:
        with open(a.json, "w") as f:
            json.dump(res, f, indent=1)
    if not res["ok"]["frames"]:
        print("  FRAME COUNT: the .ogv does not carry the source's %d frames" % n_enc)
    if want and not res["ok"]["keyframes"]:
        print("  KEYFRAMES: %s are not all keyframes" % want)
    if not res["ok"]["colour"]:
        print("  COLOUR: a channel is off by %.3f levels (tolerance %.1f)" % (float(np.max(col["max_frame_offset_rgb"])),
                                                                          COLOUR_TOLERANCE))
    if not all(res["ok"].values()):
        sys.exit(1)


if __name__ == "__main__":
    main()
