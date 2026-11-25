# Audio credits - Mano & the Lost AirPod

Every file the game loads from `assets/audio/` is listed below with its source(s), author, licence and the edits made.
Format: OGG Vorbis 44.1 kHz; footsteps and one-shots mono, ambience and music stereo.
Ambience and music are imported with `loop=true` (see their `.ogg.import`); one-shots/footsteps play once.
Build scripts: `tools/py/audio_*.py` (raw downloads in `tools/audio_src/`, not shipped).

## Attribution required (must appear in the game's credits)

All music is by Kevin MacLeod, licensed CC BY 4.0. Use these lines verbatim in the in-game credits:

- "Almost Bliss" Kevin MacLeod (incompetech.com)  Licensed under Creative Commons: By Attribution 4.0 License  http://creativecommons.org/licenses/by/4.0/
- "Evening" Kevin MacLeod (incompetech.com)  Licensed under Creative Commons: By Attribution 4.0 License  http://creativecommons.org/licenses/by/4.0/
- "Morning" Kevin MacLeod (incompetech.com)  Licensed under Creative Commons: By Attribution 4.0 License  http://creativecommons.org/licenses/by/4.0/
- "Raving Energy" Kevin MacLeod (incompetech.com)  Licensed under Creative Commons: By Attribution 4.0 License  http://creativecommons.org/licenses/by/4.0/
- "Sneaky Snitch" Kevin MacLeod (incompetech.com)  Licensed under Creative Commons: By Attribution 4.0 License  http://creativecommons.org/licenses/by/4.0/
- "Study And Relax" Kevin MacLeod (incompetech.com)  Licensed under Creative Commons: By Attribution 4.0 License  http://creativecommons.org/licenses/by/4.0/

Everything else is CC0 (Freesound uploads listed below, Kenney packs, or synthesised for this game); no attribution is legally required, but credit is given here anyway. Suggested optional line: *Sound effects: Kenney (kenney.nl) and Freesound contributors (see CREDITS.md).*

## Music (`music/`, -18 LUFS integrated)

| File | Source | Duration / loudness / peak | What was done |
|---|---|---|---|
| `music/title.ogg` | ["Morning"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/Morning.mp3) by Kevin MacLeod (CC BY 4.0) | 113.93 s, -17.9 LUFS, peak -4.3 dBFS | loop 21.478-135.412 s of the original (38 bars of 3 at 60.01 bpm), 0.35 s equal-power crossfade of the post-loop audio into the loop head (self-similarity 0.59, waveform xcorr 0.88); static gain +0.0 dB to -18 LUFS |
| `music/explore.ogg` | ["Almost Bliss"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/Almost%20Bliss.mp3) by Kevin MacLeod (CC BY 4.0) | 170.67 s, -17.8 LUFS, peak -4.4 dBFS | loop 27.446-198.113 s of the original (64 bars of 4 at 90.00 bpm), 0.35 s equal-power crossfade of the post-loop audio into the loop head (self-similarity 0.97, waveform xcorr 1.00); static gain +2.7 dB to -18 LUFS |
| `music/explore_dusk.ogg` | ["Study And Relax"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/Study%20And%20Relax.mp3) by Kevin MacLeod (CC BY 4.0) | 160.01 s, -17.9 LUFS, peak -4.0 dBFS | loop 8.684-168.691 s of the original (48 bars of 4 at 72.00 bpm), 0.60 s equal-power crossfade of the post-loop audio into the loop head (self-similarity 0.57, waveform xcorr 0.41); static gain +0.7 dB to -18 LUFS |
| `music/tension.ogg` | ["Sneaky Snitch"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3) by Kevin MacLeod (CC BY 4.0) | 88.27 s, -17.8 LUFS, peak -2.8 dBFS | loop 8.800-97.068 s of the original (32 bars of 4 at 87.00 bpm), 0.35 s equal-power crossfade of the post-loop audio into the loop head (self-similarity 0.59, waveform xcorr 0.76); static gain -0.4 dB to -18 LUFS |
| `music/under_party.ogg` | ["Raving Energy"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/Raving%20Energy.mp3) by Kevin MacLeod (CC BY 4.0) | 188.85 s, -17.9 LUFS, peak -4.2 dBFS | loop 49.737-238.590 s of the original (96 bars of 4 at 122.00 bpm), 0.35 s equal-power crossfade of the post-loop audio into the loop head (self-similarity 0.83, waveform xcorr 0.87); static gain -4.1 dB to -18 LUFS |
| `music/ending.ogg` | ["Evening"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/Evening.mp3) by Kevin MacLeod (CC BY 4.0) | 185.67 s, -17.9 LUFS, peak -5.7 dBFS | full piece 0.48-184.65 s (leading silence trimmed, natural ending kept, 1.5 s silence before it repeats); static gain -4.6 dB to -18 LUFS |

## Ambience loops (`amb/`, seamless)

Each loop: the audio just after the loop end is equal-power crossfaded into the head (2-3 s), so the last sample flows into the first; static gain to the target loudness; a gentle wrap-around peak limiter at -8.5 dBFS only where rare transients exceeded it.

