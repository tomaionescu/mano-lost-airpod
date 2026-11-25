# Architecture

This document describes how the code of *Mano & the Lost AirPod* is organised: what runs at startup, how the story is
stored and played, how the game saves, and which tools check it. The game design is in [DESIGN.md](DESIGN.md), the
asset build in [PIPELINE.md](PIPELINE.md), the mapping of the real campus in [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md), the
look and sound in [ART_DIRECTION.md](ART_DIRECTION.md), and the current state of the project in
[STATUS.md](STATUS.md). How to run the game is in the [README](../README.md).

## 1. Overview

The project is a Godot 4.7 game written in GDScript. It uses the Forward+ renderer, Jolt physics at 60 ticks per
second with physics interpolation, and a 1600 × 900 base canvas stretched with `canvas_items` / `expand`.

Three decisions shape the rest of the code.

The scene tree is built in code. `scenes/main.tscn` is a single `Node3D` with `scripts/main.gd` attached; every other
node is created by scripts at startup. The only assets instantiated as scenes are the imported `.glb` files.

The story is data. Every line of dialogue is in text files under `dialogue/`, and chapters, to-dos, triggers, staging
and story positions are JSON under `data/`. The scripts in `scripts/story/` interpret that data and contain no
dialogue and no rule for a particular scene.

Story state is one dictionary. `GameState.flags` holds every story variable, and the objective, the staging of the
cast, the clock and the phone are computed from it. The save is therefore a plain JSON dump, and the headless tests
can play the whole story without loading the level.

| Path | Contents |
|---|---|
| `scripts/main.gd` | The game root: loading, game modes, chapter flow, conversations and their camera, sit-downs, the finale |
| `scripts/core/` | The two autoloads: `GameState` (input, settings, flags, saves) and `Sfx` (audio) |
| `scripts/story/` | Dialogue parser and runner, conditions, commands, chapters, world data, phone chat, overheard talk, voice lines |
| `scripts/actors/` | Player, NPCs, the character rig and materials, interactables, the collectible ducks |
| `scripts/camera/`, `scripts/level/` | The camera; level marker binding, lighting and time of day, the HiDPI 3D view |
| `scripts/ui/` | HUD, menus, phone, chapter card, credits, and the paper and pen drawing primitives |
| `scripts/minigames/`, `scripts/fx/` | Seven minigames, one script each; shaders and the scripts that drive them |
| `scripts/dev/`, `scenes/dev/` | The autotest driver and the dev check and viewer scenes |
| `dialogue/`, `data/` | `.dlg` dialogue files and `chat.json`; `chapters.json`, `world.json`, `flags.json` and smaller tables |
| `tests/` | The headless test runner, its tests and fixtures |
| `tools/` | Blender and Python build scripts ([PIPELINE.md](PIPELINE.md)) and the `tools/dev/` helpers |

## 2. Runtime structure

### 2.1 Startup

`main.gd` creates the long-lived nodes in `_ready()`, shows the loading screen and requests the campus and the cast's
models with `ResourceLoader.load_threaded_request`. `_process` polls the loads and reports progress. When all are in,
`_build_world()` instantiates the level, hands it to `LevelBinder`, creates the player and the cast, and shows the
title.

```
Main (Node3D, scripts/main.gd)
├─ WorldEnv        sky, sun, Environment, conversation fill light; owns the WorldView on HiDPI screens
├─ post layer      CanvasLayer with the lens finish (scripts/fx/post_layer.gd)
├─ HUD             CanvasLayer; Dialogue draws its subtitles and choices inside it
├─ Dialogue        Node; plays dialogue step queues
├─ Menus           CanvasLayer; title, pause, settings, journal, map, wardrobe, photo mode, ending
├─ Phone           CanvasLayer; lock-screen card and the phone held in hand
├─ CameraRig       Node3D holding the gameplay Camera3D
├─ campus          the instantiated assets/levels/campus.glb
├─ Mano            Player (CharacterBody3D) with a CharacterRig
├─ NPC_<id> ...    one NPC node per cast member, plus the background crowd
├─ Ducks, Overheard
└─ (transient)     a minigame node, CreditsRoll during the credits, the autotest driver in dev runs

Autoloads: GameState, Sfx
```

`Story` is a `RefCounted` object owned by `main.gd`. `DialogueData`, `Conditions`, `Chapters`, `WorldData`, `Chat`,
`Film`, `Collectibles` and `VoiceLines` are static classes that read their data once and compute from
`GameState.flags`. If `campus.glb` is missing, or the game is started with `-- sandbox`, `SandboxLevel` builds a small
stand-in level with the same marker names.

### 2.2 Game modes

`main.gd` keeps the current mode in a string, `mode`. The mode decides who reads input and what `_process` updates.

