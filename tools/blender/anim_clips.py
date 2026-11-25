"""Clip table and source-skeleton definitions for the mocap retargeter (see retarget.py).

Times are in seconds of the source take. Sources live in assets/anims/src/ (see CREDITS.md there).
Clip kinds:
  loco    in-place locomotion loop: `cycles` gait cycles (left heel strike to left heel strike) picked inside `range`
  loop    seamless loop of `length` (min, max) seconds picked inside `range` (smallest pose discontinuity)
  oneshot played once, exactly `range`
Options: mirror (swap left/right), rate (playback speed factor), fingers (0 open .. 1 curled),
seat (sitting clip: pelvis put on a 0.45 m seat whose front edge is the root), smooth (filter sigma, frames @30fps),
upper (take the upper body from another source: (take, start)), face ('start', 'mean' or 'end' facing reference),
hands ('desk' = wrists IK'd onto a desk/keyboard), turn (degrees the clip turns, carried by the Root bone).
"""

# canonical segments = target bone names. Fingers are procedural.
SEGMENTS = ["pelvis", "spine_01", "spine_02", "spine_03", "neck_01", "head",
            "clavicle_l", "upperarm_l", "lowerarm_l", "hand_l",
            "clavicle_r", "upperarm_r", "lowerarm_r", "hand_r",
            "thigh_l", "calf_l", "foot_l", "ball_l",
            "thigh_r", "calf_r", "foot_r", "ball_r"]

POINTS = ["hips", "hip_l", "hip_r", "ankle_l", "ankle_r", "toe_l", "toe_r", "wrist_l", "wrist_r",
          "shoulder_l", "shoulder_r", "elbow_l", "elbow_r", "head"]

# canonical (T-pose) bone directions in Blender axes: character faces -Y, +X is its left, +Z up
LIMB_DIRS = {"upperarm_l": (1, 0, 0), "lowerarm_l": (1, 0, 0), "hand_l": (1, 0, 0),
             "upperarm_r": (-1, 0, 0), "lowerarm_r": (-1, 0, 0), "hand_r": (-1, 0, 0),
             "thigh_l": (0, 0, -1), "calf_l": (0, 0, -1), "thigh_r": (0, 0, -1), "calf_r": (0, 0, -1)}

