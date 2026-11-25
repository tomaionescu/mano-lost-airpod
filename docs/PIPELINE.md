# Asset pipeline

How the characters, the campus, the audio and the opening video are built, and how Godot picks the results up. The
build scripts live in `tools/`. Everything they produce is committed under `assets/`, so the game runs without running
any of them.

Related documents: [ARCHITECTURE.md](ARCHITECTURE.md) for the game code, [DESIGN.md](DESIGN.md) for the game design,
[ART_DIRECTION.md](ART_DIRECTION.md) for the look, [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md) for how the real campus was
measured, [STATUS.md](STATUS.md) for known issues.

## What can be rebuilt from the repository

| Asset | Output | Rebuilds from the repository |
|---|---|---|
| Campus level and props | `assets/levels/campus.glb`, `assets/props/*.glb` | Yes. The texture sets are already in `assets/textures/`; a missing one is downloaded. |
| Campus map plan | `assets/levels/campus_plan.json` | Yes. |
| Lens, grain and notebook textures | `assets/textures/fx/`, `assets/textures/notebook_algo/` | Yes. |
| Background characters (19) | `assets/characters/<id>.glb` | Yes, with MPFB and the MakeHuman packs installed. |
| The eight main characters | `assets/characters/<id>[_<outfit>].glb` | No. The photos and scans are not in the repository. |
| Animation clips | embedded in every character GLB | Yes. The motion capture takes are in `assets/anims/src/`. |
| Music, ambience, effects, footsteps | `assets/audio/` | No, except three synthesised effects (`tools/py/sfx_synth.py`). The source recordings are not in the repository. |
| NPC voice lines | `assets/audio/voice/` | No. The raw takes are not in the repository. |
| Opening video | `assets/video/dream.ogv` | No. The motion scripts are in `tools/out/dream/engine/`, but the rendered passes are not in the repository. |

The source photos of the friends and the 3D scans made from them (`tools/photos/`, `tools/scans/`) are kept out of the
repository, together with the audio sources (`tools/audio_src/`) and nearly all intermediate files (`tools/out/`). The
character scripts read the photos and scans, so the eight main characters cannot be rebuilt from a clone. The scripts
are published as they are, to show how the shipped models were made.

## Prerequisites

The tools were written on macOS, and several paths are fixed in the scripts.

| Tool | Version | Where the scripts expect it |
|---|---|---|
| Godot | 4.7.2, Forward+ renderer | `~/Applications/godot/Godot.app` (`Play Mano.command`, `tools/dev/godot.py`) |
| Blender | 4.5.4 LTS | `/Applications/Blender.app` |
| MPFB (MakeHuman for Blender) | 2.0.18 | a Blender extension, imported as `bl_ext.user_default.mpfb` |
| Python | 3.11 | `/Library/Frameworks/Python.framework/Versions/3.11/bin/python3.11` (called by `face_fit.py`, `face_calib.py`, `scan_wrap.py`) |
| ffmpeg, ffprobe, sox | recent builds | on `PATH`; sox needs libvorbis |
| libtheora, libogg, clang | Homebrew libraries in `/opt/homebrew`, Command Line Tools clang | used only by `tools/video/to_ogv.py` |

Python packages: `numpy` everywhere; `opencv-python` for the face fit, texture projection, scan textures and video
joining; `mediapipe` for `tools/py/landmarks.py`, with the model file `tools/models/face_landmarker.task`; `scipy` for
the audio scripts, the video join and `hair_scan_cards.py` when it runs outside Blender; `Pillow` for a few texture
scripts; `openai-whisper` (model `small.en`, run locally) for `tools/py/voice_align.py` only. Blender's own Python needs
nothing beyond what Blender ships. Steps that need OpenCV or MediaPipe run as a separate Python 3.11 process started by
the Blender script.

MPFB ships without clothes, hair or skins. The build machine has these MakeHuman asset packs installed:
`makehuman_system_assets`, `skins01`-`03`, `hair01`-`03`, `shirts01`-`03`, `pants01`-`03`, `shoes01`-`03`,
`glasses01`-`02`, `eyebrows01`, `eyelashes01` and `faceunits01` (the ARKit face shapes). Every asset a character uses is
listed with its author and licence in `assets/characters/CREDITS.md`. Pack archives install with:

```
$BLENDER -b -P tools/blender/install_packs.py -- <pack.zip> [<pack.zip> ...]
```

In the commands below `$BLENDER` is `/Applications/Blender.app/Contents/MacOS/Blender` and `$GODOT` is
`~/Applications/godot/Godot.app/Contents/MacOS/Godot`. All commands run from the project root. After any build,
`$GODOT --headless --path . --import` imports the new files.

## Coordinates

Game space is Godot space: metres, Y up. The X axis runs along rue Pasteur and Z points across it, with bâtiment
Voltaire on the negative Z side and cour Pasteur on the positive side. The code calls these "east" and "south", but the
frame is turned from the compass: +X points to bearing 76.4°, so true north is 13.6° clockwise from -Z. The origin is
at 48.8154047 N, 2.3630521 E, on the midline of rue Pasteur. [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md) §2 explains how the
frame was chosen. `WorldEnv.sky_dir(azimuth, elevation)` turns a compass direction into game space and
`WorldEnv.bearing_of(dir)` goes back.

The campus scripts author geometry in game space and convert it with `campus_geo.P(x, y, z) -> (x, -z, y)`, so a glTF
export with +Y up lands on game coordinates with no transform in Godot. Characters are built facing -Y in Blender, which
is +Z in Godot. Yaw is a rotation about +Y, and yaw 0 faces +Z.