| Mode | Entered by | What runs |
|---|---|---|
| `loading` | startup | Polls the threaded loads |
| `title` | `show_title()` | Title menu; the camera drifts round Mano asleep in Amphi 4 |
| `cutscene` | chapter cards, the cold open, the dream and wake-up | Player frozen; scripted camera, fades and timers |
| `play` | `resume()` | Free movement; clock, triggers, interaction prompt, idle beats, zone, waypoint, autosave |
| `dialogue` | `say()` / `talk_to()` | `Dialogue` owns input; `main.gd` frames each line |
| `sit` | `begin_sit()` | A sit-down: authored cameras, a song, one thought; any input stands Mano up |
| `minigame` | `start_minigame()` | The minigame node owns input and calls back with its result |
| `pause`, `journal`, `map`, `wardrobe`, `photo`, `phone` | `enter_menu(name)` | A menu or the phone over a frozen scene |
| `credits` | `roll_credits()` | The credits roll, then the post-credits scene |
| `ending` | `show_ending()` / `show_recap()` | The last page; the save is cleared |

In `play`, `_process` advances the story clock, polls the chapter's triggers every 0.25 s, passes the nearest
interactable to the HUD prompt, updates the zone (ambience, music, footstep surface, area banner) and the waypoint,
and autosaves every 30 s. `_unhandled_input` handles keys only in `play` and in `sit`. The journal key opens the
journal on a tap and shows the objective while held. Losing window focus during play opens the pause menu.

## 3. The story layer

| File | Role |
|---|---|
| `dialogue_data.gd` | Parses `dialogue/*.dlg` into cues and compiles a cue into the steps `Dialogue` plays |
| `dialogue.gd` | Plays a step queue: subtitles, choices, voice playback, barks |
| `story.gd` | The facade `main.gd` calls (`talk`, `use`, `objective`, `target`) and the runner compiled steps act on |
| `story_commands.gd` | The `$` commands, with one specification table used by the dispatcher and the validator |
| `conditions.gd` | Evaluates condition expressions against the flags |
| `chapters.gd`, `world_data.gd` | Read `data/chapters.json` (to-dos, staging, clock, music, triggers) and `data/world.json` |
| `chat.gd`, `overheard.gd`, `voice.gd`, `film.gd`, `collectibles.gd` | Phone messages, overheard talk, recorded lines, the photo film, collectibles |
| `cast_defs.gd` | The cast: display names, subtitle colours, models, default behaviour |

### 3.1 The `.dlg` format

A `.dlg` file is a list of cues. A cue is an entry point with an id and a body of lines, choices, branches and
commands. The syntax is a small subset of Dialogue Manager 4's. `DialogueData.load_all()` reads every file in
`dialogue/` in name order, sixteen files and a little over 200 cues. Parse errors are collected with file and line
number for the validator and do not stop the game.