SKELETONS = {
    # CMU via cgspeed's MotionBuilder-friendly BVH: 120 fps, frame 0 is a T-pose (palms down, legs straight)
    "cmu": {
        "detect": "LeftUpLeg",
        "calib": "tpose",
        "segments": {
            "pelvis": [("Hips", 1.0)], "spine_01": [("LowerBack", 1.0)], "spine_02": [("Spine", 1.0)],
            "spine_03": [("Spine1", 1.0)], "neck_01": [("Neck", 0.5), ("Neck1", 0.5)], "head": [("Head", 1.0)],
            "clavicle_l": [("LeftShoulder", 1.0)], "upperarm_l": [("LeftArm", 1.0)],
            "lowerarm_l": [("LeftForeArm", 1.0)], "hand_l": [("LeftHand", 1.0)],
            "clavicle_r": [("RightShoulder", 1.0)], "upperarm_r": [("RightArm", 1.0)],
            "lowerarm_r": [("RightForeArm", 1.0)], "hand_r": [("RightHand", 1.0)],
            "thigh_l": [("LeftUpLeg", 1.0)], "calf_l": [("LeftLeg", 1.0)], "foot_l": [("LeftFoot", 1.0)],
            "ball_l": [("LeftToeBase", 1.0)],
            "thigh_r": [("RightUpLeg", 1.0)], "calf_r": [("RightLeg", 1.0)], "foot_r": [("RightFoot", 1.0)],
            "ball_r": [("RightToeBase", 1.0)],
        },
        # joint whose position gives the bone direction (child) for limb segments
        "children": {"LeftArm": "LeftForeArm", "LeftForeArm": "LeftHand", "LeftHand": "LeftHandIndex1",
                     "RightArm": "RightForeArm", "RightForeArm": "RightHand", "RightHand": "RightHandIndex1",
                     "LeftUpLeg": "LeftLeg", "LeftLeg": "LeftFoot", "RightUpLeg": "RightLeg", "RightLeg": "RightFoot"},
        "points": {"hip_l": "LeftUpLeg", "hip_r": "RightUpLeg", "ankle_l": "LeftFoot", "ankle_r": "RightFoot",
                   "toe_l": "LeftToeBase", "toe_r": "RightToeBase", "wrist_l": "LeftHand", "wrist_r": "RightHand",
                   "shoulder_l": "LeftArm", "shoulder_r": "RightArm", "elbow_l": "LeftForeArm",
                   "elbow_r": "RightForeArm", "head": "Head"},
        "leg": ("LeftUpLeg", "LeftLeg", "LeftFoot"),
    },
    # Bandai Namco Research Motion Dataset: 30 fps, no usable rest pose (every bone lies on its local X).
    # Limb frames come from the axis convention (X along the bone, Y = knee/elbow flexion axis),
    # the rest (spine, neck, head, clavicles, feet, toes) from neutral standing frames of `ref`.
    "bandai": {
        "detect": "UpperLeg_L",
        "calib": "axes",
        "ref": [("dataset-2_wave-right-hand_normal_001", 0.0, 0.4)],
        # local X, Y axis directions in the canonical T-pose, BVH axes (+X left, +Y up, +Z forward)
        "axes": {
            "UpperArm_L": ((1, 0, 0), (0, 1, 0)), "LowerArm_L": ((1, 0, 0), (0, 1, 0)), "Hand_L": ((1, 0, 0), (0, 1, 0)),
            "UpperArm_R": ((1, 0, 0), (0, -1, 0)), "LowerArm_R": ((1, 0, 0), (0, -1, 0)), "Hand_R": ((1, 0, 0), (0, -1, 0)),
            "UpperLeg_L": ((0, -1, 0), (1, 0, 0)), "LowerLeg_L": ((0, -1, 0), (1, 0, 0)),
            "UpperLeg_R": ((0, 1, 0), (1, 0, 0)), "LowerLeg_R": ((0, 1, 0), (1, 0, 0)),
        },
        "segments": {
            "pelvis": [("Hips", 1.0)], "spine_01": [("Hips", 0.5), ("Spine", 0.5)], "spine_02": [("Spine", 1.0)],
            "spine_03": [("Chest", 1.0)], "neck_01": [("Neck", 1.0)], "head": [("Head", 1.0)],
            "clavicle_l": [("Shoulder_L", 1.0)], "upperarm_l": [("UpperArm_L", 1.0)],
            "lowerarm_l": [("LowerArm_L", 1.0)], "hand_l": [("Hand_L", 1.0)],
            "clavicle_r": [("Shoulder_R", 1.0)], "upperarm_r": [("UpperArm_R", 1.0)],
            "lowerarm_r": [("LowerArm_R", 1.0)], "hand_r": [("Hand_R", 1.0)],
            "thigh_l": [("UpperLeg_L", 1.0)], "calf_l": [("LowerLeg_L", 1.0)], "foot_l": [("Foot_L", 1.0)],
            "ball_l": [("Toes_L", 1.0)],
            "thigh_r": [("UpperLeg_R", 1.0)], "calf_r": [("LowerLeg_R", 1.0)], "foot_r": [("Foot_R", 1.0)],
            "ball_r": [("Toes_R", 1.0)],
        },
        "children": {},
        "points": {"hip_l": "UpperLeg_L", "hip_r": "UpperLeg_R", "ankle_l": "Foot_L", "ankle_r": "Foot_R",
                   "toe_l": "Toes_L", "toe_r": "Toes_R", "wrist_l": "Hand_L", "wrist_r": "Hand_R",
                   "shoulder_l": "UpperArm_L", "shoulder_r": "UpperArm_R", "elbow_l": "LowerArm_L",
                   "elbow_r": "LowerArm_R", "head": "Head"},
        "leg": ("UpperLeg_L", "LowerLeg_L", "Foot_L"),
    },
}

