# assets/video

## dream.ogv: the opening's dream (docs/DESIGN.md §7)

| | |
|---|---|
| What | 8.67 s, 1280x720, 24 fps, Ogg Theora, no audio (208 frames, 7.1 MB). Keyframes at 0, 72, 144 and 200, so the end hold starts on one |
| Played by | `scripts/main.gd` `_play_dream()`, between the chapter card and the wake-up, under the post layer, at the window's full height with the letterbox out (black at the sides of a window wider than 16:9; a narrower one crops the sides, as the 3D camera does); the bars close in again over its dissolve. It plays any length: the 0.3 s dissolve starts at `length - DREAM_OUT` (8.37 s), on the end hold |
| Made of | Out 0–105 (0–4.4 s): the engine's own render of the tumble (clip A, below), its earbud from the engine's own render passes. Out 106–114: a flow bridge from A to B. Out 115–199: Wan 3.0's drift to the notebook (clip B). Out 189–199 morph onto `dream_end.png`, out 200–207 hold on it |
| Joined by | `tools/video/join_dream.py`, converted by `tools/video/to_ogv.py` |

Clip B is AI-generated: Wan 3.0 image-to-video, run through Higgsfield. Its start and end images are engine renders
of the empty Amphi 4, and clip A is rendered by the game itself. No person appears in the clip.

### Clip A: the engine render (out 0–105)

The game renders the earbud's tumble frame by frame in Amphi 4 (`autotest=dream round2`), along a camera path from
`start.png` to `mid.png`:

1. `python3.11 tools/out/dream/engine/retime.py --cap 10.5 --ramp 1.0` writes `retime.json`: a time warp so that the
   camera's picture speed eases in over the first second and never goes over 10.5 px/frame (unwarped, it rises from
   1 to 15 px/frame in 0.6 s).
2. `python3.11 tools/out/dream/engine/tumble.py --sway=-0.00142,-0.00355,0.00181,-0.00004 --warp retime.json --sub 8 --shutter 0.5 --name clipA_mb`
   writes `clipA_mb_track.json` (108 frames, 8 steps per frame, the middle 4 kept). The earbud's motion comes from
   `sim.py`, a deterministic rigid-body simulation of the earbud (`earbud.py`) rolling off the top step and tumbling
   down the aisle steps. Its parameters come from `search.py` and `refine.py`, and it ends exactly in `mid.png`'s
   pose. The camera follows a Hermite path with its handheld sway baked in.
3. `python3.11 tools/dev/godot.py --timeout 900 -- --path . --resolution 1600x900 --fixed-fps 192 -- autotest=dream round2 clipA track=clipA_mb_track shots=../tools/out/dream/engine/keys_mb`
   (a windowed run). It plays the track step by step at 1920x1080 into `tools/out/dream/engine/clipA_mb/`.
4. `python3.11 tools/out/dream/engine/finish.py --src clipA_mb --name clipA_mb` averages each frame's 4 kept steps in
   linear light (a 180° shutter, real motion blur). It grades the ends to `start.png` and `mid.png` and encodes
   `tools/out/dream/engine/clipA_mb.mp4` (1920x1080, 24 fps, 108 frames, 4.5 s; h264 CRF 12, BT.709).

The earbud itself is composited from separate render passes, which give it a true soft matte:

5. `python3.11 tools/out/dream/engine/tumble.py --sway=-0.00142,-0.00355,0.00181,-0.00004 --warp retime.json --sub 16 --shutter 0.5 --name clipA_mb16`
   writes `clipA_mb16_track.json`: the same camera path and tumble, 16 steps per frame. The track used for the
   clip saves all 16 steps (its `save` list is 0–15; `--shutter 0.5` alone saves the middle 8).
6. `python3.11 tools/out/dream/engine/flip.py` (defaults `--src clipA_mb16 --name clipA_mb16f --from 63.25 --to 69.0 --turns -1`)
   writes `clipA_mb16f_track.json`. It changes only the earbud's fall off the second nosing (out 66–72): the earbud
   turns about its line of sight, so the stem turns one way on screen, a cartwheel, and lands in the same pose.
   Every centre of mass stays where it was, and nothing goes into the steps.