| Syntax | Meaning |
|---|---|
| `~ cue.id` | Starts a cue. Ids are lowercase `[a-z0-9_]` parts joined by dots |
| `who: text` | A line. `who` is a cast id, `mano`, `think` (Mano's inner voice), `nar` (stage sounds such as `*clunk*`) or `crowd` |
| `who: [#smile] text` | A line with an expression: `smile`, `grin`, `shock`, `annoyed`, `sad`, `smirk`, `tired`, `neutral` |
| `... [if expr]` | At the end of a line or a response: shown only when the condition holds |
| `... [slot]` | At the end of a line or a response: a tag with no runtime effect; the validator lists tagged lines in `tools/out/slots.txt` |
| `- label` | A response to the line above it, with its block indented one level under it |
| `% who: text` | A random group: of consecutive `%` lines, one is picked |
| `if expr` / `elif expr` / `else` | A branch, evaluated when the cue reaches it |
| `$ name args key=value` | A command (section 3.4) |
| `=> cue`, `=>< cue`, `=> END` | Jump to a cue, call a cue and come back, end the dialogue |
| `{{flag}}`, `{{word.key}}`, `{{song.flag}}` | Filled in when the card shows: a flag, an entry of `data/words.json`, the title of the song a flag names |
| `# ...` | A comment |

Indentation is tabs; four spaces count as one level. Command arguments are typed when parsed: `"quoted"` is a string,
`true` and `false` are booleans, digits are numbers, any other bare word is a string, and `key=value` is a keyword
argument. A lone `=` is skipped, so `$ set choco = "pac"` and `$ set choco "pac"` are the same.

One cue as it is in `dialogue/c2.dlg`:

```
~ c2.partner
karim: [#grin] Bring a teammate if you want. I play both rods. BDE tradition.
think: Two against one. Who's on my side?
- Ian [if choco != "choco"]
	ian: [#grin] Pain au chocolat gang, assemble.
	$ set foot_partner = "ian"
- Silvia [if choco != "pac"]
	silvia: [#grin] Chocolatine gang. Finally, a sport.
	$ set foot_partner = "silvia"
- Joaquin [if joaquin_met]
	joaquin: [#smile] Okay. I have notes. [slot]
	$ set foot_partner = "joaquin"
- Alone
	karim: [#smirk] Respect. Bad idea, but respect.
	$ set foot_partner = "solo"
$ minigame babyfoot stand_at=babyfootSpot win=c2.foot_win lose=c2.foot_lose with=karim
```

Cue ids follow a convention the code relies on. `talk.<npc>` plays when Mano talks to that character and `use.<spot>`
when he uses a spot, with `talk._default`, `talk.crowd` and `use._default` as fallbacks. `c<n>.<beat>` are a chapter's
scenes, `sit.<id>` a sit-down's thought, `over.<id>` an overheard exchange, and `bridge.end` is what `$ chapter n`
plays when chapter `n` is not in the data.

### 3.2 How a cue runs

`DialogueData.steps(cue, runner)` compiles a cue's body into an array of steps. `Dialogue` understands three kinds:

```
["who", "text"]  or  ["who", "text", "expression"]        a card
{"who": ..., "t": ..., "e": ..., "ask": [[label, steps]]}  a card with choices
Callable                                                    runs at once, shows nothing
```

Plain lines compile to cards. Whatever is decided at run time (a branch, a random group, a conditional line, a jump,
a command, a line with `{{...}}`) compiles to a `Callable` that acts on the runner when it is reached. The runner
interface is `push(steps)`, `jump(steps)`, `end_now()`, `pause(seconds)`, `wait_phone()` and `command(node)`. `Story`
implements it against the real `Dialogue` node, `Story.BarkRunner` with no screen, and `tests/support.gd` headless,
so the same compiled steps run in the game and in the tests.

`Dialogue` pops steps from its queue, runs Callables immediately, and stops on a card until the player confirms or
picks a response, whose steps go to the front of the queue. Each card emits `line_shown`; `main.gd` uses it to set the
speaker's expression and lip movement, turn heads and choose the camera shot. `$ say`, `$ chapter` and `$ sit` do not
act at once: they register a callback with `Story.after()` that runs when the dialogue has finished, so a chapter
card never cuts into a conversation.

A cue made only of `think` lines and stage sounds, with no choice and only side-effect commands, is think-only.
Look-at spots and `bark` triggers play such cues as barks: the lines show over the game while Mano keeps walking.

### 3.3 Conditions and flags

Conditions appear in `.dlg` files and in the `when` and `done` fields of `chapters.json` and `world.json`.
`Conditions.eval(text)` evaluates them with Godot's `Expression` class. Flag names are read as variables. The syntax
is `and`, `or`, `not`, the comparison operators, `in`, numbers, double-quoted strings, `true`, `false` and arrays,
plus three helpers: `clock_after("18:50")`, `clock_before("18:50")` and `night()`. An example:
`foot_partner == "ian" and foot_losses >= 2`. Every identifier is renamed to `f_<name>` before parsing, so a flag may
share a name with a built-in function (`sign` does). An expression that does not parse evaluates to false and logs an
error once.

Every flag is declared in `data/flags.json` with a default and a one-line description. `GameState.reset_flags()`
builds the dictionary from that file, and an unset flag reads as its default. `Story.setf()` warns when an undeclared
flag is set, and the validator fails when story data reads or writes one.

### 3.4 Commands

`StoryCommands.SPEC` lists every command with its positional arguments, their types and its keyword arguments. Running
a command calls the method `_c_<name>`. The validator checks every `$` line in the data against the same table, so a
new command is one `SPEC` entry and one method.

| Group | Commands |
|---|---|
| Flags | `set`, `add`, `coin`, `clue` |
| Feedback | `toast`, `sfx`, `hint`, `banner`, `caption` |
| Flow | `say`, `chapter`, `minigame`, `wait`, `sit`, `ending`, `credits`, `recap` |
| Time and light | `clock`, `time`, `lamps` |
| Staging | `place`, `stage`, `follow`, `unfollow` |
| Camera | `shot`, `freeze`, `photo` |
| Phone and music | `phone`, `song`, `score` |
| The AirPods | `give_airpod`, `drop_airpod`, `airpods` |
| Side story | `duck_hint` |

`$ minigame` and `$ credits` end their cue; a minigame's result plays the cue named by `win=` or `lose=`. Commands
that take time (`$ wait`, `$ song`, `$ photo`, `$ caption`, `$ phone`) hold the dialogue until they are done.

### 3.5 Chapters

`data/chapters.json` declares six chapters, 0 (the cold open) to 5 ([DESIGN.md](DESIGN.md) §3.5), and sets the first
chapter, the rate of the story clock and the music for each time of day. A chapter entry has these fields:

| Field | Meaning |
|---|---|
| `n`, `id`, `title`, `card` | Number, id and what the chapter card writes (time, date, place, chapter name) |
| `clock`, `clock_end`, `clock_holds` | Where the story clock starts, the latest it may tick to, and holds that keep it from passing a timed beat |
| `time`, `times` | The light preset the chapter opens in, and the presets `$ time` may switch to |
| `opening` | `cold_open` or `wake` for the two chapters with a scripted opening |
| `start_cue`, `start_with` | The cue played after the card, and the character it is a conversation with |
| `start_at`, `card_at` | Where Mano starts, and where he is moved under the card |
| `started` | A condition that holds once the start cue has played through |
| `start_flags` | The flags a direct start of this chapter assumes when it has no snapshot |
| `stage` | Where each character is during the chapter |
| `triggers`, `todos` | Sections 3.6 and 3.7 |
| `ends_with` | The flag the chapter's last scene sets |
| `group_shot` | A `world.json` shot used when someone far from the conversation speaks |

A chapter ends when a cue runs `$ chapter n`. `main.begin_chapter(n)` fades to black, moves Mano to `card_at`, sets
`flags.chapter`, clears any `$ stage` overrides, sets the clock, applies the light preset, restages the cast, shows the
card, writes the chapter snapshot and the save, fades back in and plays the start cue. If a save is loaded in a
chapter whose `started` condition does not hold yet, the start cue plays again; its commands are safe to run twice.

Staging decides where every character is. `Chapters.stage_of(id)` resolves it in order: a `$ stage` override stored
in `flags.stage_over`, then the chapter's `stage` entry, which is one entry (`"ian": {"point": "under_ian", "chat":
true}`) or a list whose first entry with a true `when` applies (`"sleeper": [{"when": "sup_awake", "hide": true}]`).
`main.restage(id)` applies the result: hide, place at a `world.json` point, walk there, walk out of view first, go
home, or follow Mano. Staging is re-read at the end of every conversation and minigame, so a `when` can move someone
between two scenes. Characters marked `staged_only` in `CastDefs` (Ishita, Cristina, Joaquin) are on campus only where
a chapter stages them.

The story clock is `flags.clock`, in minutes after midnight, counting on past midnight. It advances by `clock_rate`
game minutes per real minute during play and sit-downs, never past `clock_end` or an active hold, and `$ clock` only
moves it forward. The light is a separate value, `flags.time`, one of the six presets in `WorldEnv.TIMES`; it changes
only under a card or a fade. `Chapters.music_for(preset, zone)` picks the track from the `music` table, where
`zone:<id>` entries take priority over the preset's.

### 3.6 Triggers

A trigger plays a cue when Mano reaches a place under a condition.

```json
{"id": "joaquin_under", "near": "npc:joaquin", "radius": 5.0, "zone": "under",
 "when": "not joaquin_met and not karim", "cue": "c2.under", "with": "joaquin", "main": true, "once": true}
