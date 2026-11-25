# Motion capture sources

Only the takes actually used by `tools/blender/anim_clips.py` are kept here. They are retargeted onto the MPFB
`game_engine` skeleton by `tools/blender/retarget.py` (cache: `assets/anims/cache/`).

## CMU Graphics Lab Motion Capture Database

The data used in this project was obtained from mocap.cs.cmu.edu.
The database was created with funding from NSF EIA-0196217.
BVH conversion ("MotionBuilder-friendly" release) by B. Hahne / cgspeed.com, downloaded from
`https://raw.githubusercontent.com/una-dinosauria/cmu-mocap/master/data/<subject>/<take>.bvh`.
License: free for any use, including commercial products; the raw data itself may not be resold.

| File | CMU description | Used for |
|---|---|---|
| `82_08.bvh` | stand still; casual walk forward | `idle`, `idle_2`; legs of `shrug`, `talk_2` |
| `86_15.bvh` | walking, sitting, hand motions | `sit_idle`, `sit_talk`; seated legs of `typing` |
| `79_85.bvh` | typing on a laptop | upper body of `typing` |
| `143_18.bvh` | sit down and get up | `sit_down`, `stand_up` |
| `18_08.bvh` | conversation, explain with hand gestures (subject A) | `talk_idle`, `talk_1` |
| `19_08.bvh` | conversation, explain with hand gestures (subject B) | `talk_2` (upper body) |
| `141_21.bvh` | shrug | `shrug` (upper body) |
| `137_28.bvh` | normal wait | `look_around` |
| `26_09.bvh` | bend, pick up | `pickup` |
| `69_17.bvh` | turn in place | `turn_l90` |
| `69_19.bvh` | turn in place (opposite direction) | `turn_r90` |

## Bandai Namco Research Motion Dataset

"Bandai-Namco-Research-Motiondataset" (c) 2022 Bandai Namco Research Inc.,
https://github.com/BandaiNamcoResearchInc/Bandai-Namco-Research-Motiondataset,
licensed under CC BY-NC 4.0 (https://creativecommons.org/licenses/by-nc/4.0/). Non-commercial use only.
Changes: retargeted to another skeleton, trimmed, looped, resampled, played 10% faster (`run`).

| File | Content | Used for |
|---|---|---|
| `dataset-1_walk_normal_001.bvh` | walk, normal style | `walk` |
| `dataset-2_run_normal_035.bvh` | run, normal style (slow) | `jog` |
| `dataset-2_run_normal_001.bvh` | run, normal style | `run` (played at 1.1x) |
| `dataset-2_wave-right-hand_normal_001.bvh` | wave, right hand | `wave`; neutral-pose reference for the Bandai skeleton |