7. Seven windowed runs, one per pass, about 4 minutes each:
   `python3.11 tools/dev/godot.py --timeout 900 -- --path . --resolution 1600x900 --fixed-fps 384 -- autotest=dream round2 clipA track=clipA_mb16_track passes=<pass> crop=576x512 shots=../tools/out/dream/engine/<keys dir>`
   (the `clipA_mb16f` runs use `track=clipA_mb16f_track`).
   - The passes are `normal`, `plate`, `white` and `black` for `clipA_mb16`, and `normal`, `white` and `black`
     for `clipA_mb16f`, whose plate is `clipA_mb16`'s.
   - `plate` renders without the earbud. `white` and `black` render the earbud unshaded white (0.8) and black, with
     the fogs, glow, SSR, SSIL, auto exposure and dust off.
   - Each step is a 576x512 crop around the earbud, saved to `tools/out/dream/engine/<track>_<pass>/`. The
     `normal` pass goes to `<track>/`.
8. `tools/video/dream_matte.py` (called by `join_dream.py --earbud-matte`) turns the passes into the earbud layer:
   - Each frame averages its middle 12 of the 16 steps in linear light under a tent. That is a soft-edged shutter
     about as wide as the 180° one, with no stepped copies on the spinning stem.
   - alpha = (white − black) / white level is the earbud's soft matte: its motion blur and the carpet fibres in
     front of it are included.
   - E = (normal − (1 − alpha) · plate) / alpha is its own colour, separated from the floor.
   - Its highlight is held on a smooth target (about 216 levels in the shade), and its chroma eases to its own
     sunlit cream over out 23–34.
   - The result is composited onto the normal pass, so the rendered shadow stays. Only the earbud's own region of
     the frame changes. The matte cache is `tools/out/dream/engine/clipA_mb16_matte/`.

The rendered passes are not in the repository (about 4.9 GB, plus a 0.6 GB matte cache); steps 5 to 7 produce them
again. The autotest's `passes=` and `crop=` options are in `scripts/dev/autotest.gd` (`_dream3_clip_a`).

### Clip B: Wan 3.0 (from out 106)

| | |
|---|---|
| Model | Wan 3.0 (`wan3_0`) image-to-video, through Higgsfield |
| Settings | `resolution 1080p`, `duration 4`, `aspect_ratio 16:9`, `generate_audio false`. The mp4 is 1920x1080, 30 fps, 120 frames |
| `start_image` | `shots/dream/round2/mid.png` (1792x1008). Seated eye level in the aisle, the earbud at rest on a lower step, the notebook's desk row ahead-right |
| `end_image` | `shots/dream/final/dream_end.png` (1792x1008). The wake-up's first shot (`main.wake_shots()`): the desk across the aisle from Mano, his algo notebook and pen, as soft as the wake-up opens on it (`set_wake_blur(0.55)`), Mano out of frame |
| Prompt | In short: the same slow dream camera keeps gliding forward and right along the aisle, sinking to the desk tops, and turns toward the notebook as the picture softens. The earbud stays where it lies and slips out at the bottom left. No people, no new text, no cuts, plus an avoid list (morphing, melting, duplicates, wipes, garbled letters) |

**Keyframes**: all are engine renders by `autotest=dream`, with nobody in the room and no lens finish or letterbox:
`shots/dream/round2/start.png`, `mid.png` and `final/dream_end.png`, the shot the live game cuts to. Clip A renders
`start.png`'s and `mid.png`'s views itself, so its first and last frames match them.

### Join and post (`tools/video/join_dream.py`)

```
python3.11 tools/video/join_dream.py --a tools/out/dream/engine/clipA_mb.mp4 --matrix-a bt709 --a-even --a-moving \
    --b B_wan3 --out tools/out/dream/joined6_r1 --hold-first 3 --max-seconds 9.0 --a-soften \
    --earbud-grade 218,2.4,0.5,1 --earbud-matte clipA_mb16 --earbud-flip clipA_mb16f --earbud-xfade \
    --earbud-floor-lock --bridge-fb 1.0 --bridge-fb-region 20 --bridge-fb-feather 8 --bridge-detail \
    --overscan-release 30 --morph-ease --b-ease-out 1.5
```

It takes about 100 s once the matte cache is there.

- A plays frame for frame after a 3-frame hold. B plays at x0.995, conformed from 30 to 24 fps.
- `--a-soften`: a Gaussian blur of up to 0.62 px brings the render's crispness down to the keyframes' detail.
- `--earbud-matte clipA_mb16`: clip A's earbud comes from the render passes above (`dream_matte.py`). No
  brightness key and no inpainted floor are used. Its highlight seen in the .ogv holds 211–227 levels over out
  28–70, with steps of 6 levels or less frame to frame.
