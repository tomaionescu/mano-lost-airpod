# Art direction

This document covers how the game looks, how its interface is drawn and how it sounds. Each part states the
intent first and then how the code implements it. The design it serves is in [DESIGN.md](DESIGN.md), the code
structure in [ARCHITECTURE.md](ARCHITECTURE.md), and the way assets are built in [PIPELINE.md](PIPELINE.md).
Known problems are listed in [STATUS.md](STATUS.md).

Three ideas run through all of it. The story is one real evening, Thursday 15 October 2026, from 17:42 to
past midnight, and the light runs out as it goes. Every piece of interface is an object from Mano's algorithms
notebook. Sound belongs to places: each zone of the campus has its own ambience, and music is tied to the
place, the hour, or a moment the player chooses to sit through.

## 1. Look

### 1.1 Intent

The reference is the Life is Strange series, where light and colour carry the mood more than surface detail
does, and where small movement such as leaves and dust makes a place feel inhabited. The campus is modelled
from the real one, so the game keeps a realistic base and puts its effort into lighting, grading and a
film-like lens.

The evening's light is computed. Sun and moon positions come from the campus coordinates (48.8154 N,
2.3631 E) and the date, so shadows fall where they would on that day and the sun sets when it should.

### 1.2 The six times of day

`scripts/level/world_env.gd` holds six presets in `WorldEnv.TIMES`. Each one lists only what differs from
`TIME_DEFAULTS`. Sun positions are compass azimuth and elevation in degrees.

| Preset | Clock | Chapters | Sun (az / el) | Sun energy | Ambient | Exposure | Street lamps | String lights | Lit windows |
|---|---|---|---|---|---|---|---|---|---|
| `golden` | 17:42 | 1 | 242.3 / 11.5 | 2.6 | 0.75 | 1.0 | off | 30 % | 0 |
| `late_gold` | 18:15 | 1, 2 | 248.9 / 6.6 | 1.9 | 0.62 | 1.0 | off | 60 % | 0.3 |
| `last_light` | 18:50 | 2 | 255.6 / 1.3 | 0.9 | 0.50 | 1.05 | on | 100 % | 0.8 |
| `blue` | 19:25 | 3 | 262.1 / -4.6 | off | 0.60, tinted blue | 1.4 | on | 100 % | 1.5 |
| `night` | 21:30 | 3, 4 | 286.3 / -25.1 | off | 0.20 | 1.45 | on | 100 % | 1.5 |
| `late` | 23:45 | cold open, 4, 5 | 320.4 / -43.7 | off | 0.18 | 1.45 | on | 100 % | 1.2 |

The chapter column comes from `data/chapters.json`, which names the presets each chapter uses.

#### Sun

One `DirectionalLight3D`. The level's +X axis runs along rue Pasteur at compass bearing 76.4°
(see [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md)), so `WorldEnv.sky_dir()` converts a compass position into game
space. As the sun drops its colour moves from warm white to orange and its angular size grows from 0.8° to
1.4°, which softens the shadow edges. The light itself never comes from lower than 2° (`MIN_SHADOW_ELEV`) to
avoid shadow artefacts at grazing angles; the sky still shows the sun at its true position.

#### Sky

`scripts/fx/sky_blend.gdshader` blends two HDRI panoramas (`assets/hdri/`). Each panorama is rotated
so that its own sun sits on the real sun's bearing, and its brightest texels are capped so the shader can draw
the sun disk where the sun really is. After sunset the panoramas fade into a procedural sky: an afterglow
toward the set sun, an orange-grey glow of light pollution low on the horizon, a few stars, and the crescent
moon (24 % lit, drawn at about twice its real size so it reads on screen). The moon is up at `blue` and has
set by `night`. The radiance pass has its own gain, tint and fill, so ambient light can follow the preset
without changing how the sky looks. The shader does not use `TIME`, so the sky's radiance map is only
recomputed when the preset changes.

