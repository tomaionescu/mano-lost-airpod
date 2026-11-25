"""Every character in the game: body (MakeHuman macros), face photo, hair, clothes and colours.

Macro ranges follow MakeHuman: age 0.5 = 25 years, 0.1875 = 11 years (students around 0.39-0.43);
height 0.5 = average for the gender/age/ethnicity. `tint` multiplies an asset's base colour (linear RGB).
Clothes are MakeHuman assets fitted to the body; `photo` projects a real face onto the head (face_fit.py).
A scanned outfit's "hair": "scan" keeps the scan's sculpted hair as one shell; "scan_cards" lays strand cards over it
(hair_scan_cards.py, styled by hair_style and the outfit's "hair_cards" overrides: colours as "#rrggbb" root / tip /
under (the dark underlayer), flow, part_x, sweep...). build_human.py --hair=scan_cards tries the cards without
editing this file. "head_scan": "<id>/<file>.glb" splices a separate scan of the head in place of the scan's own
(scan_wrap.splice_head; "head_scan_fit": "affine" gives its face the template's proportions);
tools/dev/head_scan_build.py tries one without editing this file.
"""

C = "clothes/{0}/{0}.mhclo"
H = "hair/{0}/{0}.mhclo"
SKIN = "skins/{0}/{0}.mhmat"


def hx(h, k=1.0):
    """'#rrggbb' -> linear RGB tuple scaled by k (MakeHuman textures are sRGB, tints are multiplied)."""
    h = h.lstrip('#')
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    return tuple(min(1.0, (x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4) * k) for x in c)


BASE = {
    "eyes": "eyes/high-poly/high-poly.mhclo",
    "eyelashes": "eyelashes/eyelashes01/eyelashes01.mhclo",
    "teeth": "teeth/teeth_base/teeth_base.mhclo",
    "tongue": "tongue/tongue01/tongue01.mhclo",
}