## Characters

`tools/blender/build_human.py` builds one character per argument and writes `assets/characters/<id>.glb`, or
`<id>_<outfit>.glb` for an outfit other than `default`. All settings come from `tools/blender/cast.py`.

```
$BLENDER -b -P tools/blender/build_human.py -- mano:street ian karim
$BLENDER -b -P tools/blender/build_human.py -- toma:fit1 --out=tools/out/try --preview
```

An argument is `<id>` or `<id>:<outfit>`; without an outfit the first one in the cast entry is built. `--out=<dir>`
writes the GLB there and leaves `assets/characters/` alone, `--preview` also renders a full-body and a face image to
`tools/out/`, `--no-photo` skips the face fit, `--no-anim` skips the animation clips, and `--hair=scan` or
`--hair=scan_cards` overrides a scanned outfit's hair mode. A rebuild overwrites the shipped GLB, so build with `--out=`
first to compare the two.

### What a build produces

Every character has the MPFB `game_engine` skeleton (53 bones with Unreal-style names such as `pelvis`, `spine_01`,
`neck_01`, `head`, `upperarm_l`, `hand_l`, `thigh_l`, `foot_l`), the 52 ARKit blend shapes on the body mesh
(`eyeBlinkLeft`, `jawOpen`, `mouthSmileLeft` and so on) and 19 animation clips.

Mesh nodes and materials are named `<id>_<kind>_<asset>`. The kind decides the material the game gives the surface
(`scripts/actors/character_materials.gd`):

| Kind | Mesh | Material in Godot |
|---|---|---|
| `skin` | the body (node `<id>_body`); on a scanned outfit also `<id>_skin_head`, the head with its own textures | standard, with subsurface scattering in skin mode (off on Low quality) |
| `cloth` | a garment, or `<id>_cloth_scan`, the clothed part of a scanned body | standard, with the garment's maps |
| `eye`, `cornea` | the eyeballs, and the cornea split off as its own glossy shell | `eye.gdshader`, which shades the sclera away from the iris and can recolour the iris |
| `brow`, `lash` | MakeHuman's alpha cards | standard, alpha |
| `teeth`, `tongue` | the MakeHuman mouth parts | standard; dark while the mouth is closed, lit as the jaw opens |
| `hair` | hair cards: generated, a MakeHuman hair asset, or scan cards | `hair.gdshader` and `hair_fringe.gdshader`; for scan cards `hair_scan.gdshader`, `hair_scan_fringe.gdshader` and `hair_scan_ear.gdshader` |
| `hairshell`, `hairunder`, `haircap` | a scan's sculpted hair as one surface, the same surface as a dark layer under scan cards, and the scalp cap | standard for the shell and the cap, `hair_under.gdshader` for the underlayer |
| `glasses` | frames and lenses | `glasses.gdshader`, with a second pass (`glasses_over_hair.gdshader`) that draws the temple arms over hair, using the stencil buffer |

### Build steps

`build_human.build()` runs these in order.