#### Lamps

`LevelBinder` (`scripts/level/level_binder.gd`) sorts the level's lights into three groups by name:
street lamps (about 3000 K), the courtyard's string lights (about 2200 K) and classroom panels (about
4500 K). Each preset sets a level per group. The colours are chosen so that at 17:42 it is warm outside and
cool inside, and after sunset the reverse. Lights that belong to no group, such as signs and the lights of
the amphitheatre, the cafeteria and the Under, stay as exported all evening. `set_lamps()` changes one
group on its own; the chapter 2 script uses it to bring the street lamps on over four seconds. The Under also
has three warm wash lights of its own, over the sofa, the babyfoot table and the bar (`data/world.json`
"lights"): short-range, unshadowed, on all evening.

#### Windows

Rooms the player never enters are drawn with interior mapping
(`scripts/fx/interior.gdshader`, set up by `scripts/fx/interiors.gd`). Each window quad looks into its own
box-shaped room that is ray-traced per pixel, with walls, a floor, a ceiling light, a piece of furniture and
blinds or curtains, all without textures. There are five kinds (office, flat, two flat variants, hotel), and
each window carries its own chance of being lit. The preset's "lit windows" value drives their emission.

#### Faces after dark

During a filmed conversation one unshadowed spot light points at the face in shot (`set_convo_fill()`). It is
a key light, not a flash: it stands 18° round the face from the lens, to the camera's left, and 30° above it,
as far from the face as the lens is, and it reaches 1.9 times that distance, so the wall behind the face keeps
the scene's own light. Its energy is zero at `golden`, 2.4 at `blue` and 1.8 at `night` and `late`, with a cool
tint at blue hour and a warm one at night. The place sets its share: 40 % in a lamp-lit room, 45 % in the
Under. A conversation single aims a little under the face, which puts the eyes near the upper third of the
letterboxed picture (`CameraRig.EYE_LINE`).

#### Changing preset

`apply_time(name, seconds)` moves from one preset to another. It is only called under a
chapter card, a fade, a sit-down or a cut, so the player never watches a time-lapse. Numbers and colours
interpolate; the colour grade switches at the halfway point. The sun and the lamps are static lights in SDFGI
to keep it cheap, so the global illumination is switched off for two frames and rebuilt at the end of a
change. The preset's name is stored in the save.

#### Indoors

In an indoor zone `set_interior()` cuts the sky's ambient light to 60 %, thins the fog and
lowers the lens dirt and halation.

#### Light by place

Exposure and the conversation fill also follow the zone the camera is in (`WorldEnv.PLACES`, `set_place()`).
A place states how much of the preset's exposure above 1 it keeps, an exposure gain on top, and its share of
the fill. The Under, a dark-walled basement, is exposed 1.5 times up at every hour. Voltaire's corridors and
stairwell, white walls under ceiling panels that do not follow the clock, drop the night exposure and run at
0.9. Other rooms and the open air keep the preset's exposure. The values ease over 0.6 s as the camera walks
from one place to the next and change at once on a cut.

### 1.3 Tonemapping and grade

The tonemapper is AgX (white 6.0, contrast 1.25). It desaturates very bright highlights toward white instead
of clipping them to a saturated colour, which suits a low orange sun. Exposure is per preset, 1.0 in
daylight and up to 1.45 at night, then corrected per place (§1.2, Light by place).

After tonemapping, each preset applies a 17³ colour lookup table that `_make_lut()` generates in code from
five numbers. The grade desaturates yellow-green hues by up to 18 % so that foliage reads olive, tints
shadows and highlights separately, applies a gentle S-curve and lifts the blacks slightly, as faded film
does. Shadows lean blue and highlights warm in every preset: `last_light` pushes the highlights toward coral,
`blue` has the strongest blue, and at `night` and `late` the warm highlights keep lamp light warm.

### 1.4 Lens and post stack