CAST = {
    # ------------------------------------------------------------------ the friends
    "mano": {
        "macro": {"gender": 1.0, "age": 0.4, "muscle": 0.5, "weight": 0.54, "proportions": 0.6, "height": 0.62,
                  "race": {"asian": 0.92, "caucasian": 0.08, "african": 0.0}},
        "oval_weight": 0.65,
        "targets": {"head-round": 0.45, "head-fat-incr": 0.25, "l-cheek-volume-incr": 0.45, "r-cheek-volume-incr": 0.45,
                    "chin-height-decr": 0.35, "chin-prominent-decr": 0.3},
        "skin": SKIN.format("young_asian_male"), "photo": "mano.webp", "eye_color": "#3b2416",
        "photos": ["mano.webp", "mano/mano_02.jpg", "mano/mano_03.jpg", "mano/mano_04.jpg"],
        "skin_ref": "#d6a88e", "eye_weight": 0.0, "no_forehead": True,
        "brows": "eyebrows/eyebrow001/eyebrow001.mhclo",
        "hair_style": "fringe", "hair_colors": {"root": hx("#0b0908"), "tip": hx("#2b2019")},
        "glasses": {"asset": C.format("spamrakuen_sagerfrogs_glasses_03"), "frame": hx("#3a3c41"), "metal": 0.85},
        "outfits": {
            "street": {"clothes": [], "scan": "mano/scan.glb", "hair": "scan_cards", "face": "mano/portrait.png",
                       # Hair card overrides (hair_scan_cards.py). The fringe hangs past the shell's front edge in
                       # uneven, thinning locks (front_floor, front_free, floor_jitter, floor_wave, front_wisp,
                       # front_tip) and falls less steeply between the eyes (eye_beyond). Over the ears the strands
                       # run on past the shell's edge and lie on the outside of the ear (ear_free, ear_drape), drawn
                       # as fine wisps (ear_wisp) with a veil of fine locks along the hair's edge down to the glasses'
                       # arms (ear_veil). ear_stencil keeps the cards over the ears out of the glasses' arm pass.
                       "hair_cards": {"tip": "#1a1716", "under": "#100d0c", "front_floor": -0.016,
                                      "brow_band": [0.008, 0.016], "front_free": 0.022, "floor_jitter": 0.01,
                                      "floor_wave": 0.006, "normal_r": 0.02, "ear_free": 0.022, "ear_drape": 0.0015,
                                      "front_wisp": 0.35, "front_tip": 0.009, "eye_beyond": 0.5,
                                      "ear_wisp": {"w": 0.5, "strips": [5, 6], "step": 0.0015},
                                      "ear_stencil": True,
                                      "ear_veil": {"step": 0.001, "rows": [0.01, 0.02], "len": [0.01, 0.026],
                                                   "w": 0.45, "strips": [4, 5, 6], "tip": 0.75, "front": 0.026,
                                                   "front_top": 0.045, "front_len": [0.02, 0.034]}}},
            "street_mpfb": {"clothes": [
                (C.format("elvs_hooded_sweat_jacket1"), hx("#1d1d21")),
                (C.format("cortu_cargo_pants"), hx("#5a5c47", 1.25)),
                (C.format("punkduck_tennis_shoes"), None)]},
            "classic": {"clothes": [
                (C.format("namuhekam_male_polo_shirt"), hx("#b3262d")),
                (C.format("punkduck_male_classic_jeans"), hx("#3a3f4a")),
                (C.format("punkduck_running_shoes_01"), None)]},
            "merch": {"clothes": [
                (C.format("elvs_hooded_sweat_jacket1"), hx("#24336a", 1.15)),
                (C.format("mindfront_male_trousers_1"), hx("#9da2ab")),
                (C.format("punkduck_tennis_shoes"), None)], "logo": True},
        },
    },
    "ian": {
        "macro": {"gender": 1.0, "age": 0.47, "muscle": 0.52, "weight": 0.42, "proportions": 0.66, "height": 0.7,
                  "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}},
        "targets": {"head-fat-decr": 0.6, "head-oval": 0.5, "head-scale-vert-incr": 0.2, "head-age-incr": 0.35,
                    "l-cheek-volume-decr": 0.5, "r-cheek-volume-decr": 0.5, "l-cheek-bones-incr": 0.3, "r-cheek-bones-incr": 0.3,
                    "chin-height-incr": 0.2},
        "skin": SKIN.format("young_caucasian_male"), "photo": "f03.jpg", "eye_color": "#3a2818",
        "photos": ["f03.jpg", "ian/ian_01.jpg", "ian/ian_02.jpg", "ian/ian_04.jpg"],
        "skin_ref": "#e0b49a", "photo_ignore": ["mouth"],
        "brows": None, "hair_style": "swept", "hair_colors": {"root": hx("#24180f"), "tip": hx("#4b3424")},
        "outfits": {"default": {"clothes": [], "scan": "ian/scan.glb", "hair": "scan_cards", "face": "ian/portrait.png",
                                # Hair card overrides (hair_scan_cards.py): a curtain from a part at part_x that
                                # slides along the front edge (floor_slide, floor_arch), with the pit in the scan's
                                # top filled before the cards are laid. lip_light and under_front light the curtain's
                                # lower edge and drop the underlayer just above it. The roll_* keys handle the roll of
                                # hair over the temples: its underside is no guide (roll_under) or is tucked onto the
                                # skin (roll_tuck), the guide near it is pulled in and smoothed (roll_deflate,
                                # roll_smooth), strands reaching its cut drape on over the temple (roll_drape), cards
                                # near it keep a narrow tone range (roll_tone), the scalp under it gets fill strands
                                # (roll_fill) and no hairline cards grow along its cut (roll_bare). tone_exposed sets
                                # a floor on the tone of card rows no other card covers, ear_drape lays the hair over
                                # the ears on their outside, and ear_veil adds fine locks along the hair's edge at the
                                # ears.
                                "hair_cards": {"flow": "curtain", "split": 1.5, "crown": [0.0, 0.035, 0.012],
                                               "part_x": -0.012, "tex_w": 0.15, "curl": None, "front_floor": 0.002,
                                               "front_free": 0.035, "floor_slide": True, "floor_arch": [0.044, 0.07],
                                               "floor_jitter": 0.014, "fill_pits": 0.015, "normal_r": 0.022,
                                               "lip_light": 0.012, "under_front": 0.012, "ear_drape": 0.0015,
                                               "roll_under": 0.55, "roll_bare": True,
                                               "roll_smooth": {"iters": 30, "reach": 0.03},
                                               "roll_deflate": {"x": 0.045, "reach": 0.025, "max": 0.012},
                                               "roll_tuck": {"x": 0.045}, "tone_exposed": {"min": 0.7},
                                               "roll_drape": {"len": [0.012, 0.03], "skin": 0.35, "tone": 0.55,
                                                              "w": 0.45},
                                               "roll_tone": {"min": 0.68, "max": 0.88, "reach": 0.03},
                                               "ear_veil": {"step": 0.002, "rows": [0.008, 0.016],
                                                            "len": [0.006, 0.016], "w": 0.5, "strips": [3, 4, 5],
                                                            "tip": 0.7, "front": 0.02, "front_top": 0.05,
                                                            "front_len": [0.008, 0.02], "over": 0.03},
                                               "roll_fill": {"density": 90000, "tone": [0.45, 0.58], "under": 0.5,
                                                             "strips": [0, 1, 2]},
                                               "root": "#14110f", "tip": "#35302d", "under": "#2a221e"}},
                    "mpfb": {"clothes": [
            (C.format("mindfront_knitted_sweater_01"), hx("#8a7560")),
            (C.format("punkduck_male_classic_jeans"), hx("#2b2f38")),
            (C.format("punkduck_running_shoes_01"), None)]}},
    },
    "anisha": {
        "macro": {"gender": 0.0, "age": 0.42, "muscle": 0.45, "weight": 0.47, "proportions": 0.6, "height": 0.45,
                  "race": {"asian": 0.25, "caucasian": 0.45, "african": 0.3}},
        "skin": SKIN.format("cutoff3d_indian_female_skin"), "photo": "anisha/anisha_03.jpg", "eye_color": "#1c120b",
        "photos": ["anisha/anisha_03.jpg", "f04.png", "anisha/anisha_02.jpg", "anisha/anisha_01.jpg"],
        "skin_ref": "#b07c5c", "photo_ignore": ["mouth"],
        "brows": None, "hair_style": "long_part", "hair_colors": {"root": hx("#0b0908"), "tip": hx("#1e1612")},
        "outfits": {"default": {"clothes": [], "scan": "anisha/scan.glb", "hair": "scan_cards", "hair_long": True,
                                "face": "anisha/portrait.png",
                                # Hair card overrides (hair_scan_cards.py): long hair with front locks that hang over
                                # the shoulders (front_len, front_y). taper keeps most of a card's width to its tip.
                                # The shell's steep underside beside the neck is neither guide nor underlayer
                                # (underside, under_inner), and strands leaving the guide there fall on over the
                                # shoulder (fall_on, fall_front). window_smooth and window_dense smooth the face
                                # window's edge and keep the strands off it, hem_min drops short cards that would end
                                # at the back hem, front_lit lights strands hanging free in front of the ears, and
                                # drape_cover fills gaps between the locks beside the neck.
                                "hair_cards": {"tip": "#1c1a1a", "under": "#0e0d0d", "front_len": 0.32,
                                               "front_y": 0.025, "end_trim": 0.16, "normal_r": 0.02, "taper": 0.3,
                                               "under_inner": 0.15, "window_smooth": 0.01, "window_dense": True,
                                               "hem_min": 0.2, "fall_on": 0.3, "underside": 0.55, "fall_front": 0.035,
                                               "front_lit": 0.7,
                                               "drape_cover": {"z": [0.07, 0.26], "turn": [0.0, 0.3, -0.3], "jaw": 0.02}}},
                    "mpfb": {"clothes": [
            (C.format("janexx_old_female_sweater"), hx("#c9b79c")),
            (C.format("punkduck_female_tight_jeans"), hx("#2c3240")),
            (C.format("punkduck_comfortable_sneakers"), None)]}},
    },
    "silvia": {
        # height 0.638 gives 1.58 m in the game.
        "macro": {"gender": 0.0, "age": 0.41, "muscle": 0.45, "weight": 0.44, "proportions": 0.62, "height": 0.638,
                  "race": {"asian": 1.0, "caucasian": 0.0, "african": 0.0}},
        "skin": SKIN.format("young_asian_female"), "photo": "silvia/silvia_01.jpg", "eye_color": "#47332b",
        "photos": ["silvia/silvia_01.jpg", "silvia/silvia_02.jpg", "silvia/silvia_03.jpg", "silvia/silvia_04.jpg"],
        "skin_ref": "#ddb092",
        "brows": None, "hair_style": "layered", "hair_colors": {"root": hx("#3a2f27"), "tip": hx("#ab8674")},
        # Round frames with a plain grey finish (CharacterMaterials.FINISH 'silvia' flattens the asset's print and
        # clears its lenses). `lens` gives the lens box in inter-ocular distances from the eyeballs' centres, and
        # `seat` places the rims by rays a fixed clearance off the skin, with a smooth bump over the bridge
        # (glasses_seat.py).
        "glasses": {"asset": C.format("toigo_round_glasses_leopard"), "frame": hx("#858c86"), "metal": 0.0,
                    "clear": 0.0015, "lens": {"top": 0.18, "bottom": 0.56, "width": 0.88},
                    "seat": {"clear": 0.0015, "sigma": 0.008, "bridge": 0.02},
                    # `wire` scales the rim's width and depth and keeps the lens UVs below the texture's opaque top
                    # edge (glasses_seat.wire).
                    "wire": {"k": 1.5, "depth": 1.3, "lens_v_max": 0.9}},
        # face_finish.py options: `widen` broadens the cheeks and jaw, `brows` deepens the brows in the head texture,
        # `eye_corners` removes the eye whites painted onto the lids' corners, `teeth` scales the arch and moves it
        # back, and `molars` darkens and smooths the back teeth.
        "face_finish": {"widen": {"amount": 0.045}, "brows": {"dark": 0.35, "desat": 0.75, "fill": 0.08, "reach": 0.004},
                        "eye_corners": {"reach": 0.004}, "teeth": {"scale": 0.95, "back": 0.0005, "dilate": 12,
                                                                    "molars": {"from": 0.009, "to": 0.016, "shade": 0.24,
                                                                               "blur": 3, "tint": [1.0, 0.8, 0.72]}},
                        # `temples` and `temple_skin` repaint hair baked onto the temples as skin, and `neck_skin`
                        # reclassifies skin-coloured faces on the front of the neck that the scan wrap took for cloth.
                        "temples": {"top": 0.35, "shade": 0.96},
                        "temple_skin": {"beyond": 0.012, "z": [-0.035, 0.045], "ear": 0.004, "fade": 0.006, "blur": 24,
                                        "shade": 0.93, "warm": 0.85},
                        "neck_skin": {"z": [0.06, 0.2], "x": 0.07, "ny": -0.2, "y": 0.075},
                        # `mouth_dark` darkens the inside of the mouth with depth.
                        "mouth_dark": {"from": 0.003, "to": 0.012, "dark": 0.35},
                        # `collar_hair` repaints hair baked onto the back of the jacket in the jacket's colour.
                        "collar_hair": {"z": [0.08, 0.24], "x": 0.15, "ny": 0.3, "ref": [0.27, 0.4], "dilate": 3,
                                        "color": "#2c2c2c"}},
        "outfits": {"default": {"clothes": [], "scan": "silvia/scan.glb", "hair": "scan_cards", "hair_long": True,
                                "face": "silvia/portrait.png",
                                # Tripo multiview scan, with the hair kept down to the shoulders (hair_long) as
                                # long_part cards. Card colours are set here (root, tip, under); `cape` is off because
                                # the dark jacket would be taken for hair. window_min widens the face window, and
                                # window_hairline takes its top and sides from the portrait's hairline and face
                                # outline. tone_exposed sets a floor on the tone of cards no other card covers,
                                # cap_color and part_gap set the scalp cap's colour and the width of the open part.
                                "hair_cards": {"style": "long_part", "root": "#b08470", "tip": "#cf9f88",
                                               "under": "#8a6c5a", "window_smooth": 0.01, "window_dense": True,
                                               "hem_min": 0.2, "front_lit": 0.7, "cape": False, "window_min": 1.06,
                                               # root_tone darkens the cards near the part into regrowth: graded by
                                               # distance from the part (L, part), carried down the back of the head
                                               # from the crown (crown), with a share of cards left lighter (spare),
                                               # cards rooted on or passing near the part darkened along their length
                                               # (part_cards, pass, len, soft) and a tint for the regrowth colour.
                                               # under_roots darkens the underlayer the same way, and neck_clear
                                               # removes cards in front of the neck under the jaw.
                                               "root_tone": {"L": [0, 1], "dark": 0.22, "z": 0.04,
                                                             "part": [0.012, 0.055], "cap": 0.065, "tex_part": 0.025,
                                                             "spare": [0.4, 0.6],
                                                             "crown": {"depth": 0.12, "r": 0.025, "soft": 0.02,
                                                                       "amount": 0.85, "solid": 0.75},
                                                             "part_cards": {"r": 0.004, "side": -1, "len": 0.02,
                                                                            "soft": 0.04, "cap": 0.07, "probe": 0.04,
                                                                            "pass": 0.025},
                                                             "tint": [0.7, 1.08, 1.25]},
                                               "under_roots": {"dark": 0.3},
                                               "fly": {"bulge": [0.002, 0.005]},
                                               "neck_clear": {"z": [0.085, 0.21], "x": 0.05, "d": 0.04, "ny": -0.15},
                                               "cap_color": "#322e21", "part_gap": {"r": [0.0002, 0.0008], "open": 0.2},
                                               "tone_exposed": {"min": 0.8},
                                               "window_hairline": {"h": [-1.7, -1.47, -1.25, -1.0, -0.67, -0.44, -0.22,
                                                                         0.0, 0.2, 0.3, 0.42, 0.54, 0.7, 0.82, 0.98, 1.08],
                                                                   "w": [0.3, 0.52, 0.8, 0.98, 1.08, 1.12, 1.13, 1.14,
                                                                         1.1, 0.92, 0.8, 0.68, 0.54, 0.4, 0.24, 0.0],
                                                                   "from": -1.3, "fade": 0.4, "guide_from": 0.3,
                                                                   "guide": True}}},
                    "mpfb": {"clothes": [
            (C.format("elvs_hooded_sweat_jacket1"), hx("#18181b")),
            (C.format("toigo_wool_pants"), hx("#26262b")),
            (C.format("punkduck_tennis_shoes"), None)]}},
    },
}

CAST.update({
    # Toma
    "toma": {
        "macro": {"gender": 1.0, "age": 0.45, "muscle": 0.52, "weight": 0.46, "proportions": 0.64, "height": 0.62,
                  "race": {"asian": 0.1, "caucasian": 0.85, "african": 0.05}},
        "targets": {"head-fat-decr": 0.45, "head-oval": 0.4, "head-scale-vert-incr": 0.25, "head-age-incr": 0.3,
                    "l-cheek-volume-decr": 0.35, "r-cheek-volume-decr": 0.35, "l-cheek-bones-incr": 0.25, "r-cheek-bones-incr": 0.25,
                    "chin-height-incr": 0.25},
        "skin": SKIN.format("toigo_light_skin_male_bronze"), "photo": "toma/toma_01.jpg", "eye_color": "#1f140c",
        "photos": ["toma/toma_01.jpg", "toma/toma_02.jpg", "toma/toma_03.jpg", "toma/toma_04.jpg", "toma/toma_05.jpg"],
        "skin_ref": "#d6a184", "brows": None, "hair_style": "curly",
        "hair_colors": {"root": hx("#0e0907"), "tip": hx("#2a1c14")},
        # Scanned outfits only: `widen` with `inner` broadens the sides of the face from under the eyes to the jaw and
        # leaves its middle alone (face_finish.py).
        "face_finish": {"widen": {"amount": 0.06, "top": 0.06, "bottom": 0.8, "under": 1.5, "front": 0.07,
                                  "back": 0.105, "inner": (0.035, 0.058)}},
        "outfits": {"default": {"clothes": [
            (C.format("elvs_male_shirt_untucked_bd1"), hx("#e9e6df")),
            (C.format("punkduck_male_classic_jeans"), hx("#31394a")),
            (C.format("punkduck_tennis_shoes"), None)]},
            # Scanned outfit, see scan_wrap.py.
            "fit1": {"clothes": [], "scan": "toma/scan_fit1.glb", "hair": "scan_cards", "face": "toma/portrait.png",
                     "hair_cards": {"tip": "#241d19", "under": "#110e0d",
                                    # Hair card overrides (hair_scan_cards.py) for loose wavy locks: the "wavy2" atlas
                                    # (each card one lock, split in two with a darker trough and curled ends), wide
                                    # cards in three layers with long, calm waves, clump tone patches, few short loops
                                    # and flyaways.
                                    "atlas": "wavy2",
                                    "layers": [("under", 4200, (0.05, 0.07), (0.02, 0.028), (0.0004, 0.0014),
                                                (0.26, 0.38), (0, 1, 2), 0.25),
                                               ("mid", 4300, (0.06, 0.085), (0.017, 0.024), (0.0015, 0.004),
                                                (0.5, 0.68), (0, 1, 2, 3, 4), 0.25),
                                               ("top", 2500, (0.06, 0.085), (0.02, 0.028), (0.0032, 0.0065),
                                                (0.82, 1.0), (2, 3, 4, 5, 6), 0.3)],
                                    "curl": {"wave": (0.07, 0.09), "wiggle": 0.2, "lift": 0.004, "twist": 0.3,
                                             "jitter": 0.3},
                                    "loops": {"count_per_m2": 300, "length": (0.025, 0.04), "width": (0.009, 0.013),
                                              "bulge": (0.004, 0.008), "strips": (4, 5, 6)},
                                    "fly": {"count": 40},
                                    # `crown` lowers and smooths the guide over the crown; with `inside`, a lowered
                                    # vertex that lands inside the head counts as too close to the skin (the distance
                                    # to the skin is unsigned).
                                    "crown": {"drop": 0.016, "min": 0.005, "lift": 0.6, "smooth": 16, "inside": True},
                                    "side_trim": {"in": 0.018, "z": (0.045, 0.06, 0.09, 0.11), "right": 0.009,
                                                  "rz": (-0.01, 0.01, 0.05, 0.07), "min": 0.005},
                                    "front_lift": {"h": 0.006, "y": (0.02, 0.06), "z": (0.005, 0.03),
                                                   "rim": (0.004, 0.015)},
                                    # front_locks: loose locks from the front hairline onto the forehead (`at` is
                                    # their offset from the middle) and from its corners over the temples.
                                    "front_locks": {"at": (0.021,), "hang": (0.03, 0.04), "back": (0.012, 0.02),
                                                    "w": (0.014, 0.02), "strips": (1, 2, 3), "wave": (0.006, 0.032),
                                                    "sweep": 0.1, "clump": 2, "floor": 0.036, "tip": 0.008,
                                                    "tone": (0.72, 0.88),
                                                    "short": {"at": None, "n": 3, "half": 0.035, "hang": (0.01, 0.02),
                                                              "back": (0.015, 0.03), "w": (0.007, 0.011),
                                                              "strips": (3, 4, 5), "clump": 1, "sweep": 0.5,
                                                              "floor": 0.008, "tip": 0.02, "tone": (0.9, 1.0)},
                                                    "temples": {"at": (0.044, 0.052, 0.06), "dir": (0.2, 0.1, -1.0),
                                                                "hang": (0.025, 0.045), "back": (0.01, 0.02),
                                                                "w": (0.010, 0.016), "clump": 3, "floor": -0.002,
                                                                "sweep": 0.2, "strips": (1, 2, 3), "tip": 0.02,
                                                                "tone": (0.62, 0.78)}},
                                    "edge_free": {"len": (0.006, 0.028), "scale": 0.018, "pow": 1.5},
                                    "clump_tone": {"amp": 0.45, "scale": 0.035},
                                    # curl_tips: a few thin curled ends on the outline.
                                    "curl_tips": {"n": 30, "layers": ("top", "mid"), "at": (0.6, 0.85),
                                                  "r": (0.003, 0.005), "turn": (0.8, 1.1), "w": (0.002, 0.0035),
                                                  "strips": (5, 6), "tone": (0.85, 1.0)},
                                    # relief_tone takes each card's depth tone mostly from its depth under the hair's
                                    # smooth outer surface, so the guide's clumps are lit at their crests and dark in
                                    # the grooves between them.
                                    "relief_tone": {"depth": (0.0, 0.007), "lo": 0.2, "mix": 0.9},
                                    # lock_clump gathers the cards into locks along streamlines `sep` apart, each an S
                                    # curve with its core pushed out and its flanks pulled in; `flare` lifts the ends
                                    # of a few locks on the upper sides. `cover` sets how closely the coverage pass
                                    # fills the grooves between locks.
                                    "cover": 0.008,
                                    "lock_clump": {"sep": 0.042, "pull": 0.7, "narrow": 0.85, "bulge": 0.0015,
                                                   "bump": 0.002, "sink": 0.003, "amp": (0.004, 0.008),
                                                   "period": (0.045, 0.065), "seg": (0.05, 0.08),
                                                   "flare": {"n": 8, "h": (0.006, 0.012), "ny": 0.6, "nz": 0.8,
                                                             "z": 0.0, "gap": 0.045}}},
                     # Tripo head scan spliced in (scan_wrap.splice_head); head_scan_jaw 0.5 applies half of
                     # scan_wrap.widen_jaw's widening of the lower face.
                     "head_scan": "toma/head_scans/head_tripo.glb", "head_scan_jaw": 0.5,
                     # skull_crown holds the skull's crown this far under the scan's hair.
                     "skull_crown": {"gap": 0.013},
                     # brow_paint and beard_dark paint the brows and darken the beard in the head texture
                     # (scan_wrap.paint_brows, darken_beard). The amounts are mild: the defaults measure darker than
                     # the reference photos.
                     "brow_paint": {"thick": 1.3, "lay": 0.15, "shade": 0.04, "cover": (0.38, 0.6)},
                     "beard_dark": {"color": "#1a1411", "amount": (0.3, 0.15, 0.55), "goat_w": 0.009,
                                    "goat_back": 0.006, "strap_ear": (0.02, 0.03), "strap_up": (0.0, 0.006)},
                     # side_clear tones the stubble on the cheek in front of the ears toward the clean cheek and keeps
                     # the line along the jaw's edge (scan_wrap.clear_sides).
                     "side_clear": {"ear": (0.02, 0.03), "jaw": (0.008, 0.014), "amount": 0.85}}},
    },
    # Ishita. MPFB body with a photo-projected face. glasses_in_photo and glasses_smooth remove the frames from the
    # source photo with a median filter over a band round the eyes (an empty glasses_smooth reads as off in
    # face_texture.py). mouth_lift lightens and warms the chin and lips toward the cheek's tone, brow_deepen darkens
    # the brows before projection. The hair is MakeHuman's culturalibre_hair_01, lengthened and kept off the face and
    # over the glasses' arms (hair_stretch). The glasses are fitted to the eyes by lens_fit and drawn as thin metal
    # wire (wire, CharacterMaterials.FINISH 'ishita').
    "ishita": {
        "macro": {"gender": 0.0, "age": 0.41, "muscle": 0.45, "weight": 0.46, "proportions": 0.6, "height": 0.42,
                  "race": {"asian": 0.25, "caucasian": 0.45, "african": 0.3}},
        "targets": {"l-cheek-volume-incr": 0.5, "r-cheek-volume-incr": 0.5, "head-fat-incr": 0.4},
        "skin": SKIN.format("cutoff3d_indian_female_skin"), "photo": "ishita/ishita_01.jpg", "eye_color": "#1c120b",
        "photos": ["ishita/ishita_01.jpg", "ishita/ishita_04.jpg", "ishita/ishita_03c.jpg"],
        "glasses_in_photo": True,
        "glasses_smooth": {"rx": 1.65, "ry": 1.5, "dy": 0.22, "k": 0.034, "passes": 3, "feather": 0.02},
        "mouth_lift": {"chin": {"to": 1.8, "k": 1.0, "warm": 0.8, "depth": 0.65}, "lower": {"to": 1.0, "k": 1.0, "warm": 0.3},
                       "upper": {"to": 0.85, "k": 1.0, "warm": 0.5}},
        "brow_deepen": {"to": 0.30, "color": "#2a1c15", "k": 1.0, "grow": 0.008, "feather": 0.01, "keep": 0.5},
        "skin_ref": "#966650", "brows": "eyebrows/eyebrow004/eyebrow004.mhclo",
        "hair": H.format("culturalibre_hair_01"), "hair_tint": hx("#17110d"),
        "hair_stretch": {"from": 0.0, "k": 1.7, "clear": 0.006, "skin": 0.005,
                         "over_glasses": {"clear": 0.004, "behind": 0.015}},
        "glasses": {"asset": C.format("toigo_round_glasses_leopard"), "frame": hx("#c9ab6e"), "metal": 0.95,
                    "lens_fit": {"lens": {"top": 0.27, "bottom": 0.49, "width": 0.99},
                                 "seat": {"clear": 0.0015, "sigma": 0.008, "bridge": 0.02},
                                 "wire": {"k": 0.4, "depth": 0.75, "panto": 0.0, "lens_v_max": 0.9,
                                          "square": 1.6, "square_in": 0.5, "square_bottom": 0.0}}},
        "outfits": {"default": {"clothes": [
            (C.format("punkduck_v_neck_top"), hx("#1f2a44")),
            (C.format("punkduck_female_tight_jeans"), hx("#2c3240")),
            (C.format("punkduck_comfortable_sneakers"), None)]}},
    },
    # Cristina. MPFB body with a photo-projected face; photo_finish widens the cheeks after the fit and mouth_lift
    # lightens and warms the skin round the mouth. The braids are generated by hair_gen.py: they hang from a centre
    # part (part, lengths, gravity), stay out of a window in front of the face (face_clear), collide only with nearby
    # surfaces (collide_reach) and follow a flow chosen by the zone of their root (flow_zones). hairline_up and
    # cap_below raise the hairline and extend the cap under it, root_taper and fin_flat narrow and flatten the braids
    # where they start, and scalp_hug holds them close to the scalp on the top of the head.
    "cristina": {
        "macro": {"gender": 0.0, "age": 0.41, "muscle": 0.45, "weight": 0.5, "proportions": 0.6, "height": 0.5,
                  "race": {"asian": 0.0, "caucasian": 0.05, "african": 0.95}},
        "targets": {"l-cheek-volume-incr": 0.4, "r-cheek-volume-incr": 0.4, "head-age-decr": 0.4,
                    "mouth-trans-backward": 0.6, "mouth-scale-depth-decr": 0.4, "mouth-angles-up": 0.2,
                    "mouth-lowerlip-volume-decr": 0.4, "mouth-upperlip-volume-decr": 0.2, "chin-width-decr": 0.3},
        "skin": SKIN.format("young_african_female"), "photo": "cristina/cristina_01.jpg", "eye_color": "#150d08",
        "photos": ["cristina/cristina_01.jpg", "cristina/cristina_02.jpg", "cristina/cristina_03.jpg", "cristina/cristina_04.jpg"],
        "skin_ref": "#7a4a36", "brows": None, "hair_style": "braids",
        "mouth_lift": {"above": {"to": 0.85, "k": 1.0, "warm": 0.7}, "upper": {"to": 0.68, "k": 1.0, "warm": 0.5},
                       "chin": {"to": 1.0, "k": 1.0, "warm": 0.4, "depth": 0.5}},
        "hair_colors": {"root": hx("#4f3f2e"), "tip": hx("#8e7752")},
        "hair_gen": {"sweep_back": False, "part": True, "lengths": {"front": 0.3, "top": 0.36, "side": 0.36, "back": 0.42},
                     "gravity": 0.9, "lift": 0.012, "front_lift": 1.0, "cards": 300, "width": 0.009, "collide_reach": 0.05,
                     "floors": {"front": "free", "side": "free", "back": "free"},
                     "face_clear": {"w": 1.0, "margin": 0.006, "ahead": 0.0, "top": 0.09, "profile": True,
                                    "slide": 0.015},
                     "flow_zones": {"front": 0.6, "front_side": 0.35, "back": 2.3, "back_out": 0.15, "fall": (0.0, 0.08)},
                     "hairline_up": {"front": 0.02, "temple": 0.012}, "cap_below": 0.006,
                     "root_taper": {"len": 0.025, "w": 0.3}, "fin_flat": {"h": 0.35, "near": 0.012, "far": 0.03},
                     "scalp_hug": {"max": 0.004, "layer": 0.3, "up": (0.1, 0.4)}},
        "photo_finish": {"widen": {"amount": 0.10, "top": 0.25, "bottom": 1.0, "under": 2.0, "front": 0.07, "back": 0.14}},
        "outfits": {"default": {"clothes": [
            (C.format("janexx_old_female_sweater"), hx("#ece8e0")),
            (C.format("mindfront_female_trousers_1"), hx("#1d1d20")),
            (C.format("punkduck_comfortable_sneakers"), None)]}},
    },
    # Joaquin
    "joaquin": {
        "macro": {"gender": 1.0, "age": 0.45, "muscle": 0.48, "weight": 0.4, "proportions": 0.66, "height": 0.7,
                  "race": {"asian": 0.0, "caucasian": 1.0, "african": 0.0}},
        "targets": {"head-fat-decr": 0.6, "head-oval": 0.6, "head-scale-vert-incr": 0.3, "head-age-incr": 0.3,
                    "l-cheek-volume-decr": 0.5, "r-cheek-volume-decr": 0.5, "l-cheek-bones-incr": 0.2, "r-cheek-bones-incr": 0.2,
                    "chin-height-incr": 0.3},
        "skin": SKIN.format("young_caucasian_male"), "photo": "joaquin/joaquin_01.jpg", "eye_color": "#3a2c1e",
        "photos": ["joaquin/joaquin_01.jpg", "joaquin/joaquin_02.jpg", "joaquin/joaquin_03.jpg", "joaquin/joaquin_04.jpg"],
        "skin_ref": "#e2b59c", "photo_ignore": ["mouth"], "brows": None, "hair_style": "swept",
        "hair_colors": {"root": hx("#4a321f"), "tip": hx("#8c6a47")},
        "glasses": {"asset": C.format("spamrakuen_tbm_glasses_frames_01"), "frame": hx("#18181a"), "metal": 0.1},
        "outfits": {"default": {"clothes": [], "scan": "joaquin/scan.glb", "hair": "scan_cards", "face": "joaquin/portrait.png",
                                # Hair card overrides (hair_scan_cards.py): a side part at part_x with the top swept
                                # across (flow side_swept, sweep, lift) and a front edge the strands slide along
                                # (floor_slide, floor_arch, floor_wave, floor_wave_fine). lip_light and under_front
                                # light the hairline's edge and drop the underlayer just above it, and cap_side keeps
                                # the scalp cap's dark roots off the skin in front of the ears.
                                "hair_cards": {"flow": "side_swept", "part_x": -0.035, "sweep": 1.3, "lift": 0.12,
                                               "front_back": 0.05, "front_down": 0.25, "tex_w": 0.3,
                                               "front_floor": 0.016, "front_free": 0.016, "floor_jitter": 0.012,
                                               "floor_slide": True, "floor_arch": [0.03, 0.075], "floor_wave": 0.006,
                                               "fill_pits": 0.012, "normal_r": 0.02,
                                               "lip_light": 0.012, "under_front": 0.012, "cap_side": 0.008,
                                               "floor_wave_fine": 0.12,
                                               "root": "#130e0d", "tip": "#332c28", "under": "#14100f"}},
                    "mpfb": {"clothes": [
            (C.format("namuhekam_male_polo_shirt"), hx("#9fb4cc")),
            (C.format("mindfront_male_trousers_2"), hx("#8a7d66")),
            (C.format("punkduck_running_shoes_01"), None)]}},
    },
})


def npc(gender, age, race, skin, hair_style, hair_root, hair_tip, top, top_col, bottom, bottom_col, shoes,
        height=0.5, weight=0.5, muscle=0.5, glasses=None, brows="eyebrow001", extra=None):
    spec = {
        "macro": {"gender": gender, "age": age, "muscle": muscle, "weight": weight, "proportions": 0.55, "height": height,
                  "race": race},
        "skin": SKIN.format(skin), "brows": f"eyebrows/{brows}/{brows}.mhclo", "tier": "npc", "skin_size": 2048,
        "outfits": {"default": {"clothes": [(C.format(top), hx(top_col) if top_col else None),
                                            (C.format(bottom), hx(bottom_col) if bottom_col else None),
                                            (C.format(shoes), None)]}},
    }
    if hair_style.startswith("mh:"):
        spec["hair"] = H.format(hair_style[3:])
        spec["hair_tint"] = hx(hair_root)
    else:
        spec["hair_style"] = hair_style
        spec["hair_colors"] = {"root": hx(hair_root), "tip": hx(hair_tip)}
    if glasses:
        spec["glasses"] = {"asset": C.format(glasses[0]), "frame": hx(glasses[1]), "metal": glasses[2]}
    if extra:
        spec.update(extra)
    return spec


EU = {"asian": 0.0, "caucasian": 1.0, "african": 0.0}
MAGH = {"asian": 0.05, "caucasian": 0.7, "african": 0.25}
AF = {"asian": 0.0, "caucasian": 0.1, "african": 0.9}
AS = {"asian": 1.0, "caucasian": 0.0, "african": 0.0}
MIX = {"asian": 0.3, "caucasian": 0.5, "african": 0.2}

CAST.update({
    "prof": npc(1.0, 0.66, EU, "middleage_caucasian_male", "short", "#6d6258", "#8e857c",
                "elvs_male_shirt_untucked_bd1", "#a9bdd6", "mindfront_male_trousers_2", "#6b5a45", "shoes04",
                height=0.55, weight=0.62, glasses=("spamrakuen_tbm_glasses_frames_01", "#2a2523", 0.2)),
    "lucas": npc(1.0, 0.4, MIX, "young_caucasian_male2", "short", "#3a2a1e", "#5b4330",
                 "elvs_hooded_sweat_jacket1", "#6f7378", "elvs_jeans_straight_leg", "#3c4658", "shoes05", height=0.58),
    "yanis": npc(1.0, 0.41, MAGH, "young_caucasian_male", "short", "#0f0c0a", "#211a15",
                 "elvs_male_logo_tshirt1", "#e8e8e8", "cortu_cargo_pants", "#3e4237", "culturalibre_sneakers", height=0.55),
    "student2": npc(1.0, 0.4, EU, "young_caucasian_male", "short", "#5b4026", "#7b5a3a",
                    "toigo_basic_tucked_t-shirt", "#27ae60", "punkduck_male_classic_jeans", "#2d3340", "shoes06", height=0.5, weight=0.55),
    "ines": npc(0.0, 0.41, MAGH, "young_caucasian_female", "long_part", "#1c130e", "#3b2a1f",
                "punkduck_v_neck_top", "#e2559a", "punkduck_female_tight_jeans", "#2d3445", "punkduck_comfortable_sneakers", height=0.45),
    "acu": npc(1.0, 0.45, EU, "young_caucasian_male", "swept", "#1d150f", "#3a2a1e",
               "toigo_basic_tucked_t-shirt", "#c0392b", "punkduck_male_classic_jeans", "#2a2e38", "culturalibre_sneakers", height=0.6, muscle=0.6),
    "karim": npc(1.0, 0.43, MAGH, "young_caucasian_male", "short", "#0d0a08", "#1b1511",
                 "elvs_hooded_sweat_jacket1", "#e0aa1c", "mindfront_male_trousers_1", "#2f3036", "elvs_zombie_killer_sneakers",
                 height=0.6, weight=0.55, muscle=0.6),
    "chloe": npc(0.0, 0.41, AF, "young_african_female", "mh:afro01", "#120d0a", "#120d0a",
                 "punkduck_retro_top", "#16a085", "punkduck_female_tight_jeans", "#22262f", "punkduck_tennis_shoes", height=0.5),
    "madame": npc(0.0, 0.72, EU, "middleage_caucasian_female", "layered", "#9a8a78", "#c2b39f",
                  "mindfront_cardigan_long_open_front", "#6c5ce7", "mindfront_female_trousers_1", "#3a3a40", "toigo_ballet_flats",
                  height=0.42, weight=0.62, glasses=("spamrakuen_sagerfrogs_glasses_02", "#5a2a3a", 0.1)),
    "theo": npc(1.0, 0.4, EU, "young_caucasian_male2", "swept", "#7a5634", "#a07850",
                "mindfront_knitted_sweater_02", "#3d4b5c", "elvs_jeans_straight_leg", "#3a4255", "shoes05", height=0.52),
    "student3": npc(0.0, 0.4, AS, "young_asian_female", "layered", "#0c0a09", "#191310",
                    "elvs_hooded_sweat_jacket1", "#8e44ad", "toigo_wool_pants", "#2b2b30", "punkduck_comfortable_sneakers", height=0.4),
    "crowd1": npc(1.0, 0.42, AF, "young_african_male", "short", "#0a0807", "#0a0807",
                  "drednicolson_short-tail_camo_tee", None, "cortu_cargo_pants", "#2e3a2e", "shoes05", height=0.66),
    "crowd2": npc(0.0, 0.41, EU, "young_caucasian_female2", "long_part", "#5a3c22", "#8a6440",
                  "mindfront_knitted_sweater_02", "#b55a3c", "punkduck_female_tight_jeans", "#2c3240", "punkduck_comfortable_sneakers"),
    "crowd3": npc(1.0, 0.43, AS, "young_asian_male", "swept", "#0c0a09", "#1a1512",
                  "elvs_male_shirt_untucked_bd1", "#2a3a4f", "mindfront_male_trousers_1", "#1f2228", "shoes04", height=0.5),
    "crowd4": npc(0.0, 0.42, AF, "young_african_female", "layered", "#100b08", "#1d140f",
                  "elvs_hooded_sweat_jacket1", "#4b6584", "toigo_wool_pants", "#25262b", "punkduck_tennis_shoes", height=0.55),
    "crowd5": npc(1.0, 0.41, MAGH, "young_caucasian_male", "short", "#120d0a", "#211812",
                  "namuhekam_male_polo_shirt", "#2d6a4f", "punkduck_male_classic_jeans", "#323846", "culturalibre_sneakers"),
    "crowd6": npc(0.0, 0.4, AS, "young_asian_female", "long_part", "#0d0b0a", "#1c1714",
                  "punkduck_retro_top", "#f2e8d5", "toigo_wool_pants", "#202124", "punkduck_tennis_shoes", height=0.38),
    "crowd7": npc(1.0, 0.44, EU, "young_caucasian_male2", "swept", "#a07a4e", "#c9a46c",
                  "toigo_fisherman_sweater", "#d8cfbf", "mindfront_male_trousers_2", "#45403a", "shoes04", height=0.7),
    "crowd8": npc(0.0, 0.42, MIX, "young_caucasian_female", "layered", "#3b2416", "#6b4428",
                  "janexx_old_female_sweater", "#3c4f76", "punkduck_female_tight_jeans", "#2b2f3a", "punkduck_comfortable_sneakers", height=0.48),
})
