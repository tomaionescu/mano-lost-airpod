# Status

The game plays from the title screen to the recap page: a cold open, five chapters, the credits and a
post-credits scene. This page lists what is in it, how it is checked, what is known to be wrong, and
what comes next. The design is in [DESIGN.md](DESIGN.md) and the code layout in
[ARCHITECTURE.md](ARCHITECTURE.md).

## What is in the game

The story is one evening, Thursday 15 October, told by a clock that starts at 17:42 and ends past
midnight. The chapters are data (`data/chapters.json`); each has a title card, a clock range, light presets, staging
for the cast, triggers and a list of to-dos.

| Chapter | Clock | Main path | Minigames |
|---|---|---|---|
| Cold open, "23:41" | 23:41 | The courtyard steps at night with everyone there, then back to the afternoon. Skipped when a chapter is replayed. | |
| 1 Mono | 17:42 to 18:29 | Mano wakes in Amphi 4 with one AirPod and a dead phone. He talks to Toma, walks into Ian and Silvia's pastry argument, shows Ishita the way to SM14 and helps Anisha get her code past the moulinette. | Moulinette |
| 2 Lost & Found | 18:30 to 19:04 | Karim in the Under, the lost and found at the Voltaire reception, Mme Dupont's coffee and the two euros it costs, a box of wrong AirPods and a note signed "C.", then the sunset on rue Pasteur. | Babyfoot (alone or with a partner), coffee machine, lost and found |
| 3 Blue Hour | 19:10 to 20:44 | The phone comes back with its messages, Find and Music. Mano follows Cristina's trail to the cafeteria and back, gives Ishita a tour of three places out of six, settles the pastry argument and picks a song with Toma on the steps. | |
| 4 Sauce Samouraï | 21:00 to 23:40 | Cristina and Joaquin at the east end of rue Pasteur, eight kebab orders, the sound search in the Under, a kebab carried past the ACU into SM14, and Anisha's last submission. | Kebab orders, sound search, "1, 2, 3, ACU!", moulinette at night |
| 5 Stereo | 23:41 to 00:10 | Everyone on the steps. Mano chooses who gets the other AirPod, then the credits roll over the night's photos, followed by the post-credits scene and the recap page. | |

Around the main path:

- Twelve golden ducks, a few more each chapter. Eight unlock the third outfit.
- Ishita's disposable camera: ten photo spots and the group photo, taken in photo mode or by the story.
- Six places to sit down and listen to a song, twelve overheard conversations between other students,
  four side stories, and 88 spots to look at or read (`dialogue/look.dlg`, `dialogue/spots.dlg`).
- Mano's phone from chapter 3: five message threads with 56 messages and three replies, a Find app
  and a music list.
- A journal with six tabs, a drawn map of the campus, a wardrobe with three outfits, photo mode.
- Saves: an autosave every 30 seconds of play, after each conversation and under each chapter card,
  with a backup file. The title screen offers Continue and a chapter select that keeps the night's
  choices and everything found.
- Settings: four graphics presets, field of view, volumes per bus, subtitle size, readable fonts,
  typewriter text, reduce motion, film grain, camera sensitivity and Y inversion.

## Verified by

The headless test runner checks the story data without opening a window and exits with code 1 on any
failure:

```
Godot --headless --path . res://tests/test_runner.tscn
```

It runs six suites (`tests/`):

| Suite | What it checks |
|---|---|
| `compile` | Every GDScript in the project loads and compiles, autoloads included. |
| `validate` | The dialogue files, `chapters.json`, `world.json`, `flags.json` and the phone's messages: parse errors, duplicate or missing cues, unknown speakers and flags, references that do not resolve, card length. |
| `port` | Every line and objective of the first version of the game is still present in the data, or listed as rewritten. |
| `quest` | A walker plays the story from the cold open to the recap with no level loaded. A second pass takes every answer of every question, loses each minigame once, and plays the four side stories to their ends. |
| `saves` | A save round trip, migration of an older save format, recovery from a truncated file, chapter snapshots, and that test runs never write to the player's own files. |
| `map` | The campus plan file is complete and no two labels on the map overlap, including with the whole cast on the steps. |

Three further headless scenes under `scenes/dev/` check presentation: `line_check` lays out every
subtitle card in the real font and fails if one needs more than two lines, `hud_check` checks the HUD's
rules (toasts, the objective strip, one-off hints), and `ui_check` checks the notebook screens.

The autotest plans (`scripts/dev/autotest.gd`, `scripts/dev/autotest_life.gd`) drive the real game in a
window and save screenshots. `autotest=story` plays from the cold open to the recap; other plans cover
single minigames, the phone, the sit-downs, the ducks, the photo spots, chapter select, the journal, the
map and frame times. Autotests and tests use their own save and settings files.

None of this replaces a person playing. The autotest places Mano in front of whoever he talks to and
wins minigames from outside, so it does not judge pacing, difficulty or how a scene reads on foot.