| File | Sources | Duration / loudness / peak | What was done |
|---|---|---|---|
| `amb/city_traffic.ogg` | [Freesound #513729 "ambiance rue stereo.wav"](https://freesound.org/people/transeman/sounds/513729/) by transeman (CC0 1.0 (public domain))<br>[Freesound #36734 "citystreet3.wav"](https://freesound.org/people/moxobna/sounds/36734/) by moxobna (CC0 1.0 (public domain))<br>[Freesound #523959 "moped pass by.wav"](https://freesound.org/people/lartti/sounds/523959/) by lartti (CC0 1.0 (public domain))<br>[Freesound #3185 "PassingMoped01.wav"](https://freesound.org/people/Pingel/sounds/3185/) by Pingel (CC0 1.0 (public domain)) | 80.00 s, -23.0 LUFS, peak -8.2 dBFS | calm Paris street (513729) + distant low traffic roar (36734 calm section, low-passed 1.4 kHz) + one moped pass (523959, low-passed, ~38 s) + a fainter distant moped (3185, ~14 s); target -23 LUFS |
| `amb/wind_light.ogg` | [Freesound #181250 "a gentle breeze, wind 1"](https://freesound.org/people/mario1298/sounds/181250/) by mario1298 (CC0 1.0 (public domain)) | 70.00 s, -28.0 LUFS, peak -13.2 dBFS | gentle breeze (181250, mono) made stereo by taking the right channel 17 s later; high-passed 70 Hz, low-passed 5.5 kHz; target -28 LUFS |
| `amb/courtyard_crowd.ogg` | [Freesound #741283 "Crowd walla (french english) EXT"](https://freesound.org/people/xkeril/sounds/741283/) by xkeril (CC0 1.0 (public domain))<br>[Freesound #407051 "crowd ext light students on covered concrete path of university campus could be courtyard boomy voices echo scratchy steps kinda too close for ambience Mbale, Uganda, Africa 2016.wav"](https://freesound.org/people/kyles/sounds/407051/) by kyles (CC0 1.0 (public domain)) | 65.00 s, -24.0 LUFS, peak -8.0 dBFS | outdoor walla, mostly French (741283) + a farther student crowd layer (407051); both band-limited (150 Hz-3.6 kHz / 2.5 kHz) with a little reverb for distance so words stay unintelligible; target -24 LUFS |
| `amb/birds_evening.ogg` | [Freesound #509682 "town or city, Warsaw University main campus, coronavirus quarantine, birds sing, pigeons, dusk, spring, 5 o'clock chime, bells, very sparse people, spring, Poland.wav"](https://freesound.org/people/be_a_hero_not_a_patriot/sounds/509682/) by be_a_hero_not_a_patriot (CC0 1.0 (public domain))<br>[Freesound #521558 "blackbird-evening.wav"](https://freesound.org/people/echobones/sounds/521558/) by echobones (CC0 1.0 (public domain)) | 80.00 s, -27.0 LUFS, peak -10.6 dBFS | sparse dusk birds: high-passed (1.2 kHz) bird bed from a Warsaw campus dusk recording (509682, 62-145 s) + seven blackbird phrases (521558) placed irregularly with varied level/pan and a little distance reverb; target -27 LUFS |
| `amb/room_tone_large.ogg` | [Freesound #454165 "room tone large convention room heavy ventilation +light crowd Palais des Congres Montreal, Canada2.flac"](https://freesound.org/people/kyles/sounds/454165/) by kyles (CC0 1.0 (public domain))<br>[Freesound #144046 "Room_Tone_Ambience_Medium_Control_Low_Hum.wav"](https://freesound.org/people/gchase/sounds/144046/) by gchase (CC0 1.0 (public domain)) | 66.00 s, -26.0 LUFS, peak -11.9 dBFS | large convention-room tone with ventilation and a very distant crowd (454165) + low theatre control-room hum (144046) for weight; low-passed 6 kHz; target -26 LUFS |
| `amb/hvac.ogg` | [Freesound #637804 "room tone office hallway heavy ventilation.flac"](https://freesound.org/people/kyles/sounds/637804/) by kyles (CC0 1.0 (public domain)) | 75.00 s, -27.0 LUFS, peak -15.8 dBFS | office hallway with heavy ventilation (637804, 12-90 s), low-passed 7 kHz; target -27 LUFS |
| `amb/room_tone.ogg` | [Freesound #203306 "Room Tone Office 13"](https://freesound.org/people/mzui/sounds/203306/) by mzui (CC0 1.0 (public domain))<br>[Freesound #144046 "Room_Tone_Ambience_Medium_Control_Low_Hum.wav"](https://freesound.org/people/gchase/sounds/144046/) by gchase (CC0 1.0 (public domain)) | 70.00 s, -28.0 LUFS, peak -13.9 dBFS | office room tone (203306) blended with a soft low hum (144046); target -28 LUFS |
| `amb/lobby_murmur.ogg` | [Freesound #733849 "Walla Crowd Inside French"](https://freesound.org/people/Salom%C3%A9_Lubczanski/sounds/733849/) by Salomé_Lubczanski (CC0 1.0 (public domain)) | 62.00 s, -24.0 LUFS, peak -8.9 dBFS | French crowd murmur in a big hall (733849), band-limited 120 Hz-6 kHz; target -24 LUFS |
| `amb/computer_room.ogg` | [Freesound #455828 "room tone small room with computer fans in open enclosure.flac"](https://freesound.org/people/kyles/sounds/455828/) by kyles (CC0 1.0 (public domain)) | 75.00 s, -25.0 LUFS, peak -10.1 dBFS | small room full of computer fans (455828, 20-98 s); target -25 LUFS |
| `amb/keyboards.ogg` | [Freesound #537473 "typing real words on a computer keyboard.m4a"](https://freesound.org/people/MoralX/sounds/537473/) by MoralX (CC0 1.0 (public domain))<br>[Freesound #489424 "Typing on a keyboard"](https://freesound.org/people/SamsterBirdies/sounds/489424/) by SamsterBirdies (CC0 1.0 (public domain)) | 75.00 s, -27.0 LUFS, peak -7.8 dBFS | sparse distant typing: 14 typing bursts (537473 laptop/keyboard, 489424 mechanical) at different distances (low-pass 2.5-6 kHz, room reverb, pan), with silent gaps; target -27 LUFS |
| `amb/cafeteria.ogg` | [Freesound #625112 "Crowd at Cafeteria"](https://freesound.org/people/sonically_sound/sounds/625112/) by sonically_sound (CC0 1.0 (public domain))<br>[Freesound #128291 "Cafeteria.mp3"](https://freesound.org/people/GaryQ/sounds/128291/) by GaryQ (CC0 1.0 (public domain))<br>[Kenney impact-sounds](https://kenney.nl/assets/impact-sounds) - impactPlate_light, impactGlass_light, impactMetal_light by Kenney (CC0 1.0 (public domain)) | 80.00 s, -22.9 LUFS, peak -8.3 dBFS | canteen chatter (625112, Turkish university cafeteria) + far school-canteen layer (128291, low-passed 3.5 kHz) + soft scattered plate/glass/cutlery clinks (Kenney impact sounds, low-passed, reverb); target -23 LUFS |
| `amb/fridge_hum.ogg` | [Freesound #730438 "Vending Machine Hum"](https://freesound.org/people/HECKFRICKER/sounds/730438/) by HECKFRICKER (CC0 1.0 (public domain)) | 47.00 s, -28.0 LUFS, peak -15.5 dBFS | vending machine cooling hum (730438, 2-52 s); target -28 LUFS |
| `amb/basement_tone.ogg` | [Freesound #451924 "room tone large room church basement heavy deep ventilation or furnace hum.flac"](https://freesound.org/people/kyles/sounds/451924/) by kyles (CC0 1.0 (public domain)) | 64.00 s, -27.0 LUFS, peak -14.0 dBFS | large church-basement room tone with deep ventilation/furnace hum (451924); target -27 LUFS |
| `amb/under_music.ogg` | ["Raving Energy"](https://incompetech.com/music/royalty-free/mp3-royaltyfree/Raving%20Energy.mp3) by Kevin MacLeod (CC BY 4.0) | 62.95 s, -23.9 LUFS, peak -10.5 dBFS | muffled party music through a wall: a bar-aligned loop of Kevin MacLeod 'Raving Energy' (same track as music/under_party), folded to near-mono, low-passed (400 Hz + 900 Hz, 2nd order each), +3 dB at 90 Hz, small basement reverb (loop 49.74-112.69 s, 32 bars, waveform xcorr 0.91); target -24 LUFS |

## One-shots (`sfx/`, mono, peak about -3 dBFS)

Numbered variants (`machine_shake_1..3`, `babyfoot_kick_1..3`) are picked at random by `Sfx._load`.

| File | Sources | Duration / loudness / peak | What was done |
|---|---|---|---|
| `sfx/babyfoot_goal.ogg` | [Freesound #387132 "Foosball Win"](https://freesound.org/people/Jofae/sounds/387132/) by Jofae (CC0 1.0 (public domain)) | 1.71 s, -28.1 LUFS, peak -3.1 dBFS | Freesound 387132 'Foosball Win': ball thud into the goal (0.80-1.25 s) spliced onto the return-channel rattle (2.00-3.25 s) with a 60 ms crossfade; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/babyfoot_kick_1.ogg` | [Freesound #180320 "foosballslapshots.wav"](https://freesound.org/people/wjoojoo/sounds/180320/) by wjoojoo (CC0 1.0 (public domain)) | 0.33 s, peak -3.2 dBFS | table-football slapshot hit (Freesound 180320, 2.40-2.72 s); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/babyfoot_kick_2.ogg` | [Freesound #186354 "foosball.wav"](https://freesound.org/people/estupe/sounds/186354/) by estupe (CC0 1.0 (public domain)) | 0.29 s, peak -2.9 dBFS | table-football rod/ball hit (Freesound 186354, 1.76-2.05 s); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/babyfoot_kick_3.ogg` | [Freesound #186354 "foosball.wav"](https://freesound.org/people/estupe/sounds/186354/) by estupe (CC0 1.0 (public domain)) | 0.29 s, peak -3.6 dBFS | table-football rod/ball hit (Freesound 186354, 0.01-0.30 s); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/coffee_machine.ogg` | [Freesound #503427 "Coffee Grinder HQ.wav"](https://freesound.org/people/tosha73/sounds/503427/) by tosha73 (CC0 1.0 (public domain))<br>[Freesound #402845 "Espresso Machine (Automatic)"](https://freesound.org/people/BageBoy/sounds/402845/) by BageBoy (CC0 1.0 (public domain)) | 3.00 s, -15.5 LUFS, peak -3.1 dBFS | 3.0 s seamless loop: coffee grinder (Freesound 503427) over espresso pump/brew (Freesound 402845, 24-33 s), 0.4 s crossfaded seam, fade-in/out not applied so it can loop |
| `sfx/coin.ogg` | [Kenney rpg-audio](https://kenney.nl/assets/rpg-audio) - handleCoins2.ogg by Kenney (CC0 1.0 (public domain))<br>original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 1.13 s, -15.3 LUFS, peak -2.8 dBFS | real coin clink (Kenney handleCoins2, high-passed) + synthesised 2-note celesta chime B5 -> E6; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/crowd_cheer.ogg` | [Freesound #752709 "Voice_Crowd_Small_Expression_Applause_Cheer_Stereo"](https://freesound.org/people/Nox_Sound/sounds/752709/) by Nox_Sound (CC0 1.0 (public domain)) | 2.31 s, -19.2 LUFS, peak -2.9 dBFS | Freesound 752709 small crowd cheer + applause (0.28-2.60 s), mono, fades; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/door_close.ogg` | [Freesound #637479 "door metal institutional push bar open close.flac"](https://freesound.org/people/kyles/sounds/637479/) by kyles (CC0 1.0 (public domain)) | 0.77 s, -20.9 LUFS, peak -2.9 dBFS | Freesound 637479 institutional push-bar door, closing part (1.96-2.89 s); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/door_open.ogg` | [Freesound #637479 "door metal institutional push bar open close.flac"](https://freesound.org/people/kyles/sounds/637479/) by kyles (CC0 1.0 (public domain)) | 1.14 s, -23.4 LUFS, peak -2.4 dBFS | Freesound 637479 institutional push-bar door, opening part (0.00-1.26 s); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/duck.ogg` | [Freesound #201285 "Rubber duck toy squeaking.wav"](https://freesound.org/people/panmaterac/sounds/201285/) by panmaterac (CC0 1.0 (public domain))<br>original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 1.08 s, -15.5 LUFS, peak -3.1 dBFS | rubber duck squeak (Freesound 201285, 1.78-2.25 s) + synthesised pentatonic celesta sparkle; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/fanfare.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 3.10 s, -19.4 LUFS, peak -3.0 dBFS | synthesised short happy sting (C major: plucked-string arpeggio G4-C5-E5-G5 / E5-G5 -> C6, held C chord on FM e-piano, celesta sparkle), plate reverb; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/journal_close.ogg` | [Kenney rpg-audio](https://kenney.nl/assets/rpg-audio) - bookClose.ogg by Kenney (CC0 1.0 (public domain)) | 0.20 s, peak -2.8 dBFS | Kenney bookClose, gentle 9 kHz low-pass, small room; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/journal_open.ogg` | [Kenney rpg-audio](https://kenney.nl/assets/rpg-audio) - bookOpen.ogg by Kenney (CC0 1.0 (public domain))<br>[Kenney rpg-audio](https://kenney.nl/assets/rpg-audio) - bookFlip3.ogg by Kenney (CC0 1.0 (public domain)) | 0.35 s, peak -3.3 dBFS | Kenney bookOpen followed by a page flip (bookFlip3), small room; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/machine_clunk.ogg` | [Freesound #448673 "Soda Machine Bottle Drop (Binaural).wav"](https://freesound.org/people/courter/sounds/448673/) by courter (CC0 1.0 (public domain))<br>[Kenney impact-sounds](https://kenney.nl/assets/impact-sounds) - impactSoft_heavy_000.ogg by Kenney (CC0 1.0 (public domain)) | 0.58 s, -17.1 LUFS, peak -3.2 dBFS | soda machine bottle drop (Freesound 448673, 18.00-18.60 s) layered with a low soft thud (Kenney impactSoft_heavy_000); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/machine_shake_1.ogg` | [Freesound #104371 "Metal Thing Medium-Heavy Rattling.aif"](https://freesound.org/people/RutgerMuller/sounds/104371/) by RutgerMuller (CC0 1.0 (public domain))<br>[Kenney impact-sounds](https://kenney.nl/assets/impact-sounds) - impactMetal_heavy_000.ogg by Kenney (CC0 1.0 (public domain)) | 0.70 s, -23.3 LUFS, peak -3.1 dBFS | metal rattle (Freesound 104371, 6.85-7.55 s) + Kenney metal thud on the downbeat; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/machine_shake_2.ogg` | [Freesound #104371 "Metal Thing Medium-Heavy Rattling.aif"](https://freesound.org/people/RutgerMuller/sounds/104371/) by RutgerMuller (CC0 1.0 (public domain))<br>[Kenney impact-sounds](https://kenney.nl/assets/impact-sounds) - impactMetal_heavy_000.ogg by Kenney (CC0 1.0 (public domain)) | 0.70 s, -23.3 LUFS, peak -3.0 dBFS | metal rattle (Freesound 104371, 7.75-8.45 s) + Kenney metal thud; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/machine_shake_3.ogg` | [Freesound #849797 "Metal Rattles"](https://freesound.org/people/IENBA/sounds/849797/) by IENBA (CC0 1.0 (public domain))<br>[Kenney impact-sounds](https://kenney.nl/assets/impact-sounds) - impactMetal_heavy_000.ogg by Kenney (CC0 1.0 (public domain)) | 0.63 s, -23.9 LUFS, peak -3.2 dBFS | metal rattle hit (Freesound 849797, 22.42-23.05 s) + Kenney metal thud; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/map_open.ogg` | [Freesound #447931 "Unfold a map"](https://freesound.org/people/Breviceps/sounds/447931/) by Breviceps (CC0 1.0 (public domain)) | 1.03 s, -26.4 LUFS, peak -3.7 dBFS | Freesound 447931 'Unfold a map' from 0.28 s (skips the faint pre-crinkle so the unfold starts at once), 20 ms fade-in, high-passed 120 Hz; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/objective.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 2.52 s, -15.3 LUFS, peak -2.9 dBFS | synthesised gentle 2-note sting: FM electric-piano E5 -> A5 with mallet octave doubling and a low A3 bed, plate reverb; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/phone_buzz.ogg` | [Freesound #384487 "cell phone vibrate glass_loopable.wav"](https://freesound.org/people/mobaudio/sounds/384487/) by mobaudio (CC0 1.0 (public domain)) | 1.63 s, -17.1 LUFS, peak -3.3 dBFS | Freesound 384487 phone vibrating on glass, two pulses (0.00-1.66 s); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/pickup.ogg` | [Kenney rpg-audio](https://kenney.nl/assets/rpg-audio) - cloth3.ogg by Kenney (CC0 1.0 (public domain))<br>original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 0.61 s, -18.8 LUFS, peak -3.0 dBFS | synthesised soft rising 'pop' + mallet G6 blip, with a short cloth rustle (Kenney cloth3); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/plink.ogg` | [Freesound #361661 "Item Drop_Plastic 001.wav"](https://freesound.org/people/mjvilches/sounds/361661/) by mjvilches (CC0 1.0 (public domain)) | 0.58 s, -29.9 LUFS, peak -3.8 dBFS | Freesound 361661 small plastic item drop (bounce sequence), sped up x1.12 for a lighter object, short tiled-room reflection; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/shutter.ogg` | [Freesound #271010 "Camera Shutter Click"](https://freesound.org/people/Kodack/sounds/271010/) by Kodack (CC0 1.0 (public domain)) | 0.58 s, -21.8 LUFS, peak -3.8 dBFS | Freesound 271010 camera shutter click (0.62-1.30 s), high-passed 150 Hz; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/sit.ogg` | [Freesound #767051 "Office chair creaking"](https://freesound.org/people/ThabzMalik/sounds/767051/) by ThabzMalik (CC0 1.0 (public domain))<br>[Kenney impact-sounds](https://kenney.nl/assets/impact-sounds) - impactSoft_medium_000.ogg by Kenney (CC0 1.0 (public domain)) | 0.42 s, -24.3 LUFS, peak -2.9 dBFS | soft seat thud (Kenney impactSoft_medium_000, low-passed) + office-chair creak (Freesound 767051, 7.60-8.00 s); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/toast.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 1.11 s, -15.2 LUFS, peak -3.0 dBFS | synthesised soft notification chime (celesta E6 + B6 grace, small plate); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/typing_burst.ogg` | [Freesound #537473 "typing real words on a computer keyboard.m4a"](https://freesound.org/people/MoralX/sounds/537473/) by MoralX (CC0 1.0 (public domain)) | 2.11 s, -31.4 LUFS, peak -3.1 dBFS | Freesound 537473 keyboard typing, densest 2.0 s window (45.8-47.8 s), mono, fades; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/ui_back.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 0.32 s, peak -3.3 dBFS | synthesised low mallet 'bup' (D5 with a slight downward pitch glide); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/ui_click.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 0.31 s, peak -3.1 dBFS | synthesised soft mallet 'tock' (A5 + woody strike noise), tiny room; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/ui_close.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 0.72 s, -17.3 LUFS, peak -3.0 dBFS | synthesised falling mallet pair (E6 -> A5) over a soft falling air swish; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/ui_hover.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 0.12 s, peak -6.0 dBFS | synthesised soft wooden tick (modal mallet D7, 25 ms decay); peak -6 dBFS on purpose (frequent); start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/ui_open.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 0.75 s, -16.4 LUFS, peak -3.2 dBFS | synthesised rising mallet pair (A5 -> E6) over a soft rising air swish; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/whoosh.ogg` | original synthesis for this game (`tools/py/audio_sfx.py`, CC0 1.0 (public domain)) | 0.72 s, -15.5 LUFS, peak -3.3 dBFS | synthesised soft transition whoosh (band-swept noise 350 Hz -> 1.9 kHz -> 600 Hz, 0.55 s), gentle room; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/zipper.ogg` | [Freesound #763462 "zipper on backpack - 1"](https://freesound.org/people/FOSSarts/sounds/763462/) by FOSSarts (CC0 1.0 (public domain)) | 1.25 s, -15.9 LUFS, peak -2.9 dBFS | Freesound 763462 backpack zipper, first 1.15 s of the pull, fade-out; start trimmed to the first transient, tail faded, peak-normalised |
| `sfx/airpod_chirp.ogg` | original synthesis for this game (`tools/py/sfx_synth.py`, CC0 1.0 (public domain)) | 1.29 s, peak -3.0 dBFS | the right AirPod ringing in the Under's sofa (chapter 4's sound search): a rising four-note sine chirp (A6, C#7, E7, A7) played twice, low-passed 7 kHz, a small room; not any brand's sound |
| `sfx/soundcheck_thump.ogg` | original synthesis for this game (`tools/py/sfx_synth.py`, CC0 1.0 (public domain)) | 0.60 s, peak -3.0 dBFS | the BDE's sound check through the Under: a kick drum (sine swept 140 -> 48 Hz, a band-passed click, soft saturation, room) |
| `sfx/kebab_bell.ogg` | original synthesis for this game (`tools/py/sfx_synth.py`, CC0 1.0 (public domain)) | 1.10 s, peak -3.0 dBFS | the kebab counter's bell for each ticket: a struck bell on E6 (four inharmonic partials), a small room |

## Footsteps (`footsteps/`, mono, single sneaker steps < 0.5 s)

Each step was sliced from a walking recording at the transient (2 ms lead-in), high-passed (50-70 Hz), cut where it decays 38 dB under its peak (or before the next step) with a short fade-out, then level-matched inside its set (RMS of the first 120 ms: -27 dBFS for concrete/tile/rubber, -27.5 wood, -29.5 grass, -31 carpet; peaks <= -6 dBFS).

| Files | Source | Source times (s) | Peaks |
|---|---|---|---|
| `concrete_1.ogg`, `concrete_2.ogg`, `concrete_3.ogg`, `concrete_4.ogg`, `concrete_5.ogg`, `concrete_6.ogg` | [Freesound #713428 "Foley Zapatillas o Crocs Calle"](https://freesound.org/people/StarfunkBoogie/sounds/713428/) by StarfunkBoogie (CC0 1.0 (public domain)) | 6.93, 13.97, 15.43, 27.80, 29.74, 33.63 | -8.3 / -8.5 / -7.8 / -9.3 / -7.4 / -7.5 dBFS |
| `tile_1.ogg`, `tile_2.ogg`, `tile_3.ogg`, `tile_4.ogg`, `tile_5.ogg`, `tile_6.ogg` | [Freesound #170506 "Footsteps, Tile, Male Sneakers, Slow Pace.wav"](https://freesound.org/people/SpliceSound/sounds/170506/) by SpliceSound (CC0 1.0 (public domain)) | 1.00, 2.34, 2.96, 6.25, 7.53, 18.56 | -8.6 / -8.1 / -6.3 / -9.7 / -8.8 / -7.1 dBFS |
| `carpet_1.ogg`, `carpet_2.ogg`, `carpet_3.ogg`, `carpet_4.ogg`, `carpet_5.ogg`, `carpet_6.ogg` | [Freesound #256209 "Foodsteps-Sneakers-on-Carpet_mono.wav"](https://freesound.org/people/hannagreen/sounds/256209/) by hannagreen (CC0 1.0 (public domain)) | 4.72, 5.21, 5.73, 10.07, 12.14, 12.66 | -21.1 / -20.1 / -18.9 / -20.1 / -22.0 / -20.3 dBFS |
| `wood_1.ogg`, `wood_2.ogg`, `wood_3.ogg`, `wood_4.ogg` | [Freesound #405114 "WoodType_1_Footstep_Sneakers.wav"](https://freesound.org/people/monte32/sounds/405114/) by monte32 (CC0 1.0 (public domain)) | 0.99, 2.37, 3.50, 4.56 | -9.8 / -11.6 / -12.5 / -14.9 dBFS |
| `wood_5.ogg`, `wood_6.ogg` | [Freesound #863017 "Footsteps - very slow walking in trainers on hardwood floor"](https://freesound.org/people/lreeve/sounds/863017/) by lreeve (CC0 1.0 (public domain)) | 8.78, 13.87 | -13.6 / -14.2 dBFS |
| `rubber_1.ogg`, `rubber_2.ogg`, `rubber_3.ogg`, `rubber_4.ogg`, `rubber_5.ogg`, `rubber_6.ogg` | [Freesound #546826 "Footsteps Sneaker Linoleum"](https://freesound.org/people/Kinoton/sounds/546826/) by Kinoton (CC0 1.0 (public domain)) | 2.25, 3.03, 8.76, 10.55, 13.27, 14.16 | -7.0 / -8.2 / -8.7 / -9.0 / -6.5 / -6.9 dBFS |
| `grass_1.ogg`, `grass_2.ogg`, `grass_3.ogg`, `grass_4.ogg` | [Freesound #476119 "Steps: Sneakers on Grass"](https://freesound.org/people/Sheyvan/sounds/476119/) by Sheyvan (CC0 1.0 (public domain)) | 27.12, 32.08, 34.07, 58.07 | -12.2 / -13.2 / -12.3 / -13.6 dBFS |

## Voice lines (`voice/`, mono, about -18 LUFS, true peak at most -3 dBFS)

Synthetic voices for the **fictional NPCs only**. The friends (Toma, Mano, Ian, Joaquin, Anisha, Silvia, Ishita,
Cristina) have no synthetic voice and nobody's voice was cloned: their lines are silent text. Generated with
**Higgsfield `qwen_audio_tts` (Qwen Audio 3.0 TTS Flash, Alibaba Cloud)**, Higgsfield preset voices, `language fr`
with an instruction asking for English with a light, natural French accent, wav 44.1 kHz.
Each file is one subtitle card, `<key>.ogg` with key = speaker + sha1 of the card text (`scripts/story/voice.gd`);
`manifest.json` lists text, length, source job and the 30 Hz jaw envelope. Lines that share a voice and scene
were spoken in one take and cut at the pauses (word timings from a local Whisper, `tools/py/voice_align.py`), then
trimmed, high-passed at 70 Hz, levelled (fast lookahead limiter on the loudest syllables) and encoded to Vorbis
by `tools/py/voice_build.py`. The sleeper's mumble sits 7 dB and Inès's whisper 4 dB under the others.

| NPC | Preset voice | Files |
|---|---|---|
| Mme Dupont | Nora | 17 |
| M. Bernard | Alexey | 3 |
| ACU Léo | Leo | 5 |
| Karim (BDE) | Mark | 14 |
| Yanis | Xavier | 3 |
| Théo | Julian | 3 |
| Piscine survivor | Andre | 3 |
| Inès | Vesper | 1 |
| Chloé (BDE) | Chloe | 2 |
| SPE student | Hana | 2 |
| Waiting student | Kevin | 2 |
| Sleepy SUP | Caspian | 1 |

Not voiced: the background students' five lines (`crowd_m` / `crowd_f`) and Mme Dupont's six replies in the lost &
found minigame.

## Source index

### Freesound (HQ previews, downloaded without login; licence checked on each sound page)

- #3185 "PassingMoped01.wav" by **Pingel** - CC0 1.0 (public domain) - https://freesound.org/people/Pingel/sounds/3185/
- #36734 "citystreet3.wav" by **moxobna** - CC0 1.0 (public domain) - https://freesound.org/people/moxobna/sounds/36734/
- #104371 "Metal Thing Medium-Heavy Rattling.aif" by **RutgerMuller** - CC0 1.0 (public domain) - https://freesound.org/people/RutgerMuller/sounds/104371/
- #128291 "Cafeteria.mp3" by **GaryQ** - CC0 1.0 (public domain) - https://freesound.org/people/GaryQ/sounds/128291/
- #144046 "Room_Tone_Ambience_Medium_Control_Low_Hum.wav" by **gchase** - CC0 1.0 (public domain) - https://freesound.org/people/gchase/sounds/144046/
- #170506 "Footsteps, Tile, Male Sneakers, Slow Pace.wav" by **SpliceSound** - CC0 1.0 (public domain) - https://freesound.org/people/SpliceSound/sounds/170506/
- #180320 "foosballslapshots.wav" by **wjoojoo** - CC0 1.0 (public domain) - https://freesound.org/people/wjoojoo/sounds/180320/
- #181250 "a gentle breeze, wind 1" by **mario1298** - CC0 1.0 (public domain) - https://freesound.org/people/mario1298/sounds/181250/
- #186354 "foosball.wav" by **estupe** - CC0 1.0 (public domain) - https://freesound.org/people/estupe/sounds/186354/
- #201285 "Rubber duck toy squeaking.wav" by **panmaterac** - CC0 1.0 (public domain) - https://freesound.org/people/panmaterac/sounds/201285/
- #203306 "Room Tone Office 13" by **mzui** - CC0 1.0 (public domain) - https://freesound.org/people/mzui/sounds/203306/
- #256209 "Foodsteps-Sneakers-on-Carpet_mono.wav" by **hannagreen** - CC0 1.0 (public domain) - https://freesound.org/people/hannagreen/sounds/256209/
- #271010 "Camera Shutter Click" by **Kodack** - CC0 1.0 (public domain) - https://freesound.org/people/Kodack/sounds/271010/
- #361661 "Item Drop_Plastic 001.wav" by **mjvilches** - CC0 1.0 (public domain) - https://freesound.org/people/mjvilches/sounds/361661/
- #384487 "cell phone vibrate glass_loopable.wav" by **mobaudio** - CC0 1.0 (public domain) - https://freesound.org/people/mobaudio/sounds/384487/
- #387132 "Foosball Win" by **Jofae** - CC0 1.0 (public domain) - https://freesound.org/people/Jofae/sounds/387132/
- #402845 "Espresso Machine (Automatic)" by **BageBoy** - CC0 1.0 (public domain) - https://freesound.org/people/BageBoy/sounds/402845/
- #405114 "WoodType_1_Footstep_Sneakers.wav" by **monte32** - CC0 1.0 (public domain) - https://freesound.org/people/monte32/sounds/405114/
- #407051 "crowd ext light students on covered concrete path of university campus could be courtyard boomy voices echo scratchy steps kinda too close for ambience Mbale, Uganda, Africa 2016.wav" by **kyles** - CC0 1.0 (public domain) - https://freesound.org/people/kyles/sounds/407051/
- #447931 "Unfold a map" by **Breviceps** - CC0 1.0 (public domain) - https://freesound.org/people/Breviceps/sounds/447931/
- #448673 "Soda Machine Bottle Drop (Binaural).wav" by **courter** - CC0 1.0 (public domain) - https://freesound.org/people/courter/sounds/448673/
- #451924 "room tone large room church basement heavy deep ventilation or furnace hum.flac" by **kyles** - CC0 1.0 (public domain) - https://freesound.org/people/kyles/sounds/451924/
- #454165 "room tone large convention room heavy ventilation +light crowd Palais des Congres Montreal, Canada2.flac" by **kyles** - CC0 1.0 (public domain) - https://freesound.org/people/kyles/sounds/454165/
- #455828 "room tone small room with computer fans in open enclosure.flac" by **kyles** - CC0 1.0 (public domain) - https://freesound.org/people/kyles/sounds/455828/
- #476119 "Steps: Sneakers on Grass" by **Sheyvan** - CC0 1.0 (public domain) - https://freesound.org/people/Sheyvan/sounds/476119/
- #489424 "Typing on a keyboard" by **SamsterBirdies** - CC0 1.0 (public domain) - https://freesound.org/people/SamsterBirdies/sounds/489424/
- #503427 "Coffee Grinder HQ.wav" by **tosha73** - CC0 1.0 (public domain) - https://freesound.org/people/tosha73/sounds/503427/
- #509682 "town or city, Warsaw University main campus, coronavirus quarantine, birds sing, pigeons, dusk, spring, 5 o'clock chime, bells, very sparse people, spring, Poland.wav" by **be_a_hero_not_a_patriot** - CC0 1.0 (public domain) - https://freesound.org/people/be_a_hero_not_a_patriot/sounds/509682/
- #513729 "ambiance rue stereo.wav" by **transeman** - CC0 1.0 (public domain) - https://freesound.org/people/transeman/sounds/513729/
- #521558 "blackbird-evening.wav" by **echobones** - CC0 1.0 (public domain) - https://freesound.org/people/echobones/sounds/521558/
- #523959 "moped pass by.wav" by **lartti** - CC0 1.0 (public domain) - https://freesound.org/people/lartti/sounds/523959/
- #537473 "typing real words on a computer keyboard.m4a" by **MoralX** - CC0 1.0 (public domain) - https://freesound.org/people/MoralX/sounds/537473/
- #546826 "Footsteps Sneaker Linoleum" by **Kinoton** - CC0 1.0 (public domain) - https://freesound.org/people/Kinoton/sounds/546826/
- #625112 "Crowd at Cafeteria" by **sonically_sound** - CC0 1.0 (public domain) - https://freesound.org/people/sonically_sound/sounds/625112/
- #637479 "door metal institutional push bar open close.flac" by **kyles** - CC0 1.0 (public domain) - https://freesound.org/people/kyles/sounds/637479/
- #637804 "room tone office hallway heavy ventilation.flac" by **kyles** - CC0 1.0 (public domain) - https://freesound.org/people/kyles/sounds/637804/
- #713428 "Foley Zapatillas o Crocs Calle" by **StarfunkBoogie** - CC0 1.0 (public domain) - https://freesound.org/people/StarfunkBoogie/sounds/713428/
- #730438 "Vending Machine Hum" by **HECKFRICKER** - CC0 1.0 (public domain) - https://freesound.org/people/HECKFRICKER/sounds/730438/
- #733849 "Walla Crowd Inside French" by **Salomé_Lubczanski** - CC0 1.0 (public domain) - https://freesound.org/people/Salom%C3%A9_Lubczanski/sounds/733849/
- #741283 "Crowd walla (french english) EXT" by **xkeril** - CC0 1.0 (public domain) - https://freesound.org/people/xkeril/sounds/741283/
- #752709 "Voice_Crowd_Small_Expression_Applause_Cheer_Stereo" by **Nox_Sound** - CC0 1.0 (public domain) - https://freesound.org/people/Nox_Sound/sounds/752709/
- #763462 "zipper on backpack - 1" by **FOSSarts** - CC0 1.0 (public domain) - https://freesound.org/people/FOSSarts/sounds/763462/
- #767051 "Office chair creaking" by **ThabzMalik** - CC0 1.0 (public domain) - https://freesound.org/people/ThabzMalik/sounds/767051/
- #849797 "Metal Rattles" by **IENBA** - CC0 1.0 (public domain) - https://freesound.org/people/IENBA/sounds/849797/
- #863017 "Footsteps - very slow walking in trainers on hardwood floor" by **lreeve** - CC0 1.0 (public domain) - https://freesound.org/people/lreeve/sounds/863017/

### Kenney (CC0, https://kenney.nl)

- impact-sounds - https://kenney.nl/assets/impact-sounds - Creative Commons Zero (CC0)
- rpg-audio - https://kenney.nl/assets/rpg-audio - Creative Commons Zero (CC0)

### Kevin MacLeod (incompetech.com, CC BY 4.0)

- "Almost Bliss" - https://incompetech.com/music/royalty-free/mp3-royaltyfree/Almost%20Bliss.mp3
- "Evening" - https://incompetech.com/music/royalty-free/mp3-royaltyfree/Evening.mp3
- "Morning" - https://incompetech.com/music/royalty-free/mp3-royaltyfree/Morning.mp3
- "Raving Energy" - https://incompetech.com/music/royalty-free/mp3-royaltyfree/Raving%20Energy.mp3
- "Sneaky Snitch" - https://incompetech.com/music/royalty-free/mp3-royaltyfree/Sneaky%20Snitch.mp3
- "Study And Relax" - https://incompetech.com/music/royalty-free/mp3-royaltyfree/Study%20And%20Relax.mp3