Bloom and depth of field are set on the `Environment`. The rest is a full-screen shader drawn under the UI
(`scripts/fx/post.gdshader`, driven by `scripts/fx/post_layer.gd`).

#### Bloom

Soft-light blend, threshold 0.9, wide and low. It passes through a lens-dirt map
(`assets/textures/fx/lens_dirt.png`, generated by `tools/py/fx_textures.py`) at strength 0.25 outdoors and
0.1 indoors, so smudges only show where something bright is in frame.

#### Depth of field

Off while exploring. Each kind of shot has its own setting, in `WorldEnv.DOF`:

| Kind | Used for | Far blur starts | Far transition | Amount | Near blur |
|---|---|---|---|---|---|
| `wide` | two-shots, minigames | focus + 1.6 m | 5 m | 0.06 | none |
| `ots` | over the shoulder | focus + 0.8 m | 3 m | 0.10 | from 0.6 × focus, so the near shoulder is soft |
| `single` | singles and close-ups | focus + 0.5 m | 2 m | 0.14 | none |
| `sit` | sit-down wides | focus + 6 m | 15 m | 0.05 | within 1.2 m, for foreground framing |
| `insert` | a poster, a phone, an object | focus + 0.25 m | 0.6 m | 0.16 | none |

When a shot does not name a kind, `dof_kind()` picks one from the lens: 22° or narrower is a single (an insert
if the subject is under a metre away), up to 27° a single, up to 31° over the shoulder, wider is `wide`.
Bokeh is circular. The opening uses a separate ramp (`set_wake_blur()`) that goes from fully soft to sharp as
Mano wakes up.

#### Post shader

In order:

1. Chromatic aberration at the frame edges, kept very light (0.0012).
2. Halation: a red-orange glow around bright edges that spills into the darker side, read from the blurred
   mip levels of the screen. Strength 0.05 at golden hour, 0.04 at night, 0.03 indoors.
3. Sun flare: a soft glow and three warm ghost discs on the line from the sun through the centre of the frame,
   with no streaks. It appears only outdoors, when the sun is in frame, when a ray to the sun hits no level
   collision, and when the frame is bright at the sun's position (which accounts for trees and people). It
   fades over 0.15 s.
4. Vignette: 0.22 while exploring, 0.34 in conversations and sit-downs, following the letterbox over 0.6 s.
5. Grain: a tiling Gaussian grain texture at about 1.4 px, moved to a new offset 24 times a second, weaker in
   highlights. The amount comes from the preset (0.022 to 0.028). The Film grain setting turns it off.

Conversations and cutscenes are letterboxed to 2.39:1 (`scripts/ui/hud.gd`); the bars slide in over 0.5 s.

The photographs in the credits go through a separate 2D shader, `scripts/fx/film.gdshader`, which makes them
look like prints from a disposable camera: lifted blacks, warm highlights, a light leak, grain.

### 1.5 Foliage and atmosphere

#### Fog

Depth fog with aerial perspective (0.55) softens distant buildings, and the sun scatters into it more
as it gets lower. Volumetric fog adds light shafts, with its density falling from 0.008 at golden hour to
0.005 at night.

#### Foliage

`LevelBinder` replaces the imported leaf and grass materials with
`scripts/fx/foliage.gdshader` at load time, copying their textures. Plane-tree leaves sway 3 cm at 0.8 Hz,
birch leaves 3.5 cm at 1.1 Hz, and grass bends 2.5 cm from the root at 1.2 Hz. The phase comes from world
position, so neighbouring clusters move together and a crown sways as a wave, with a slow gust on top. The
sway also runs in the shadow pass, so dappled shadows move with the leaves. Plants indoors keep their
imported material.

#### Falling leaves