```

`near` is a reference (`npc:`, `spot:`, `point:` or `anchor:`), `zone` a level zone id, `after` a number of seconds
into the chapter. The first trigger that is due plays, and its id goes into `flags.triggers_fired`. A trigger with
`"bark": true` plays a think-only cue without stopping play. Otherwise the cue is a conversation with the character in
`with`: Mano is placed at talking distance first, or everyone is moved to the points listed in `place`, so the scene
is filmed where it was framed. `main` marks the triggers on the critical path, which the tests visit.

### 3.7 To-dos, the objective and the waypoint

```json
{"id": "find_karim", "main": true, "kind": "go", "text": "Karim has my AirPod. Find him in the Under.",
 "when": "not karim", "done": "karim", "target": "npc:karim", "label": "Karim"}
```

The main to-do is the first one with `main: true` whose `when` holds and whose `done` does not. When the chapter has
none left and its `ends_with` flag is set, the next chapter's is shown. Up to two optional to-dos are active at a
time, and one marked `carry` stays open in later chapters. A to-do can list several `targets` with `unless` conditions
and a `fallback`; the nearest valid one is used.

`GameState.flags_changed` calls `main.on_flags_changed()`, which records finished to-dos and gives the HUD the new
objective text. The waypoint is off by default. When it is on and the target is in another zone, a breadth-first
search over the level's `PORTAL_` markers aims it at the next door or staircase on the way.

### 3.8 Phone, overheard talk and voice lines

`dialogue/chat.json` holds the phone's threads, messages and reply options. Messages belong to delivery batches;
`$ phone flood <batch>` delivers a batch and every earlier one. What the phone shows is computed by `Chat` from flags:
batches delivered, messages read per thread, replies sent and the tone of each reply. `Overheard` plays short
exchanges between two characters near Mano as small text in a corner of the screen, without taking control; one
starts when Mano is within its radius with a line of sight to the pair.

`VoiceLines` looks up a recording for a card. The key is the speaker id plus the first ten hex digits of the SHA-1 of
`"<speaker>|<exact text>"`; `assets/audio/voice/manifest.json` maps keys to files, durations and a jaw-opening
envelope at 30 Hz that drives lip sync. Only the fictional campus characters have recordings
([PIPELINE.md](PIPELINE.md) says how they are made). A card with no entry is silent.

## 4. World data

Positions come from two places. The level file carries markers placed in Blender ([PIPELINE.md](PIPELINE.md),
[CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md)), which `LevelBinder.bind()` collects by name prefix:

| Marker | Becomes |
|---|---|
| `SPAWN_player` | The player's spawn |
| `NPC_<id>` | A cast member's home position, or a background student (`NPC_crowd*`) |
| `SPOT_<id>`, `ANCHOR_<id>`, `DUCK_<id>` | An interactable spot; a named transform such as a minigame seat; a collectible duck |
| `ZONE_<id>` | A box volume: place name, footstep surface, ambience |
| `PATH_<name>_<i>` | A walking path for a background student |
| `PORTAL_<a>__<b>_<i>` | Door and stair points between two zones, used by the waypoint |
| `LIGHT_`, `PROP_`, `DECAL_`, `CAM_` | Lights, prop instances, decals and camera transforms created at load |

`data/world.json` adds what the story needs on top of that, so story work does not require a level rebuild. Positions
are in game metres with Y up and +X along rue Pasteur; yaw is in degrees, 0 facing +Z. A level spot wins over a
`world.json` spot of the same id unless the entry sets `"override": true`.

| Section | Entries | Contents |
|---|---|---|
| `points` | 52 | Named positions for staging, starts and triggers, with an optional `via` path for walking there |
| `spots` | 74 | Extra look-at and readable spots: position, label, kind, condition, optional camera insert or drawn note |
| `spot_when`, `npc_when`, `zone_*` | | Conditions for level spots and for characters who come and go; place names for the area banner |
| `sits` | 6 | Sit-downs: seat, chapter, clock window, cameras, song, journal line |
| `shots` | 15 | Framed cameras for `$ shot`, absolute or relative to Mano |
| `photos`, `ducks` | 10, 12 | Photo spots (where to stand, what to frame); each duck's chapter and hint, and a position for the four with no level marker |
| `overheard` | 12 | Overheard exchanges: two characters, a cue, a condition |
| `finder_places`, `lights`, `cam_occluders` | 2, 2, 1 | The finder app's pins; story lights; boxes only camera checks see |

Physics uses four layers:

| Layer | Used by |
|---|---|
| 1 | Level and prop collision |
| 2 | The player capsule |
| 4 | Bodies of standing NPCs; off while a character follows Mano |
| 16 | Camera-only volumes (monitors, chair backs, `cam_occluders`): tested by shot selection, never by movement |

## 5. The save system

`GameState` owns three kinds of JSON file. The name `save_v1.json` is historical; the format version is the `version`
field inside, currently 2.

| File | Written |
|---|---|
| `save_v1.json` | Every 30 s of play, at the end of every conversation, under each chapter card, and when the window is closed during play |
| `save_ch<n>.json` | Under chapter `n`'s card: the state chapter select starts from |
| `settings_v1.json` | Whenever a setting changes |

```json
{"version": 2, "chapter": 2,
 "flags": {"clock": 1115, "time": "late_gold", "coins": 2, "karim": true},
 "outfit": "street", "ducks": ["amphi"], "play_time": 912.4,
 "pos": [1.5, -3.6, 42.0], "yaw": 1.2, "saved_at": "2026-10-15T18:35:02"}