## Known issues

Input

- The game can only be paused while walking freely. During a conversation, a cutscene or a minigame
  the pause key does nothing and losing window focus does not pause. In a sit-down any key stands Mano
  up.
- Keys are bound by physical position and cannot be rebound in the settings. On an AZERTY keyboard the
  map therefore opens with the `,` key, not with `M`.
- Six prompts print fixed letters instead of the live binding: babyfoot (`W`, `S`), the lost and found
  (`A / D`), the journal (`A, D`), the photo mode list (`W, S`, `C`, `P`), the wardrobe (`F`) and the
  film note (`C`). Four of them name the wrong key on AZERTY.
- Gamepad bindings exist for walking, talking and the menus but have never been tried with a real
  gamepad. Photo mode is keyboard and mouse only: a pad can open and close it but cannot turn the
  camera or take the picture.

Characters

- Eyes do not move. Every model carries the eight ARKit eye-look shapes, and the rig drives the head,
  the blink, the mouth and the expressions but never those shapes, so a character looks where the head
  points.
- Mme Dupont's hair mesh is broken: stretched polygons hang from the fringe over her face and down to
  her waist in every front shot, including the last line of the game.

Light and camera

- Exposure is set per time of day only. Indoors the game lowers ambient light, fog and the
  conversation fill light but keeps the outdoor exposure, so the Under is too dark at blue hour and at
  night and the Voltaire stairwell is too bright.
- Anisha's first line opens on a two-shot from standing height in which Mano's back fills the frame.
- Mano's thoughts are filmed over the nearest shoulder, which is crowded when three people stand
  together at the cafeteria counter or on the steps.

Minigames

- Babyfoot is not balanced. Karim's rods move at roughly half the speed of Mano's, a partner's rod is
  faster than Karim's as well, and none of it has been tuned against players.
- The babyfoot table in the level has its own eight rods of figures. The minigame draws its four rods
  on top without hiding them, so the table's figures show through.

Audio

- The music is never panned to one ear, although Mano wears a single AirPod until chapter 4. It plays
  in stereo throughout, and there is no mono setting (V2-12 in the design backlog).
- All music is six tracks by Kevin MacLeod. The soundtrack change planned in V2-11 has not been made,
  nor has the audio mix pass (V2-34).

Story and text

- Chapter 5 is short: one to-do and no walking, about four minutes by the estimate described below.
- Karim says Cristina asked for "M." and did not know the name, but her message in the group chat at
  18:54 already says "It's Mano's?".
- At night the thought on the passage gate says it is locked, and Mano walks through it all night.
- The wardrobe's locked outfit says "Find all 8 golden rubber ducks"; there are twelve, and eight is
  the threshold.
- Photo mode copies kept for the credits are never cleared, so pictures from an earlier playthrough
  appear in a later one's credits.

Build and platform

- There is no export preset. The game runs from the Godot editor binary through `Play Mano.command`,
  which is macOS only and expects Godot at `~/Applications/godot/Godot.app`.
- It has only ever run on the machine it was developed on, an M4 MacBook. There the High preset stays
  under 60 frames a second while moving; no performance pass (V2-32) has been done.
- The playtime of about 50 minutes on the main path is an estimate built from card counts, walking
  distances and an assumed reading speed. Nobody has timed a playthrough.
- `tools/blender/build_campus.py` documents a `--preview-only` option that the script does not handle.
- The tool scripts assume macOS and fixed install paths for Godot, Blender and Python
  ([PIPELINE.md](PIPELINE.md), Prerequisites).

Repository

- A few files ship without being used: the fonts `PlaywriteFRModerne-VF.ttf` and
  `ShantellSans-Italic-VF.ttf`, the ambience loop `assets/audio/amb/under_music.ogg`, the prototype hair
  shaders `scripts/fx/proto_hair_*` and the probe shaders in `scripts/dev/`.

Not built from the design backlog ([DESIGN.md](DESIGN.md) §12): the journal's messages tab and clue web
(V2-08), floors, zoom and pan on the map (V2-09), the remaining accessibility settings such as a
subtitle background, mono audio and a UI scale (V2-35), and the KB1 terrace (V2-37).

## Next

1. Make pause work in conversations, cutscenes and minigames.
2. Add export presets, build the game, and run it on a second machine and with a gamepad.
3. Read every key prompt from the live binding, bind the map key by its label, and give photo mode
   gamepad controls.
4. Rebuild Mme Dupont's hair.
5. Add an exposure correction per interior, starting with the Under and the Voltaire stairwell.
6. Drive the eye-look shapes from the same target as the head.
7. Hide the table's own figures during babyfoot, then tune Karim's speed against real players.
8. Play the music in the left ear only until the second AirPod is found, with a mono setting beside it.
9. Have someone who has not seen the game play it through with a stopwatch, and use the result to
   decide what chapter 5 needs.