1. Create the body. MPFB builds a human from the cast entry's `macro` values (MakeHuman's body sliders, such as age,
   muscle, weight, proportions and height) and optional `targets` (MakeHuman's detail sliders), with the eyes, lashes, teeth and tongue
   from `cast.BASE`, the outfit's clothes, the glasses and the brows. Subdivision is off and the targets are baked.
2. Fit the face to photos and project a photo into the skin texture (`face_fit.py`), if the entry has a `photo`.
3. For an outfit with a `scan`, wrap the body onto the scan (`scan_wrap.py`), then apply `face_finish` and seat the
   glasses. See "Scanned outfits".
4. Make the hair: scan cards, generated cards or a MakeHuman asset.
5. Load the 52 ARKit face shapes and interpolate them onto the meshes that sit on the face (brows, lashes, eyes, teeth,
   tongue, glasses), each of which keeps the subset that moves it. For a scanned outfit the shapes are rescaled with the
   head fit (`scan_wrap.scale_shapes`) and copied to the scalp cap.
6. Bake modifiers, remove MakeHuman's helper geometry and finish the meshes (`finish_meshes`): split the cornea,
   classify every mesh into a kind, subdivide very low-poly clothes so their normal maps hold up, rebuild each material
   as a plain Principled BSDF that the glTF exporter understands, and rename everything.
7. Remove hidden faces (`cull_hidden`). Garments are layered by keywords in their names (trousers and shoes 1, shirts 2,
   jackets 3). A body or inner-garment face is deleted when every one of its vertices has an outer garment within
   4.5 cm along its normal. The head, the neck and the hands are never cut.
8. Retarget the animation clips onto the rig (`retarget.py`).
9. Export one binary glTF with the rig and every skinned mesh: skins, blend shapes, one sampled action per clip, deform
   bones only, +Y up, custom properties as extras. Textures are embedded, so a character file is about 40 MB.

### Face fit from landmarks

The fit works on 468 anchor points, one for each MediaPipe face landmark, stored in
`tools/models/mpfb_face_anchors.json` as three vertex indices and barycentric weights on the MakeHuman base mesh.
`$BLENDER -b -P tools/blender/face_calib.py` produced the file once: it renders a neutral MPFB head straight on, runs
the landmarker on the render and ray-casts each landmark onto the mesh. MPFB's topology is fixed, so the same anchors
work for every character.

For each photo in the entry's `photos` list, `tools/py/landmarks.py` runs the MediaPipe Face Landmarker and caches the
result beside the photo as `<photo>.lm.json`; when a photo holds several faces the largest is used. Then
`tools/py/face_solve.py` finds the camera with `solvePnP` on the rigid landmarks (nose, eyes, brows), searching over
focal lengths. It pushes the remaining 2D error back into 3D in the camera's image plane, partly symmetrises it, clamps
each step to 12 mm and the total to 14 mm, and iterates six times. Depth is never invented: a photo only moves points
within its own image plane.

With several photos the displacements are averaged, the first photo counting double, and a photo whose fit error is over
3.5 % of the face width is skipped. Different angles together constrain the shape better than one frontal photo. A
Gaussian radial basis function (radius 22 mm) then spreads the landmark displacements over the head. Eyes, teeth and
tongue move rigidly by the mean displacement so the eyeballs stay round, and glasses move by the median.

| Cast key | Effect on the fit |
|---|---|
| `photos` | the photos to fit, best frontal one first; `photo` is the single-photo form |
| `photo_ignore: ["mouth"]` | leave the lips out of the fit and weight the chin down. The solver also does this by itself when the landmarker reports an open or puckered mouth. |
| `oval_weight` | weight of the face outline landmarks, default 0.35; the outline slides with head pose, so it is trusted less than the nose and eyes |
| `photo_finish: {"widen": {...}}` | after the fit, widen the cheeks and jaw by a fraction (unscanned builds) |

### Texture projection

`tools/py/face_texture.py` projects the first photo into the MakeHuman skin texture. It cleans the photo (inpaints the
eyes and an open mouth, removes glasses rims), flattens its lighting while keeping detail, and renders a depth buffer of
the fitted head from the solved camera so that only visible surface is sampled. It then rasterises every face triangle
in UV space, sampling the photo, and blends the result through a feathered mask into the base skin, which is first
colour-matched to the face. The output is a 4096 px texture, or 2048 px for background characters.

| Cast key | Effect on the texture |
|---|---|
| `skin_ref` | a reference skin colour; the photo's white balance and exposure are pulled part of the way to it |
| `delight` | how much of the photo's shading is removed, default 0.7 |
| `eye_weight` | how much of the photo is kept round the eyes, default 0.35; the rest fades to the base skin |
| `no_forehead` | keep the base skin above the brows |
| `glasses_in_photo`, `glasses_smooth` | mask rims found by line detection (on by default when the character has glasses), or remove faint rims with a median filter over a band round each eye |
| `mouth_lift`, `brow_deepen` | adjust the photo's tone round the mouth or on the brows before projection |
| `eye_color` | the iris colour; the build recolours MakeHuman's iris texture with it and keeps its fibres and pupil |

### Hair

The cast entry chooses one of three kinds. The third, cards laid over a scan's hair, is described under "Hair cards
over a scan".

Generated cards (`hair_style`, built by `tools/blender/hair_gen.py`). Roots are scattered over the scalp above a
hairline traced from the face landmarks. Each strand grows through the style's flow field with gravity, is kept outside
the head and body, and is pulled into clumps toward its tip. Every strand becomes a tapered ribbon card mapped onto a
generated strand texture with alpha and a root-to-tip colour ramp (`hair_colors`). A thin dark cap 1.5 mm above the
scalp hides the skin between cards. The presets in `hair_gen.STYLES` are `fringe`, `swept`, `long_part`, `layered`,
`curly`, `braids` and `short`; each sets lengths per region, card count, width, gravity, lift, clumping and where
strands may end. A cast entry overrides any preset key with `hair_gen: {...}` and fixes the random seed with
`hair_seed`. Background characters get 60 % of the card count.

A MakeHuman hair asset (`hair`, tinted by `hair_tint`). MPFB fits it like a garment. `hair_stretch`
(`tools/blender/mh_hair.py`) can lengthen it below the shoulders and keep it clear of the body, the clothes and the
glasses' arms. `tools/blender/try_hair.py -- <id> <hair1> <hair2> ...` renders one head with several assets.

### Clothes and glasses

Clothes are MakeHuman assets that MPFB fits to the body. An outfit lists them as `(asset, tint)` pairs. A tint replaces
the texture's hue and keeps its luminance, so the weave and shading stay; `None` keeps the asset's own colours. A
scanned outfit has an empty clothes list because the scan supplies the clothing.

Glasses are a MakeHuman asset named in `glasses.asset`. An untextured frame takes `frame` as its colour and `metal` as
its metallic value; a textured frame is recoloured to `frame`. The glasses follow the face fit rigidly.
`tools/blender/glasses_seat.py` refines the result when the entry asks for it: `clear` moves the glasses forward until
the front of the frame stands a given distance off the skin, `lens` reshapes the front so each lens sits at given
offsets from the eyeball centres, `seat` seats the rims by rays cast from in front of the face, and `wire` changes the
rim's thickness and outline. `lens_fit` applies the last three to an unscanned build.

### Animation retargeting

The clips come from motion capture: the CMU Graphics Lab database for idles, sitting, typing, talking and one-shot
gestures, and the Bandai Namco Research Motion Dataset for walk, jog, run and wave. The takes used are in
`assets/anims/src/` with their licences in `assets/anims/src/CREDITS.md`. The Bandai clips are CC BY-NC 4.0, which is
why the game is non-commercial.

`tools/blender/anim_clips.py` is the clip table: source take, time range, kind (`loco` for an in-place gait loop, `loop`
for a seamless loop, `oneshot`) and options such as `mirror`, `rate`, `fingers`, `seat`, `upper` and `legs` (take part
of the body from another take) and `turn`. It also describes the two source skeletons.

`tools/blender/anim_prep.py` converts each take once into a skeleton-independent clip, cached as
`assets/anims/cache/<clip>.json`: for every body segment the world rotation relative to a canonical T-pose, plus joint
positions measured in leg lengths and foot contacts, at 30 fps. It needs only numpy and runs automatically.

`tools/blender/retarget.py` applies the cached clips to a rig of any proportions. Each bone takes its segment's rotation
composed with its own rest frame moved into the same T-pose. Hip height and stride scale with the leg-length ratio. Legs
are then solved with two-bone IK onto the scaled ankle positions, with planted feet locked and a ground clamp. Arms are
pushed out of the torso and fingers get a relaxed curl. Sitting clips are placed on a seat 0.45 m high whose front edge
is at the character root, and `typing` puts the wrists on a desk.

Locomotion clips play in place. Each armature carries its own stride speeds as the glTF extra `anim_speeds = {walk,
jog, run}`, which `CharacterRig` reads to match foot speed to movement speed. The 19 clips are `idle`, `idle_2`, `walk`,
`jog`, `run`, `sit_idle`, `sit_talk`, `typing`, `sit_down`, `stand_up`, `talk_idle`, `talk_1`, `talk_2`, `shrug`,
`wave`, `look_around`, `pickup`, `turn_l90` and `turn_r90`. `tools/blender/anim_test.py` renders a contact sheet of each.

### Cast settings and adding a character

`cast.CAST` maps a character id to a dictionary. The keys not already covered above:

| Key | Meaning |
|---|---|
| `macro`, `targets` | MakeHuman's body sliders (0 to 1) and named detail targets with weights |
| `skin` | the MakeHuman skin material the texture starts from |
| `brows` | a MakeHuman eyebrow asset, or `None` to use the brows in the projected photo |
| `tier: "npc"` | a background character: 2K skin, fewer hair cards |
| `outfits` | outfit name to `{clothes, ...}`; a scanned outfit adds `scan`, `hair`, `face`, `hair_cards` and the head-scan keys |

The eight main characters are written out in full. The 19 background characters go through the `npc()` helper, which
takes a body, a skin, a hair style and three garments with colours, and has no photo fit.

To add a character:

1. Add an entry to `cast.CAST`. For a background character one `npc(...)` line is enough. For a likeness, put the photos
   under `tools/photos/<id>/` and list them in `photos`, best frontal one first.
2. Build it with `--preview`, then import it into Godot.
3. Look at it under the game's lighting: `$GODOT --path . res://scenes/dev/char_viewer.tscn -- <id>`.
4. Give it a role in `scripts/story/cast_defs.gd`, where `model` is the GLB's file name without the extension.
5. Add any asset it introduces to `assets/characters/CREDITS.md`.

Review tools: `tools/dev/face_sheet.py` and `face_closeup.py` render a GLB's face in Blender, `face_metrics.py` measures
scale-free face proportions from landmarks on photos and renders alike, and the scenes `char_viewer`, `glass_probe`,
`hair_still_viewer` and `anim_preview` in `scenes/dev/` render a GLB with the game's own shaders.

## Scanned outfits

An outfit with `"scan": "<id>/<file>.glb"` dresses the character in a 3D scan of the person in their own clothes. The
scan is one textured shell of clothes, shoes, hair and skin, with no rig, no face shapes and fused fingers, so it cannot
be animated as it is. `tools/blender/scan_wrap.py` keeps the MPFB body, with its rig and face shapes, and wraps it onto
the scan. Six shipped models are built this way: `anisha`, `ian`, `joaquin`, `mano_street`, `silvia` and `toma_fit1`.
Where the scans come from is stated under "AI-generated material".

### The wrap

1. Normalise the scan: upright, facing -Y, soles on the floor, eyes at the character's eye height. The front is the side
   where the face landmarker finds a face in rendered views, and its landmarks cast onto the scan give the face's 3D
   points. The character keeps the height set in `cast.py`; the scan's head is fitted to the body's.
2. Fit the face: the same Gaussian RBF as the photo fit moves the character's face, eyes, teeth and lashes onto the
   scan's landmark points, so eyelids, lips and face shapes keep working.
3. Bring the scan into the rig's rest pose. The skeleton is posed to the scan's stance, with arm and leg axes found from
   horizontal slices. The scan is skinned to that pose and then un-posed. Lifting the scan's arms stretches its armpits
   the way fabric would; posing the body down to the scan would crush them.
4. Project the body onto the scan part by part (torso, each sleeve, each trouser leg) along its normals, and smooth the
   offsets over the mesh. `REACH` limits how far each part may move. The fitted face and the hands keep their own shape.
5. Bake the scan's colour, roughness and detail normals into the body's UVs with Cycles at 4096 px.
   `tools/py/scan_compose.py` fills the texels the bake's rays missed and tones the kept hands and ears to the face.
6. Split the materials. Skin-coloured faces of the head, neck and hands keep a skin material. Everything else becomes
   `<id>_cloth_scan`, which uses the scan's roughness map. The head becomes `<id>_skin_head` with its own 4K texture:
   its UVs are repacked, because MakeHuman's shared atlas leaves the face only a few hundred pixels.

The mouth's inside is not fitted on its own: it follows the displacement of the skin round it (`follow_mouth`,
`tuck_mouth`) and keeps the template's colour, darkened with depth.