```

`flags` is the whole story state, including the clock, the light preset and the phone's messages. Staging, objectives
and music are not saved; they are recomputed from the flags on load.

Writes are atomic. `_write_atomic()` writes `<file>.tmp`, renames the current file to `<file>.bak`, then renames the
`.tmp` into place, so a crash at any step leaves the previous save or its backup readable. `_read_save_file()` tries
the main file, then the `.bak`, and accepts a file only if it parses and has a `flags` dictionary.

Every read goes through `migrate()`. A version 1 save, from the earlier build that had no chapters, is brought to version 2:
nested `got` entries become flat `got_<id>` flags, the chapter is derived from progress, flags that version 2 sets in
the same scenes are filled in, and the light preset is moved to one the chapter allows. Unknown keys are kept. JSON
has no integer type, so `coerce_flags()` then restores integers and booleans from the defaults in `flags.json`.

Saving starts once the wake-up conversation is over, and the save is deleted when the story reaches its last page.
Chapter select lists the chapters that have a snapshot. Replaying one applies its snapshot, which keeps the choices
made earlier that night, and merges in every collectible found so far (`Collectibles.best_known`).

Tests and automated runs never use the player's files. `GameState.run_kind()` inspects the command line before
anything is read:

| Run | Save and settings | Photos |
|---|---|---|
| Normal | `user://save_v1.json`, `user://settings_v1.json` | `~/Pictures/Mano & the lost AirPod` |
| `autotest[=plan]` | `user://*.autotest.json` | `user://photos.autotest/` |
| A scene under `res://tests/`, `res://scenes/dev/` or `res://tools/`, or a `-s` script | `res://tests/out/*.test.json` | `res://tests/out/photos.test/` |

## 6. Characters at runtime

Each character is one `.glb` under `assets/characters/` ([PIPELINE.md](PIPELINE.md)). `CharacterRig` wraps it. It finds
the `Skeleton3D` and the `AnimationPlayer` and builds an `AnimationTree` in code: a one-dimensional blend space for
locomotion (idle, walk, jog and run, placed at each body's own stride speeds, which the model carries as metadata so
feet do not slide), a transition node between locomotion, sitting and talking, and a one-shot node on top for
gestures. Two `LookAtModifier3D` nodes on the neck and the head turn the character toward a point.

The face is driven through blend shapes with ARKit-style names: a random blink timer, a jaw that follows the
recorded line's envelope or a random syllable rhythm, and expressions as named sets of targets that ease in and out.