One particle system (`scripts/fx/falling_leaves.gd`, `leaves.gdshader`,
`leaf_card.gdshader`) serves up to 32 tree crowns with 20 leaves each. A leaf falls at 0.4 to 1.2 m/s with a
pendulum swing or a tumble, drifts with the same south-westerly breeze as the foliage, lies on the ground for
three seconds and shrinks away. The ground height around each trunk is baked by raycasts when the level
loads, so leaves land on the road, a bench or a table instead of all at one height.

#### Sunbeams and dust

Two rooms get the low sun: Amphi 4 and the lobby of the Voltaire building
(`LevelBinder.SUN_ROOMS`, `scripts/fx/sun_room.gd`). Amphi 4 has a light fog volume so the sun draws shafts
across it, and both rooms have sparse dust motes. A mote is an additive speck lit only by direct light
(`scripts/fx/dust_mote.gdshader`), so the dust shows inside the beams and vanishes in shade. These effects
are visible only while the sun is up and the camera is in or within 3 m of the room.

### 1.6 Quality presets

`WorldEnv.apply_quality()` reads the Graphics setting. The default is `high`.

| | low | medium | high | ultra |
|---|---|---|---|---|
| SDFGI (global illumination) | off | off | on | on |
| Screen-space indirect light | off | on | on | on |
| Ambient occlusion | on | on | on | on |
| Volumetric fog | off | on | on | on |
| Screen-space reflections | off | off | off | on |
| Shadow atlas | 2048 | 4096 | 4096 | 4096 |
| 3D render scale | 0.50 | 0.58 | 0.62 | 0.77 |
| Depth-of-field quality | low | medium | high, jittered | high, jittered |

All presets upscale with FSR 2. On a HiDPI screen the 3D scene and the post shader render in their own
viewport at one pixel per screen point (`scripts/level/world_view.gd`) while text and UI are drawn at native
resolution, so a Retina display costs about the same as a standard one.

## 2. Interface

### 2.1 The notebook idea

Mano fell asleep over his algorithms notes, and the interface is that notebook. Menus, prompts and the HUD
are drawn as paper objects and pen marks, which keeps the screen consistent with the story and avoids the
rounded translucent panels of a generic game UI. The scripts named below are in `scripts/ui/`.

| Screen | Object | Code |
|---|---|---|
| Title | The logo as a die-cut sticker over the live scene, the menu written in marker on a ruled page taped bottom-left | `menus.gd`, `title_logo.gd`, `die_cut.gd`, `tape.gd` |
| Loading | The closed notebook on a desk; a pencil line ruled under its label shows progress; one tip on a sticky note | `notebook_cover.gd` |
| Pause | The closed notebook, with the menu written on the blank lines of its label | `notebook_cover.gd` |
| Chapter card | A fresh page: the date written top-right and ruled in red, the time in marker, the place in pen | `chapter_card.gd` |
| Objective | A strip torn from the notebook, top-left | `objective_strip.gd` |
| Toasts and control hints | Sticky notes with a ballpoint doodle | `sticky_note.gd`, `doodles.gd` |
| Area banner | The place name in marker on a strip of masking tape | `hud.gd` |
| Interaction prompt | A pen ring on the object, a leader line, a verb and a sketched key cap | `pen_prompt.gd` |
| Journal | The open notebook with tabs: today, people, film, ducks, moments, on the side | `menus.gd` |
| Map | A sheet of 5 mm grid paper taped onto a notebook page, the campus drawn in pencil | `map_view.gd` |
| Settings | A printed school form filled in by hand | `menus.gd` |
| Credits | A printed sheet from the title menu; at the end of the story, names rolling over the night scene | `menus.gd`, `credits_roll.gd` |
| Ending | The notebook's last page, "à suivre…" in red marker | `menus.gd` |
| Phone | A generic device with no brand, in the print font | `phone.gd` |

#### How it is drawn