With `"face": "<id>/portrait.png"` a sharp frontal portrait supplies the face's detail, because a full-body scan gives a
face only a couple of hundred pixels wide. `shape_from_portrait` refines the face's shape in the front plane, and
`tools/py/portrait_project.py` warps the portrait onto the head texture with a landmark-driven 2D map (a least-squares
affine plus a thin-plate correction), colour-matched to the scan's skin round it and feathered in.

`tools/blender/face_finish.py` runs after the wrap when the cast entry has `face_finish`. Its keys widen the cheeks and
jaw (`widen`), repaint parts of the head texture (`brows`, `eye_corners`, `temples`, `temple_skin`), adjust the teeth
and the shading inside the mouth (`teeth`, `mouth_dark`), and fix faces at the collar (`neck_skin`, `collar_hair`).

### A separate head scan

An outfit can add `"head_scan": "<id>/<file>.glb"`, a bust scanned on its own at higher resolution, to replace the head
of the full-body scan. `toma_fit1` uses one. `splice_head` loads the bust in any unit and facing, places it by a
similarity transform from its face landmarks onto the body scan's, and turns the face straight ahead using mirrored
landmark pairs. A rigid ICP refinement on the skin round the ears is kept only if it does not move the face landmarks
further from the body scan's. The bust is decimated (the face to edges of about 1.2 mm, the rest to the body scan's
density) while a full-resolution copy takes every later move and cut and is what the texture bakes read. Both scans are
cut along a line under the jaw, and the bust's neck is blended onto the body scan's within 1.5 cm.