`CharacterMaterials.apply()` replaces the imported glTF materials with game materials. It reads the kind of each
surface from the mesh and material names (`<id>_<kind>_<asset>`: skin, cloth, hair, eye, cornea, teeth, glasses and
others) and assigns a custom shader for hair, eyes and glasses or a tuned `StandardMaterial3D` for the rest. A
per-person table, `FINISH`, sets shader parameters the model file does not carry, such as iris colour or how matte a
pair of frames is. Background students get cheaper hair and a shorter visibility range than the named cast.

`NPC` covers named characters and background students. `CastDefs.npc_defs()` gives each one an id, a display name, a
subtitle colour, a model and default behaviour; the level's `NPC_<id>` marker supplies the position. An NPC idles,
sits, types or walks a path, glances at Mano when he passes and turns to him when spoken to. A follower walks beside
and slightly behind Mano on a trail of his recent positions, has no collision body while following, and is moved back
onto the trail if it falls more than 8 m behind. A character that is off stage is hidden and stops processing.

`Player` is a `CharacterBody3D` with camera-relative movement, a jog, and footsteps by zone surface.
`find_interactable()` scores the interactables in range by distance and by how directly Mano faces them, so the prompt
goes to what he is looking at. Mano has three outfits, each a separate model.

## 7. Camera

`CameraRig` has two states. The follow camera sits behind Mano's shoulder with separate horizontal and vertical
damping, pulls in with a sphere sweep when geometry is in the way, recentres after two seconds without camera input
while he walks, and adds a slight handheld sway. A scripted shot is a `{from, look, fov, focus}` set by `set_shot()`,
reached by a cut or a blend, optionally with a slow drift or orbit. `clear_shot()` blends back.

Conversations are filmed by `main.gd`, not authored shot by shot ([DESIGN.md](DESIGN.md) §4.5). When one starts,
`_pick_side()` chooses the side of the line between the two heads that has more room, and the camera stays on it. For
each line, `_shot_for()` builds candidate positions, over the listener's shoulder and in a ring around the speaker's
face, and `_view_score()` rates them: views inside geometry or blocked by the level, a camera occluder or another
character are rejected, and frontal views are preferred. Narration and staged openings use a two-shot from the side.

Authored cameras exist where a scene needs one: `$ shot <name>` uses a `world.json` shot, a readable spot can define a
narrow insert, and each sit-down has two or three cameras played in sequence ([DESIGN.md](DESIGN.md) §4.1). Each shot
selects a depth-of-field profile in `WorldEnv.DOF` by kind (`wide`, `ots`, `single`, `sit`, `insert`). In conversations
and sit-downs an unshadowed fill light near the lens keeps faces readable; it is off at golden hour.

## 8. The UI layer

All UI is built in code from `Control` nodes on `CanvasLayer`s and drawn as paper, tape and pen marks. The visual
rules are in [ART_DIRECTION.md](ART_DIRECTION.md). `UITheme` defines the palette and four font roles used everywhere:
pen (Mano's handwriting), marker (headings and choices), print (subtitles, settings, credits) and code (the terminal
minigame).

| Class | Role |
|---|---|
| `HUD` | Objective strip, toasts, one-off control hints, interaction prompt, optional waypoint, area banner, letterbox, fade, captions |
| `Dialogue` | Subtitles, choices and barks, drawn inside the HUD |
| `Menus` | Loading, title, chapter select, pause, settings, credits sheet, journal (six tabs), map, wardrobe, photo mode, ending and recap |
| `MapView` | The campus map, drawn from `assets/levels/campus_plan.json`; its static parts render once into a `SubViewport` |
| `Phone` | Lock-screen card with message previews; the phone in hand with Messages, Find and Music |
| `ChapterCard`, `CreditsRoll`, `ObjectiveStrip`, `StickyNote`, `PenPrompt`, `PenWaypoint` | The chapter card, the credits roll and the HUD's parts |
| `PaperSheet`, `Tape`, `NotebookCover`, `Ink`, `PenStyle`, `Doodles`, `DieCut`, `TitleLogo` | Drawing primitives: ruled paper, tape, handwriting that writes itself on, hand-drawn `StyleBox`es, vector doodle icons, sticker outlines |

`GameState` registers the input actions in code from physical key codes, so WASD is ZQSD on an AZERTY keyboard, and
adds gamepad bindings. Settings cover sensitivity and inverted Y, four volumes, graphics quality, field of view, the
objective marker, subtitle size, film grain, a print font in place of the handwriting, typewriter text and reduced
motion.

## 9. Audio

`Sfx` creates five buses at startup, all sent to Master: Music, SFX, Ambience, UI and Voice. Master has a compressor
and SFX a reverb whose wet level follows the zone. Sounds are looked up by convention,
`assets/audio/<group>/<stem>[_N].ogg` with the groups `music`, `amb`, `sfx` and `footsteps`; numbered variants are
wrapped in an `AudioStreamRandomizer`, and a missing file is skipped without an error.