Paper and pen marks are drawn procedurally. Paper is one polygon with a shader
(`scripts/fx/paper.gdshader`, wrapped by `paper_sheet.gd`) that draws the fibre and the ruling: Seyès ruling
with violet lines every 8 mm, three blue interlines and a red margin, or the 5 mm squares of a maths pad. The
ruling is anti-aliased over one screen pixel, so it stays sharp at any scale. Pen marks (underlines, loops,
key caps, doodles) are polylines with a seeded wobble (`pen_style.gd`, `doodles.gd`, `ink.gd`), so a mark is
identical on every run. Some marks "boil" by cycling three seeds at 8 frames a second. Handwriting writes
itself on at about 25 characters a second through `scripts/fx/write_on.gdshader`. Icons are ballpoint doodles;
the interface uses no emoji. The logo is lettered in-engine in the marker font with a fixed seed.

### 2.2 Fonts and their roles

`scripts/ui/ui_theme.gd` defines four voices as shared `FontVariation` resources. All four families are under
the SIL Open Font License (`assets/fonts/licenses/`).

| Voice | Font | Used for |
|---|---|---|
| Pen (Mano's ballpoint) | Mynerve | journal text, the objective, toasts, tips, the inner voice |
| Marker (Mano's felt-tip) | Shantell Sans, variable | headings, menu items, prompt verbs, banners, chapter times, dialogue choices |
| Print (the school) | Atkinson Hyperlegible Next | subtitles, speaker names, settings labels, credits, the phone |
| Code (the terminal) | Atkinson Hyperlegible Mono | code and verdicts in the moulinette minigame (find the bug in a failing exercise); minigame timers |

Shantell Sans has axes for informality and bounce, and the marker roles use them: titles are heavy and
bouncy, menu items steadier, and dialogue choices use a calmer variant with no bounce so that longer lines
stay easy to read. Atkinson Hyperlegible is designed for legibility, which is why it carries the subtitles.
Fonts are rasterised at the size they are shown, without signed distance fields, so they stay crisp on HiDPI
screens. When one voice lacks a glyph it falls back to another voice instead of a system font.

#### Palette

Colours are constants in `UITheme`. On paper: paper `#faf8f2`, ballpoint blue `#233e94` for
everything Mano writes (9.0:1 against the paper), red for dates and corrections, marker red `#d23a2c` for the
objective and focus marks, green for ticks, pencil grey for places not yet visited. Over the 3D scene, text is
film white `#f7f2e8` and always carries a dark ink outline and a soft shadow (`UITheme.over_scene()`),
because white over a pale sky measures only 1.22:1 on its own.

### 2.3 HUD rules

The scene has priority, so the HUD appears when something changes and then goes away.

- The objective strip shows only when the objective changes, or while the journal key is held. On a change
  the old line is struck through in red, the new one writes itself on, the strip holds for 6 s and lifts
  away.
- At most two toasts are on screen, each for about 3 s. A third one peels the oldest off.
- Control hints appear once per save and peel off as soon as the action is used, or after 16 s.
- Only the nearest interactable gets a prompt. Its key cap shows the live binding as the player's keyboard
  prints it (W on QWERTY, Z on AZERTY), or the pad button while a controller is in use
  (`UITheme.action_key()`).
- The objective marker is off by default. When on, it is a red pen target over the next place to go and an
  arrow at the screen edge when that place is off screen. It never shows a distance, and it fades out within
  4 m of the target.
- While the letterbox is in, the whole HUD is hidden.
- Buttons are words, and the focused one gets a red pen underline or loop.

The UI is laid out on a 1600 × 900 canvas that scales with the window, with a safe margin of 64 px at 1080p.

### 2.4 Subtitles

Subtitles are drawn by `scripts/story/dialogue.gd`. Like the prompt's leader lines, the unboxed style follows
Life is Strange.

- No box. Print font in film white with the ink outline and soft shadow.
- The speaker's name is inline, bold, in that speaker's colour, and shown again only when the speaker
  changes. The name is always written out, so colour is never the only cue.
- A line is about 40 characters wide and a card is two lines at most, a common guideline for game
  subtitles.
- Size M is 38 px at 1080p. The setting offers S (0.84 ×), M, L (1.2 ×) and XL (1.5 ×).
- In a conversation the line sits in the bottom letterbox bar. Elsewhere it sits just above the bottom edge
  over a soft gradient.
- Mano's inner voice and sound captions are in his pen, unnamed, and set 10 % larger because the handwriting
  font has a smaller x-height.
- A line appears whole with a 140 ms fade; a typewriter mode (52 characters a second) is optional. The
  continue mark appears after 0.3 s plus 40 ms per character, or as the recording ends on a voiced line.
- Barks (thoughts that do not stop play) show for 2.2 s plus 0.05 s per character and give way to any
  conversation.
- Choices are words in marker above the line. The highlighted one is circled in red; keys 1 to 4 pick
  directly.

### 2.5 Settings and accessibility

The settings form (`Menus.show_settings()`) applies changes at once and has a live subtitle preview. Defaults
are in `GameState.DEFAULT_SETTINGS`.

| Setting | Values | Default |
|---|---|---|
| Subtitle size | S, M, L, XL | M |
| Typewriter text | on / off | off |
| Readable fonts | on / off | off |
| Reduce motion | on / off | off |
| Objective marker | on / off | off |
| Film grain | on / off | on |
| Field of view | 44° to 70° | 52° |
| Graphics | low, medium, high, ultra | high |
| Master, music, effects and voice volume | 0 to 100 % each | 85, 60, 90, 100 % |
| Mouse and controller sensitivity, invert camera Y | | 1.0, 1.0, off |

*Readable fonts* swaps the two handwriting voices for the print face. The roles are shared resources, so
every label follows at once (`UITheme.set_readable()`). *Reduce motion* applies to the interface: marks stop
boiling, paper lands without overshoot or turn, and write-ons appear at once (`Ink.calm()`).

Key bindings use physical key codes, so the WASD layout works unchanged as ZQSD on an AZERTY keyboard.
Menus, dialogue choices, the journal and the phone can be driven from the keyboard or a controller.

## 3. Sound

Music, ambience, footsteps and one-shots go through one autoload, `Sfx` (`scripts/core/sfx.gd`). Files live in
`assets/audio/<group>/<name>.ogg`; a missing file is skipped silently. Every file's source, author, licence
and edits are listed in `assets/audio/CREDITS.md`.

### 3.1 Mix buses

Five buses feed the master: Music, SFX, Ambience, UI and Voice. The master has a compressor (threshold -10 dB,
ratio 3:1). The SFX bus has a reverb whose wet level follows the zone. The settings expose four sliders. Music
runs at 80 % of its slider. Ambience follows the effects slider at 70 % and UI sounds at 80 %, so the bed and
the interface always sit under the sounds of the action.

Three kinds of ducking are layered on top. Music drops to 45 % during conversations and chapter cards
(`duck_music()`), and a further 6 dB while a recorded voice line plays (`duck_voice()`). Ambience drops 6 dB
over 3 s during a sit-down, so the song takes the foreground (`duck_ambience()`).

### 3.2 Music

The soundtrack is six pieces by Kevin MacLeod (CC BY 4.0), cut to bar-aligned loops (the ending piece is kept
whole) and normalised to -18 LUFS by `tools/py/audio_music.py`. `data/songs.json` gives the titles shown on
Mano's phone and in the credits.

| Stem | Piece | Where it plays |
|---|---|---|
| `title` | "Morning" | title screen; two sit-downs |
| `explore` | "Almost Bliss" | the campus at `golden` and the first part of `late_gold`; one sit-down |
| `explore_dusk` | "Study And Relax" | the campus from the second part of `late_gold` to `late`; one sit-down |
| `under_party` | "Raving Energy" | the Under, at any hour |
| `tension` | "Sneaky Snitch" | minigames |
| `ending` | "Evening" | the cold open, one sit-down, the ending; the default song of the finale |

#### By place and hour

`Chapters.music_for(time, zone)` reads the `music` table of `data/chapters.json`. A
`zone:<id>` entry wins over the time preset, and an entry can be a list of conditions on story flags, which is
how `late_gold` changes track once a story flag is set. Place music plays at -10 dB unless `music_db` says
otherwise.

#### As a sit-down song

Each sit-down spot in `data/world.json` names a track. When Mano sits, the song rises
from silence over 3.5 s while the place's music fades over 3 s and the ambience ducks. The last sit-down
plays the song the player picked for the playlist in chapter 3.

#### As score

The story can hold one track over the place music (`set_score()` in `scripts/main.gd`). The
finale uses this to keep the chosen song playing through the credits.

#### In minigames

A minigame starts the `tension` track. Two of them, the sound search and the kebab counter,
silence it because their own sounds carry the scene.

#### Crossfade and resume

Two players crossfade between tracks. A track that fades out keeps its playback position and resumes from
there the next time it plays, so leaving a place and coming back does not restart the piece. The phone's
Music app lists the songs heard so far that evening.

### 3.3 Ambience

Each zone has a set of loops and a reverb amount (`Sfx.ZONES`). `main.gd` finds the zone under the player
from the level's zone volumes and calls `Sfx.set_zone()`, which fades the old loops out and the new ones in.
Loops shared by two zones keep playing across the boundary.

| Zone | Loops | Reverb |
|---|---|---|
| Street | city traffic, light wind | none |
| Courtyard | courtyard crowd, evening birds, light wind | none |
| Covered passage | city traffic, light wind | 0.2 |
| Amphi 4 | large room tone, ventilation | 0.55 |
| Voltaire ground floor | room tone, lobby murmur | 0.35 |
| Voltaire first floor | room tone, ventilation | 0.3 |
| Computer rooms SM14 and SM15 | computer fans, distant typing | 0.25 |
| Cafeteria | cafeteria chatter, fridge hum | 0.4 |
| The Under | basement tone | 0.5 |

The loops are built by `tools/py/audio_amb.py` from CC0 field recordings, layered and filtered so that
voices stay unintelligible, then crossfaded at the seam and levelled to between -22 and -28 LUFS.

### 3.4 Footsteps and one-shots

Every zone names its floor surface. The player script (`scripts/actors/player.gd`) counts distance walked and
triggers a step every 0.72 m when walking and every 1.05 m when jogging. `Sfx.footstep()` plays one of four
to six recorded sneaker steps for that surface (concrete, tile, carpet, wood, rubber, grass) as a positional
sound, with a small random pitch change, 5 dB louder when jogging.

One-shots (`Sfx.play()`, `play_at()` for positional sounds, `ui()` for the interface) cover the coffee
machine, table football, the phone buzz, the camera shutter, the map and the notebook. When a sound
has numbered variants, one is picked at random with slight pitch and level variation. Interface sounds are
short synthesised mallet tones (`tools/py/audio_sfx.py`), kept soft because they repeat often.

### 3.5 Voices

The friends are not voiced; their lines appear as subtitles only. The fictional characters (the teacher, staff
and other students) have synthetic text-to-speech voices: 56 lines across 12 speakers, credited with the other
AI-generated material in [PIPELINE.md](PIPELINE.md#ai-generated-material). `tools/py/voice_build.py` trims the
files, levels them to about -18 LUFS and encodes them.

`scripts/story/voice.gd` looks a recording up by a key derived from the speaker and the exact text of the
line. If a line is edited, its key no longer matches and the line plays silent until it is recorded again.
The manifest stores each line's length and a jaw-opening envelope at 30 Hz, which drives the speaker's lip
movement. A recorded line plays on the Voice bus while its subtitle is shown; skipping the subtitle stops it.