The template's head is then moved onto the bust as one smooth displacement field (`fit_head`, least squares with a
bending term). `flatten_ears` turns the template's ears in toward the scan's. `tuck_skull` holds the cranium under the
scan's hair but never smaller than `SKULL_MIN` (199 mm long, 150 mm wide), and `fit_hair` moves the hair out over the
skull where they would intersect. The scan's sculpted hair is rebuilt as one clean height field over the directions from
the head's centre (`hair_envelope_mesh`), which removes undercuts that would give the cards inward-facing normals.

After the bakes a series of passes cleans the head texture: eye corners, the skin beside the face, sideburns, earlobes,
nostrils, the portrait's edge, facial hair and brows. The body below the neck is given the material split and the maps
of a build without the head scan (`absent_fit`, `absent_bake`, `absent_maps`), so a head scan changes only the head and
neck.

| Outfit key | Effect |
|---|---|
| `head_scan_fit: "affine"` | give the bust's face the template's proportions; the default is a similarity fit |
| `head_scan_jaw` (0 to 1) | widen the lower face from the bust's shape toward the person's photos |
| `skull_crown: {gap}` | hold the top of the skull further under the scan's hair |
| `brow_paint`, `beard_dark`, `side_clear` | texture passes for brows, facial hair and the cheek in front of the ears |

`tools/dev/head_scan_build.py` builds an outfit with a given head scan into another file without touching `cast.py` or
`assets/characters/`; the other `tools/dev/head_*.py` scripts compare such builds and render review sheets.

### Hair cards over a scan

A scan's sculpted hair carries the person's real hairstyle, but shown as a surface it reads as a matte helmet. The
outfit's `hair` key picks one of two modes. `"scan"` keeps the sculpted hair as one mesh (`<id>_hairshell_scanhair`); no
shipped model uses it. `"scan_cards"` never shows the shell as a surface. `tools/blender/hair_scan_cards.py` uses it in
three ways:

1. Smoothed (Taubin), it is the guide the cards follow.
2. Moved 1.5 mm inward and textured dark and matte, it is the underlayer seen through the gaps between cards
   (`<id>_hairunder_scan`). It is kept only where an opaque card lies over it.
3. Short overlapping alpha cards (`<id>_hair_scancards`) cover it along a flow field. The field blends the style's own
   flow with the strand direction painted in the scan's texture, found from the structure tensor of the baked hair
   colour. Cards are laid in three layers (`under`, `mid`, `top`), followed by a coverage pass that puts every guide
   vertex under an opaque stretch of some card, then hairline cards and a few flyaways.

A scalp cap (`<id>_haircap_scan`) is the head's hair-covered triangles 1 mm above the skin, with a mask of where the head
texture is hair. The mask comes from two colour clusters learnt per person, the shell's own colours against the forehead
skin. The cap turns the scan's painted hairline into dark roots that fade into the skin without touching the face
texture.

Card colour comes from a per-person strand atlas (`tools/blender/hair_atlas.py`): eight vertical strips from dense clumps
to a few flyaway strands, tinted from the root colour to the tip colour. Inner layers pick the dense strips and outer
layers the wispy ones. Vertex colours carry only depth tone and root fade. The atlas kinds are `curly`, `wavy`, `wavy2`,
`straight` and `short`.

Long hair (`"hair_long": true`) gets a face window fitted per person that keeps cards, underlayer and cap off the face.
Strands that reach the shoulders drape to the front or the back, and everything below the shoulders is skinned to the
spine. Two rules always apply: the glasses' arms press the hair under them, and nothing lies between a lens and the
face. Card vertices in front of the upper face carry a second UV set that lets the shader leave a fringe's tips out of
the shadow pass.

The presets in `hair_scan_cards.STYLES` are `curly`, `long_part`, `swept` and `fringe`, picked by the cast entry's
`hair_style`. An outfit overrides any preset key with `"hair_cards": {...}`:

| Group | Keys |
|---|---|
| Colour | `root`, `tip`, `under`, `cap_color`, `atlas` |
| Flow | `style`, `flow` (`curly`, `long_part`, `swept`, `side_swept`, `fringe`, `curtain`), `part_x`, `sweep`, `lift`, `split`, `spread`, `gravity`, `curl`, `tex_w` (weight of the scan's painted direction) |
| Density | `layers` (per layer: cards per m², length, width, lift, tone, atlas strips, root fade), `cover`, `loops`, `fly` |
| Guide shape | `smooth`, `fill_pits`, `deflate`, `crown` as a dictionary (lowers the top), `side_trim`, `front_lift`, `normal_r` (radius over which shading normals are averaged) |
| Front hairline | `front_floor`, `front_free`, `floor_jitter`, `floor_wave`, `floor_wave_fine`, `floor_rise`, `floor_slide`, `floor_arch`, `brow_band`, `front_wisp`, `front_tip`, `eye_beyond`, `front_locks`, `lip_light`, `under_front` |
| Ears | `ear_free`, `ear_drape`, `ear_wisp`, `ear_veil`, `ear_stencil`, `cap_side` |
| Long hair | `window_min`, `window_smooth`, `window_dense`, `window_hairline`, `front_len`, `front_y`, `end_trim`, `taper`, `underside`, `under_inner`, `fall_on`, `fall_front`, `hem_min`, `front_lit`, `drape_cover`, `cape`, `neck_clear` |
| Locks and tone | `lock_clump`, `curl_tips`, `edge_free`, `clump_tone`, `relief_tone`, `tone_exposed`, `root_tone`, `under_roots`, `part_gap` |
| A rolled curtain fringe | `roll_under`, `roll_bare`, `roll_smooth`, `roll_deflate`, `roll_tuck`, `roll_drape`, `roll_tone`, `roll_fill` |

Each key is documented where `hair_scan_cards.py` reads it. Keys added for one person are off by default and draw from
their own random sequence or from a hash of the root position, so turning one on does not reshuffle the rest of the hair.

Every build with scan cards saves the generator's inputs to `tools/out/scan_<id>/hair_guide.npz`.
`python3.11 tools/dev/hair_cards_preview.py <id> [set=key:json ...]` regrows the cards from that file in plain Python,
without Blender, and renders a quick software preview for tuning the geometry.

## How Godot uses the character files

Godot imports a character GLB with the default scene importer and no import script. Animations are imported at 30 fps,
and the embedded textures are extracted next to the GLB as `<glb>_<image>.png`.

When a character is loaded, `CharacterRig.load_model()` instances the scene and `CharacterMaterials.apply()` replaces
every glTF material with a game material chosen by kind, as listed under "What a build produces". Scan cards are drawn
with `lod_bias = 100`, because the importer's automatic LODs tear alpha cards apart. Characters receive global
illumination but are left out of the SDFGI voxelisation. Brows, lashes, eyes, teeth, the scalp cap and glasses cast no
shadows. Background characters fade out with distance and use cheaper hair.

`CharacterMaterials.FINISH` holds per-person shader settings that the GLB does not carry, keyed by the id prefix of the
mesh names: iris colour and specular, glasses frame finish and lens tint, hair ambient and highlight response, lash and
brow opacity. A character not listed there renders with the defaults.

## Campus

`tools/blender/build_campus.py` builds the whole level in code. There is no hand-edited .blend file, and the build is
deterministic: it uses no clock and no unseeded randomness.

```
$BLENDER -b --factory-startup -P tools/blender/build_campus.py                  # level and props
$BLENDER -b --factory-startup -P tools/blender/build_campus.py -- --no-props    # level and markers only
$GODOT --headless --path . --import
$GODOT --headless --path . res://scenes/dev/marker_list.tscn -- out=tests/fixtures/markers.json
```

The last command rewrites the marker fixture that the headless story tests read, and should follow every level build.
Other options after `--`: `--props-only` rebuilds only the props and `--props=a,b` picks some, `--gen-only` builds only
the generated textures, `--no-export` builds without writing the level file, `--blend` also saves
`tools/out/campus_cache/campus.blend`, and `--preview` renders check images to `tools/out/campus_*.png` (`--fast` lowers
the samples, `--views=a,b` picks views).

| Module | Builds |
|---|---|
| `campus_layout.py`, `campus_poly.py` | shared constants and the real building footprints in game metres; polygon orientation, clipping and triangulation |
| `campus_geo.py` | the geometry builder: parts with several material slots, box-mapped UVs at constant texel density, vertex colours for grime and variation, colliders, markers |
| `campus_arch.py` | walls with openings, windows, doors, curtain walls, stairs, railings |
| `campus_mat.py`, `campus_tex.py`, `campus_gen.py` | the material library, the texture download and import presets, and generated textures (posters, screens, whiteboards, notices, bark and leaf cards) |
| `campus_street.py` | rue Pasteur: road, kerbs, pavements, markings |
| `campus_kb1.py`, `campus_voltaire.py` | bâtiment Voltaire (KB1): the shell and both facades, then the lobby, stairs, corridor and the SM14 and SM15 rooms inside |
| `campus_south.py` | the south side: Paritalie, 24 rue Pasteur, cour Pasteur, Amphi 4, the cafeteria, the Under |
| `campus_backdrop.py`, `campus_backdrop_data.py` | the surrounding neighbourhood on its real outlines. The data file is generated: `python3.11 tools/py/backdrop_from_svg.py` rewrites it from the campus layout drawing, [campus_layout.svg](campus_layout.svg). |
| `campus_dress.py`, `campus_props.py`, `campus_props_out.py` | set dressing and prop markers; indoor and outdoor props |
| `campus_markers.py`, `campus_preview.py` | gameplay markers; check renders, which are not exported |

### Footprints

The south side of rue Pasteur and KB1 stand on real building outlines taken from the cadastre and IGN data, as described
in [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md) §5.1. They are the polygons in `campus_layout.py` (`X_PARITALIE`, `EAST_24`,
`PASSAGE_N`, `COURT` and others) and the outline constants in `campus_kb1.py`. A footprint is walked clockwise in
(x, z), which puts every wall's outside face on the right.

### Materials and textures

Materials are Principled BSDF node trees named `M_<name>`. Most use a CC0 texture set from Poly Haven or ambientCG,
stored in `assets/textures/<asset_id>/` as base colour, OpenGL normal map and a packed occlusion/roughness/metallic map.
`campus_tex.py` downloads a set that is not on disk yet and writes a Godot import preset beside each image;
`assets/textures/SOURCES.json` records where each set came from. Surfaces with no CC0 source get a procedural texture
written to `assets/textures/campus_gen/` by the build itself, for example `campus_kb1.ribbed_steel()`. Deleting a
generated file makes the next build write it again.

The level file does not embed textures. The exporter writes a separate glTF, and `gltf_to_glb()` packs it into a GLB
whose image URIs point to `../textures/...`, so the level and the props share one copy of each texture.

Three naming rules matter to the game:

- A material whose name contains `glass` is replaced in Godot by a tuned glass material.
- A part named `far_*` belongs to the backdrop. It casts no shadows and stays out of global illumination.
- A window of a room nobody enters is a single quad with material `M_window_<kind>`. Its UVs carry the room's seed and
  its chance of being lit at night, and the game draws a ray-traced room behind it (`scripts/fx/interior.gdshader`).

Collision is separate from the visible meshes: simplified boxes and ramps named `<name>-colonly`, which Godot turns
into static bodies on import. Stairs get a ramp collider and their visible steps carry none.

### Markers

Gameplay positions are Blender empties, exported as nodes. Their custom properties are exported as glTF extras and read
in Godot with `node.get_meta("extras")`. `scripts/level/level_binder.gd` reads them when the level loads.

| Name | Meaning | Extras |
|---|---|---|
| `SPAWN_player` | start position and yaw | |
| `NPC_<id>` | where a character stands or sits | `sit`, `sleep`, `model`, `name` |
| `SPOT_<id>` | an interaction hotspot | `label`, `range` |
| `ANCHOR_<id>` | a minigame or camera anchor | `cam_from`, `cam_look` as [x, y, z] |
| `DUCK_<id>` | a golden rubber duck | |
| `ZONE_<id>` | a room volume: a cube empty whose scale is the half extents | `label`, `sub`, `surface` (footstep sound) |
| `PATH_<name>_<nn>` | waypoints for background walkers | `loop`, `model`, `speed` |
| `PORTAL_<a>__<b>_<nn>` | ordered points through a door or stair between two zones | |
| `LIGHT_<name>` | a light created in Godot | `type` (omni or spot), `color`, `energy`, `range`, `shadow`, `angle`, `group` (the lamp group the time of day dims; without it the name prefix decides, `LevelBinder.LAMP_GROUPS`) |
| `PROP_<asset>__<nn>` | an instance of `assets/props/<asset>.glb`, with scale | |
| `DECAL_<texture>__<nn>` | a decal from `assets/decals/<texture>.png`; scale is the half extents | |
| `CAM_<name>` | a camera, such as the title shot | |

### Props, import and the map

Each prop is built round its own origin, at floor contact and facing +Z, and exported to `assets/props/<name>.glb` with
its own `-colonly` collider when it is solid. `PROP_` markers place them.

`assets/levels/campus_import.gd` is the post-import script for the level and every prop; the build writes it into each
`.import` file. It turns on vertex colour as an albedo multiplier, because the baked grime and variation would otherwise
be ignored, and applies the `far_*` rule. At load, `LevelBinder` creates the lights, instances the props, builds
camera-only occluders from prop bounds, swaps in the glass, foliage and interior-window materials, and returns the
marker positions to the game.

`python3 tools/map/export_plan.py` writes `assets/levels/campus_plan.json`, the building outlines the in-game map draws.
It reads `campus_layout.py` and scans `campus_kb1.py` for its outline constants, so the map and the level share the same
numbers.

## Audio

All game audio is OGG Vorbis at 44.1 kHz in `assets/audio/`: `music/` and `amb/` in stereo, `sfx/`, `footsteps/` and
`voice/` in mono. `scripts/core/sfx.gd` loads files by stem, and numbered variants such as `concrete_1.ogg` to
`concrete_6.ogg` are picked at random. The scripts in `tools/py/` share `audio_lib.py`, which decodes through ffmpeg,
encodes through sox, and does filtering, loudness measurement, limiting and loop building in numpy and scipy. They are
run with `python3.11 -I`.

| Script | Output | Processing |
|---|---|---|
| `audio_music.py build [stem]` | `music/<stem>.ogg` | finds loop points by self-similarity at bar multiples and refines them by cross-correlation, crossfades the seam, normalises to -18 LUFS |
| `audio_amb.py [stem]` | `amb/<stem>.ogg` | filters and layers the sources, makes a seamless loop by crossfading the audio after the loop end into its head, sets a target loudness per loop |
| `audio_sfx.py [stem]`, `sfx_synth.py [stem]` | `sfx/<stem>[_N].ogg` | cuts or synthesises each one-shot, trims to the first transient, fades the tail, normalises the peak to about -3 dBFS; `sfx_synth.py` makes three effects by synthesis alone |
| `audio_footsteps.py build [surface]` | `footsteps/<surface>_<n>.ogg` | slices single steps out of walking recordings at the transient and level-matches each set |
| `audio_import.py` | `.ogg.import` files | marks music and ambience as looping streams for Godot |
| `audio_verify.py`, `audio_credits.py` | a report, and `assets/audio/CREDITS.md` | decodes every delivered file and checks format, loudness, peaks, silence and loop seams; generates the credits from the build manifests and the licence records |

The music is by Kevin MacLeod (CC BY 4.0). Ambience, footsteps and sampled effects come from Freesound uploads and
Kenney packs under CC0. `assets/audio/CREDITS.md` lists every file with its sources and edits.

### Voice lines

Voice files are one per subtitle card, named `<key>.ogg`, where the key is the voice id, an underscore, and the first
ten hex digits of `sha1("<voice id>|<exact card text>")` (`VoiceLines.key` in `scripts/story/voice.gd`). A card whose
text changes no longer finds its file and plays silent, so a recording can never go with the wrong words.
`assets/audio/voice/manifest.json` lists each file with its text, its length and a 30 Hz jaw envelope that drives the
speaker's mouth. Only the fictional NPCs have voice files; the friends' characters have none.

```
$GODOT --headless --path . res://scenes/dev/voice_lines.tscn -- out=tools/out/voices/cards.json
python3.11 tools/py/voice_build.py lines     # what each card says aloud, with digits spelled out
python3.11 tools/py/voice_align.py           # cut points between lines in a take, and a transcription check
python3.11 tools/py/voice_build.py build     # cut, high-pass, level, encode, write the manifest
```

One take may hold several lines of one voice. `voice_align.py` transcribes it with Whisper, matches the words to the
expected lines, and places each cut in the quietest 10 ms between two lines. `voice_build.py` levels each line to
-18 LUFS with true peaks at most -3 dBFS. An exported build must include `manifest.json`, which is not a Godot resource:
add `*.json` to the export's include filter.

## Opening video

`assets/video/dream.ogv` is the short dream sequence between chapter 1's card and the wake-up: 1280x720, 24 fps, Ogg
Theora without audio, the only video format Godot 4.7 plays. `main._play_dream()` plays it and dissolves into the
same shot rendered live.

The clip has two halves. The first is rendered by the game itself: an autotest plan (`autotest=dream`) plays a
precomputed camera and earbud track frame by frame in Amphi 4 and saves several steps per frame, which are averaged in
linear light for motion blur. The second half is a generated clip (see "AI-generated material") made from two
engine-rendered keyframes with nobody in the room.

| Tool | Purpose |
|---|---|
| `tools/video/join_dream.py` | conforms both halves to 24 fps, bridges the seam with optical flow (falling back to a cross-dissolve where the flow is unreliable), morphs the end onto the final keyframe, and writes an mp4 with contact sheets |
| `tools/video/dream_matte.py` | builds the earbud layer of the first half from four render passes (normal, plate without the earbud, earbud white, earbud black): white minus black gives a true soft matte, and the plate lets the earbud's own colour be separated from the floor |
| `tools/video/to_ogv.py`, `theora_enc.c` | convert any video to Ogg Theora and check the result; the script compiles the encoder on first use |

`to_ogv.py` exists because an ffmpeg build without a Theora encoder writes VP8 into an `.ogv` file, which Godot cannot
play. ffmpeg only decodes and converts colour (Theora players decode with the BT.601 matrix, and the sources are
BT.709); `theora_enc.c`, linked against libtheora and libogg, encodes. The script verifies the codec, the keyframe
positions, the frame count and the mean colour of every frame against the source.

```
python3.11 tools/video/to_ogv.py in.mp4 assets/video/dream.ogv --quality 56 --size 1280x720 --keyint 72 --keyframe-at 200
$GODOT --path . -- autotest=opening
```

`--keyframe-at` forces a keyframe where the end hold starts, so the still picture does not change at a later regular
keyframe. The second command plays the opening in the game. `assets/video/CREDITS.md` records the shipped clip's commands.

## Other generated textures

`python3.11 -I tools/py/fx_textures.py` writes `assets/textures/fx/`: `lens_dirt.png` (the bloom's dirt map),
`grain.png` (tileable film grain) and `leaves_fall.png` (a 2x2 atlas of leaves for the falling-leaf particles, cut from
the CC0 leaf sets the trees use). `python3.11 -I tools/py/notebook_tex.py` writes
`assets/textures/notebook_algo/notebook_algo.png`, the open notebook in the wake-up shot. Both are procedural and use
fixed seeds, so a rerun gives the same files. The sky panoramas in `assets/hdri/` are Poly Haven HDRIs (CC0).

## Story data

The story is data too: `dialogue/*.dlg` hold every line in a small subset of Dialogue Manager 4's syntax (the header of
`scripts/story/dialogue_data.gd` documents the format), `dialogue/chat.json` holds the phone's message threads, and the
JSON files in `data/` hold chapters, named places and shots, flags, and the content of the journal, the phone and the
minigames. [ARCHITECTURE.md](ARCHITECTURE.md) describes how the game reads them. One headless run checks all of it:

```
$GODOT --headless --path . res://tests/test_runner.tscn
```

## AI-generated material

Some source material was made with generative models through Higgsfield. All of it is listed here.

| Material | Model | Used for |
|---|---|---|
| Full-body reference images and frontal portraits of six characters | GPT Image 2.5 | the input to the 3D scans, and the face texture of the scanned outfits |
| Six full-body 3D scans and one head scan | Tripo image-to-3D | the outfits `anisha`, `ian`, `joaquin`, `mano_street`, `silvia` and `toma_fit1` |
| Voice lines of twelve fictional NPCs | Qwen Audio TTS, preset voices | `assets/audio/voice/` |
| The second half of the opening clip | Wan 3.0 image-to-video | `assets/video/dream.ogv` |

The friends have no synthetic voice. The records for the voices and the video are in `assets/audio/CREDITS.md` and
`assets/video/CREDITS.md`, and the scanned outfits are named in `assets/characters/CREDITS.md`.