Music uses two players and crossfades between them. A track that fades out keeps its playback position and resumes
from it, so the exploration track continues after a minigame and a sit-down's song continues at the next sit-down.
Music ducks during conversations and chapter cards, and further under a recorded line. `set_zone()` crossfades the
ambience loops listed for the zone in `Sfx.ZONES`. Footsteps are positional one-shots chosen by the zone's surface.
`main.gd` decides what plays: the track for the preset and zone, a `$ score` track, or a sit-down's song.

## 10. Rendering and quality presets

`WorldEnv` owns the `Environment`, the sun and the sky. `apply_time()` moves between six presets (`golden`,
`late_gold`, `last_light`, `blue`, `night`, `late`), each a set of differences from shared defaults: sun and moon
position, sky blend, ambient, fog, exposure, colour grade, lamp levels and window emission. `LevelBinder` sorts the
level's lights into lamp groups so a preset can dim street lamps, string lights and classroom panels separately.

The quality setting selects one of four presets in `WorldEnv.apply_quality()`:

| | low | medium | high | ultra |
|---|---|---|---|---|
| SDFGI | off | off | on | on |
| SSIL, volumetric fog | off | on | on | on |
| Screen-space reflections | off | off | off | on |
| Directional shadow atlas | 2048 | 4096 | 4096 | 4096 |
| 3D resolution scale (FSR2) | 0.50 | 0.58 | 0.62 | 0.77 |
| Depth-of-field quality | low | medium | high | high |

SSAO is on at every level and skin subsurface scattering is off at `low`. On a HiDPI screen, `WorldView` renders the
3D world into a `SubViewport` at one pixel per screen point and draws it under the UI, so text is native resolution
while the 3D costs what it would on a standard display. The lens finish (`post_layer.gd`: vignette, grain, halation,
sun flare) is a full-screen shader drawn under the UI.

## 11. Minigames

A minigame is one script in `scripts/minigames/`, started by `$ minigame <name>`. `main.start_minigame()` switches to
`minigame` mode, moves Mano to the anchor named by `sit_at` or `stand_at`, instantiates the script and calls
`setup(game, opts, done)`. The minigame builds its own UI or 3D scene, handles its own input and calls `done(result)`;
the story then plays the `win` or `lose` cue. There are seven: `moulinette` (find the buggy line in a terminal),
`babyfoot` (table football, alone or with a partner), `coffee` (shake the machine loose), `lostfound` (inspect the
box), `kebab` (memorise the orders in `data/kebab.json`), `findmy` (find the AirPod by sound) and `soleil` (a
red-light, green-light sneak across a computer room).

## 12. Dev tooling

### 12.1 Autotest plans

Starting the game with `-- autotest[=plan]` adds `scripts/dev/autotest.gd` to the tree. It drives the real game by
calling into `main.gd` and injecting input, logs `[autotest]` lines and saves screenshots to `res://shots/`, as in
`Godot --path . -- autotest=convo ids=ishita,joaquin chapter=2 shots=convo`. There are more than forty plans:

| Plan | What it plays |
|---|---|
| `basic` (default) | Title, new game, the opening, a short walk, the journal, the map, the pause menu |
| `story` | The whole story from the cold open to the recap on the critical path; `chapter=<n>` starts later |
| `chapters`, `chapter_select`, `cold_open`, `opening`, `credits` | Every chapter started from the title; chapter select; the scripted opening and ending |
| `convo`, `choices`, `voice` | Conversations with given characters, choices through real key events, recorded lines |
| `look`, `looks`, `place`, `shots`, `sit` | Look-at spots, `world.json` points, framed shots and sit-downs, each visited and photographed |
| `phone`, `hud`, `journal`, `map`, `ducks`, `photos`, `overheard`, `side`, `idle` | The phone and UI screens; collectibles, overheard talk, side stories, idle behaviour |
| `moulinette`, `babyfoot`, `coffee`, `lostfound`, `kebab`, `findmy`, `soleil` | Each minigame played with real input |
| `perf`, `perfwalk`, `perfab`, `perfvar`, `perflens` | Frame-time measurements per quality preset and along fixed walks |

Common options are `shots=<dir>`, `time=<preset>`, `chapter=<n>` and `ids=a,b`. `lens=v1` swaps in a simpler post
shader and turns off lens dirt, foliage sway, falling leaves and the sun-room fog, to measure what they cost.

### 12.2 Dev scenes

Each scene in `scenes/dev/` attaches one script from `scripts/dev/`. The check scenes exit with code 1 on a failure.

| Scene | Purpose |
|---|---|
| `line_check` | Headless. Lays out every subtitle card in the real font and fails if one does not fit two lines |
| `hud_check` | Headless. HUD behaviour without the level: toasts, objective changes, hints, prompt, waypoint default |
| `ui_check` | Headless. The notebook screens: credits names, chapter card timing, title lettering, settings form layout |
| `marker_list`, `voice_lines`, `v1_ladder` | Write data files: the level's markers for the headless tests, every card with its voice key, the objective fixture of `test_port.gd` |
| `char_viewer`, `hair_still_viewer`, `hair_dump_viewer`, `glass_probe` | Render a character under game lighting; the probe overrides material parameters from the command line |
| `anim_preview`, `campus_preview` | Contact sheets of every animation clip; views of the level with a collision probe under the markers |