- `--earbud-flip clipA_mb16f`: out 66–72 take the cartwheel's passes.
- `--earbud-grade` grades B's earbud.
- The seam is at 4.58 s (out 110). It is a flow bridge over out 106–114. Where the flow fails its forward-backward
  check, it falls back to a plain cross-dissolve, so the left seat panels do not tear.
- `--earbud-xfade`: on the bridge, A's resting earbud and B's are each pasted on its path and cross-dissolved by
  the footage's own weights (0.04 / 0.45 / 0.91 at out 109 / 110 / 111) instead of switching in one frame.
- `--earbud-floor-lock`: B's resting earbud follows a smooth floor path, about 1 px RMS.
- B_wan3's paint-out preset carries the blurred near panel out of the right edge in one motion (out 158–175).
- B's last 1.5 s ease out to rest.
- The morph lands on `dream_end.png` (MAD 0.61), then holds for 8 frames.
- The earbud check tracks 130 frames and none fails.

Contact sheets and the JSON report are written next to the mp4.

### Conversion

`python3.11 tools/video/to_ogv.py tools/out/dream/joined6_r1/clipA_mb+B_wan3.mp4 assets/video/dream.ogv --quality 56 --size 1280x720 --keyint 72 --keyframe-at 200`

- ffmpeg scales with lanczos and re-matrixes BT.709 to BT.601, and `tools/video/theora_enc.c` encodes, linked
  against Homebrew's libtheora and libogg (an ffmpeg without a Theora encoder would write VP8).
- The keyframe interval is 72 rather than 64, so that no regular keyframe lands at out 192, inside the end morph,
  where it would make a one-frame detail pulse. Out 200, the first hold frame, is forced to a keyframe.
- Colour against the mp4: +0.13/-0.02/+0.00 levels, worst frame 0.40.
- The granule position counts 208 frames, keyframes at 0, 72, 144 and 200. ffprobe decodes 207: the last packet
  (207) is a zero-length repeat inside the still hold.
- To check it in the game, run windowed:
  `python3.11 tools/dev/godot.py --timeout 400 -- --path . --resolution 1600x900 -- autotest=opening shots=dream_final3 dream_at=1.5,1.75,2.8,4.6`.
  `get_stream_length()` reads 8.67 s, and the frames Godot decodes match the .ogv decoded by ffmpeg (MAD 0.33–0.39,
  mean colour within 0.6 levels).

### Frame by frame

- **0–0.12 s (out 0–2):** `start.png`'s view held, under the 0.4 s DREAM_IN and the chapter card turning away.
- **0.12–1.0 s:** the camera eases into its glide from rest (0 to 10.3 px/frame). The earbud lies white on the
  landing's edge in the sunbeam, then tips over the nosing at about 1.0–1.25 s.
- **1.0–3.4 s:** a steady glide down the aisle at about 10.5 px/frame, motion-blurred. The earbud tumbles down the
  treads in two or three low bounces on each. It stays the same cream-white in the shade on every frame, with a soft
  motion blur on the spinning stem. At 2.75–3.0 s (out 66–72) it cartwheels off the second nosing, the stem turning
  one way about 50° a frame, and lands in the same pose.
- **3.4–4.4 s:** the camera slows to 7–7.5 px/frame and rises to seated eye level. The earbud comes to rest on a
  lower step.
- **4.42–4.75 s (out 106–114):** the bridge into Wan's picture. It is slightly softer, with fewer, larger dust motes.
  The seat panels and treads stay intact, and the earbud is handed over on its floor path, cross-faded over out
  109–111.
- **4.75–6.4 s:** B glides right and up toward the notebook, peaking at about 14.5 px/frame at 6.0 s. The earbud
  slips out of the bottom of the frame at about 5.4 s (out 129).
- **6.6–7.3 s:** the blurred near panel slides out at the right edge.
- **7.25–8.29 s:** the camera eases to a stop on the notebook as the picture morphs onto `dream_end.png`.
- **8.33–8.67 s:** held on `dream_end.png`. The game dissolves into the same shot rendered live.

No people and no new text. The slide's and notebook's writing stays as rendered.