CLIPS = {
    # ---------------------------------------------------------------- standing idles
    "idle": dict(src="82_08", kind="loop", range=(1.0, 8.6), length=(6.0, 7.5), head_damp=0.3, fingers=0.55,
                 straighten=0.999),
    "idle_2": dict(src="82_08", kind="loop", range=(1.0, 8.6), length=(6.0, 7.5), fingers=0.55, straighten=0.999),
    # ---------------------------------------------------------------- locomotion (in place)
    "walk": dict(src="dataset-1_walk_normal_001", kind="loco", range=(0.8, 6.3), cycles=2, fingers=0.5),
    "jog": dict(src="dataset-2_run_normal_035", kind="loco", range=(0.5, 2.7), cycles=2, fingers=0.65, smooth=0.5),
    "run": dict(src="dataset-2_run_normal_001", kind="loco", range=(0.1, 2.25), cycles=2, rate=1.1, fingers=0.7,
                smooth=0.5),
    # ---------------------------------------------------------------- seated
    "sit_idle": dict(src="86_15", kind="loop", range=(17.8, 23.6), length=(4.5, 5.8), seat=True, fingers=0.5,
                     foot_ref=(0.5, 10.0)),
    "sit_talk": dict(src="86_15", kind="loop", range=(23.5, 37.0), length=(8.0, 12.0), seat=True, fingers=0.4,
                     foot_ref=(0.5, 10.0)),
    "typing": dict(src="86_15", kind="loop", range=(17.8, 23.6), length=(4.5, 5.8), seat=True, fingers=0.35,
                   upper=("79_85", 1.0), hands="desk", head=-14, foot_ref=(0.5, 10.0)),
    "sit_down": dict(src="143_18", kind="oneshot", range=(0.2, 2.3), seat="down", fingers=0.5),
    "stand_up": dict(src="143_18", kind="oneshot", range=(4.2, 5.45), seat="up", fingers=0.5, head_ref="end"),
    # ---------------------------------------------------------------- conversation
    "talk_idle": dict(src="18_08", kind="loop", range=(11.0, 17.3), length=(5.0, 6.2), fingers=0.35, straighten=0.999),
    "talk_1": dict(src="18_08", kind="oneshot", range=(9.6, 13.9), fingers=0.3, straighten=0.999),
    "talk_2": dict(src="19_08", kind="oneshot", range=(0.3, 3.6), fingers=0.3, legs=("82_08", 2.0), straighten=0.999),
    "shrug": dict(src="141_21", kind="oneshot", range=(0.45, 2.25), fingers=0.25, legs=("82_08", 1.5), straighten=0.999),
    "wave": dict(src="dataset-2_wave-right-hand_normal_001", kind="oneshot", range=(0.0, 2.4), straighten=0.999,
                 splice=[(5.0, 6.2)], fingers=0.1),
    # ---------------------------------------------------------------- misc one-shots
    "look_around": dict(src="137_28", kind="oneshot", range=(18.0, 23.5), fingers=0.55, straighten=0.999),
    "pickup": dict(src="26_09", kind="oneshot", range=(0.4, 4.3), fingers=0.4, head_ref="end"),
    "turn_l90": dict(src="69_17", kind="oneshot", range=(0.6, 2.55), turn=90, fingers=0.55, straighten=0.999),
    "turn_r90": dict(src="69_19", kind="oneshot", range=(0.6, 3.0), turn=-90, fingers=0.55, straighten=0.999),
}


def skeleton_of(bvh):
    for k, s in SKELETONS.items():
        if s["detect"] in bvh.names:
            return k
    raise ValueError("unknown skeleton: " + ", ".join(bvh.names[:6]))