### 12.3 The test runner

`Godot --headless --path . res://tests/test_runner.tscn [-- only=validate,quest]` runs each test script's
`run(report)`, prints one summary line per test and exits with code 1 on any failure. The tests need no window and do
not load the level.

| Test | Covers |
|---|---|
| `compile_check.gd` | Every script under `scripts/` and `tests/` loads and compiles, autoloads and class names included |
| `validate_dialogue.gd` | Static validation of all story data: parse errors, duplicate or missing cues, unknown speakers and expressions, undeclared flags, conditions that do not parse, commands and arguments against `SPEC`, references that do not resolve, card length, and the consistency of `chapters.json`, `world.json`, `chat.json` and the smaller tables |
| `test_quest.gd` | A headless walker that plays the story from data to the ending: start cue, due main triggers, then the main to-do's target. A second pass takes every answer of every question and loses each minigame once. Also checks that the main to-do always resolves to a target and that the side stories reach their ends |
| `test_saves.gd` | Save round trip, type coercion, backup fallback after a truncated or missing file, version 1 migration, chapter snapshots, and that test runs only write under `res://tests/out/` |
| `test_port.gd` | Regression against fixtures captured from the first version of the story, when lines were in code: each of its cards is still in the data or listed as rewritten, each recording still has its card, and the data gives the same objective in every state |
| `test_map.gd` | The map's plan file is complete and no two map labels overlap in the busiest layout |

`tests/support.gd` provides a `Report` that counts checks, `HeadlessDialogue`, which plays compiled steps and answers
questions through a callback, and `FakeGame`, a stand-in for `main.gd` that implements the calls `Story` and
`StoryCommands` make and resolves positions from `tests/fixtures/markers.json` and `world.json`.

### 12.4 `tools/dev/godot.py`

`python3 tools/dev/godot.py [--timeout S] -- <godot args>` is a wrapper for running the engine from scripts. It takes
an exclusive file lock so only one engine run happens at a time, which keeps frame timings comparable. It enforces a
timeout (exit code 124), writes the log to `tools/out/godot_last.log` and prints the `[test]`, `[autotest]` and error
lines at the end. A script that fails to parse would leave a black window open until the timeout, so the wrapper
watches the log for parse errors and stops the run with exit code 65. `godot_batch.py` runs several headless jobs
under one hold of the lock, `locked.py` runs any other command under it, and `metal_hud.py` extracts GPU frame times
from Apple's Metal HUD log.

## 13. Where to start reading

1. `scripts/main.gd`: `_ready()` and `_build_world()` for what exists at runtime, `_process()` for what each mode does.
2. `dialogue/c2.dlg` next to chapter 2 in `data/chapters.json`: one chapter as data.
3. `scripts/story/dialogue_data.gd`: the parser, then `compile()` for how a cue becomes steps.
4. `scripts/story/story.gd` and `story_commands.gd`: the runner and what commands do.
5. `scripts/story/chapters.gd`: to-dos, staging, clock and triggers as functions of the flags.
6. `scripts/core/game_state.gd`: flags, settings and the save files.
7. `scripts/main.gd`, `talk_to()`, `_on_line()` and `_shot_for()`: how a conversation is staged and filmed.
8. `tests/test_quest.gd` and `tests/support.gd`: the story played without the game.

## 14. Known structural debt

`main.gd` is about 2,900 lines. It is the game root, the mode switch, the chapter flow, the conversation director with
its shot scoring, the sit-down sequence, the opening and the finale. The conversation camera, the sit-downs and the
scripted sequences are separable and should become their own classes.

The game mode is a string assigned in many places, with the related state (player frozen, camera input, HUD visible,
mouse mode, letterbox) set by hand next to each assignment. No state machine guarantees those stay consistent.

Nothing is authored in the editor. Building the tree in code keeps everything diffable and testable, but UI layout and
the animation tree cannot be inspected or adjusted in Godot's tools, and `menus.gd` (about 1,600 lines) and `phone.gd`
(about 1,100) are long as a result. `autotest.gd` is about 3,000 lines with nearly all plans in one file.

`CharacterMaterials.FINISH` keeps per-person shader tuning in code; it is data and belongs next to each character.

A character's position can come from three places: the fallback coordinates in `CastDefs`, the level marker, and
chapter staging through `world.json`. Story positions in `world.json` are raw coordinates, so a level rebuild that
moves geometry does not move them; `autotest=place` exists to catch that by eye.

Some leftovers remain. The save file is `save_v1.json` at format version 2, the flag set by Anisha's scene is called
`ines`, each `StoryCommands.SPEC` entry carries a `stage` number with a `BUILT_STAGE` gate that every command now
passes, and `scripts/fx/` holds prototype hair shaders (`proto_hair_*`) that no script loads. Recorded lines are
matched to cards by a hash of the exact text, so editing a line silently drops its recording.

The headless suite covers story data, quest logic and saves. Rendering, camera placement and movement are checked only
by autotest screenshots that a person looks at, and nothing runs the tests automatically. `tools/dev/godot.py` assumes
macOS and a fixed engine path.
