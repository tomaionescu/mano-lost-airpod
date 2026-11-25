# Mano & the Lost AirPod: game design

This document describes the game as designed and as built: the story, the chapters, the minigames, the mood, the
UI, the map, the opening, the campus and the music. Where a part of the design is not built yet, the text says so
and the backlog in §12 gives its status.

Code comments cite sections of this document by number (§3.5, §4.1) and backlog items by id (V2-14), so both are
stable. The ids carry a V2 prefix because this design is the game's second, longer version.

Related documents: [ARCHITECTURE.md](ARCHITECTURE.md) (how the code is organised), [PIPELINE.md](PIPELINE.md)
(how characters, campus, audio and video are built), [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md) (how the real campus was
mapped), [ART_DIRECTION.md](ART_DIRECTION.md) (look, UI and sound in detail), [STATUS.md](STATUS.md) (what is
finished and what is known to be wrong) and the [README](../README.md).

## 0. Design decisions at a glance

| Topic | Decision | Reason |
|---|---|---|
| When the story happens | Thursday 15 October 2026, 17:42 to 00:25 | At 17:42 in mid-October the sun is 11.5° above the horizon, which gives a golden hour at the moment Mano wakes up, and it sets at 19:02, inside the story. |
| Sun direction | The real one, in the campus frame (+X along rue Pasteur toward bearing 76.4°) | The light then falls on the real facades at the real times, and at 18:55 the sun sits on the axis of rue Pasteur. |
| UI | Mano's school notebook, in his pen, with clean print for subtitles and settings | The interface belongs to the character. EPITA's own typefaces appear only on EPITA's objects in the world. |
| Paper colour | White school paper, #FAF8F2 | French school notebooks are white; a cream tone reads as a stock "paper" texture. |
| Campus map | A 5 mm grid sheet taped into the notebook, drawn from the level's own footprints | Exact geometry with hand-drawn marks, and the journal and the map are one object. |
| Lettering | Typeset or hand-drawn, never generated | Generated letters are the most recognisable flaw of generated images. |
| Characters | Built with MPFB and fitted to each friend ([PIPELINE.md](PIPELINE.md)) | Close-ups need a full rig and 52 face shapes for blinking, lip movement and expressions. |
| Ishita's photo challenge | A disposable film camera; the prints appear only in the credits | A delay between the shot and the print belongs to this game. An instant camera is another game's signature (§4.9). |
| The phone | Dies on screen at 17:43, comes back charged in chapter 3 with every missed message | The dead phone explains why Mano cannot simply locate the AirPod, and the flood of messages shows him what he missed. |
| Dialogue | Plain-text `.dlg` files with conditions, jumps and commands, read by the game's own parser | Lines can be written and reviewed without touching code, and a validator checks every cue, flag and speaker. |
| Baked lighting | None | The game has six times of day, so global illumination stays real-time (SDFGI). |
| Title screen | The live Amphi 4 at 17:41 with Mano asleep | The title is the minute before the story starts. |

## 1. Vision

A one-evening story of about fifty minutes on the main path, longer with the optional content, set on the EPITA
campus in Le Kremlin-Bicêtre on Thursday 15 October 2026. Mano wakes in Amphi 4 at 17:42 with one AirPod and chases
the other one until just after midnight, through a campus built on its real footprints, while the light runs out:
the sun lines up with rue Pasteur at 18:55 and sets at 19:02, a thin crescent moon follows it down at 21:09, and the
rest of the night is moonless under an orange-grey city sky.

The mood borrows from Life is Strange and leaves its mechanics alone: a camera that lingers, six optional sit-downs
with a song, Mano's handwritten thoughts on about ninety things, friends who talk to each other and text him, and a
UI that is his Seyès notebook in blue ballpoint.

Eight friends appear: Mano, Toma, Anisha, Ian, Silvia, Ishita, Cristina and Joaquin. Each has something they want
tonight and a sincere moment of their own. The AirPod turns up at the end of chapter 4, so the finale on the cour Pasteur
steps is about people: Mano offers one AirPod to a friend the player chooses. The *plink* comes after the credits.

## 2. Pillars

The premise is a comic hunt with fair clues. Toma describes the AirPod at the start (an "M" scratched on it, a
chewed stem), and that description is the proof Cristina asks for four chapters later.

The antagonists are comic and fair. Karim plays "finders keepers, BDE rules" and then lends his charging strip.
Mme Dupont will not open the lost & found before her second coffee. ACU Léo confiscates pastries in SM14 and ends
the night with "I saw nothing."

There is always something to collect or play with: golden rubber ducks, Ishita's film, the sit-downs, a photo
mode and a wardrobe of fits. Conversations are filmed, with shot and reverse shot, the 180° rule and a 2.39:1
letterbox, and the world is lit by the real sun of that evening.

## 3. Story and structure

### 3.1 Date, clock and light

The story happens on Thursday 15 October 2026. The lecture slide's "QCM vendredi 9h" is the next morning. Sun
positions come from the NOAA solar equations and moon positions from the suncalc model, for 48.8154 N, 2.3631 E
in Central European Summer Time.

| Clock | Sun | What it means on screen |
|---|---|---|
| 17:42 | azimuth 242.3°, elevation 11.5° | Golden hour. The courtyard is already in the shadow of the X building; KB1's white front on rue Pasteur takes grazing gold light. |
| 18:15 | 248.9°, 6.6° | The gold climbs the facades. |
| 18:50 | 255.6°, 1.3° | Only upper floors and the sky keep the light. |
| 18:55 | 256.5°, 0.6° | The sun sits on the axis of rue Pasteur (256.4°). |
| 19:02 | sunset | |
| 19:25 | 4.6° below the horizon | Blue hour. A waxing crescent moon, 24 % lit, hangs low in the south-south-west. |
| 21:09 | | The moon sets. The rest of the night is moonless. |

| Ch. | Title | In-game time | Light presets (§4.4) |
|---|---|---|---|
| 0 | *23:41* (cold open) | 23:41 | `late` |
| 1 | Mono | 17:42 to 18:29 | `golden`, then `late_gold` |
| 2 | Lost & Found | 18:30 to 19:04 | `late_gold`, then `last_light` |
| 3 | Blue Hour | 19:10 to 20:44 | `blue`, then `night` |
| 4 | Sauce Samouraï | 21:00 to 23:40 | `night`, then `late` |
| 5 | Stereo | 23:41 to 00:10 | `late` |
| | post-credits | 00:25 | `late` |

The story sets the clock at its beats (`$ clock 18:15`). Between beats it advances three game minutes per minute
of play, and each chapter lists holds so that walking around never carries the clock past a beat pinned to a time.
A light preset changes only under a chapter card, a fade or a cut, never as a visible time-lapse. Chapters, clock
and presets are data in `data/chapters.json`.

### 3.2 The pitch and the emotional line

> On a Thursday in mid-October, Mano wakes up in Amphi 4 with one AirPod. By midnight he has chased the other one
> through every corner of the campus, and found out what everyone was doing while he wasn't listening.

Mano always has one AirPod in: half music, half world, and the music usually wins. He is the friend who is present
and tuned out, which is why the first chapter is called "Mono".

The hunt makes him listen. Each friend's errand hides something that matters to them, and the group chat he missed
while his phone was dead shows what everyone was going through.

The AirPod is found at the end of chapter 4. Minutes later Mano puts both AirPods in the case to go and help
Anisha. In chapter 5 he gives one away and shares a song: "Music in one ear. Them in the other."

### 3.3 What really happened

The hidden timeline keeps every clue fair.

| Time | What happened | How the player learns it |
|---|---|---|
| During the lecture | The right AirPod (M scratch, chewed stem) ends up by Mano's seat in Amphi 4 while he sleeps. Karim (BDE), flyering the lecture for the party, picks it up. Anisha sees it before leaving early. | A blurred figure with flyers bends near the seats in the wake-up shot. Anisha tells Mano in chapter 1. |
| Before 18:10 | Karim drops it through the slot of the lost & found box at the KB1 accueil. | Karim admits it after babyfoot in chapter 2. |
| 18:10 | Cristina brings Mme Dupont a coffee, gets the box opened, and takes the M one to find its owner, leaving a note signed "C." | The empty slot and the note in chapter 2. Mme Dupont now wants her *second* coffee. |
| 18:20 | Cristina posts in the promo chat: found an AirPod, an M scratched on it, chewed stem, owner? | The message flood in chapter 3. Mano's phone has been dead since 17:43. |
| 19:12 to 19:15 | Cristina waits in the cafeteria, leaves a note by the till, and goes to the Under. | The finder app says "cafeteria, 19:12". The note is five minutes old when Mano reads it. |
| About 19:20 | Cristina asks Karim for "M." in the Under and is put on BDE errands with Chloé. | Karim, in chapter 3, then Cristina's text. |
| 20:31 | Waiting on the Under's sofa, Cristina loses the AirPod between the cushions. | The finder app in chapter 4: "the Under, 20:31", then the sound search. |
| 21:00 | Cristina and Joaquin meet Mano at rue Pasteur's east end. | Chapter 4. |

### 3.4 The chapters at a glance

Main-path minutes are estimates, computed from the number of dialogue cards at a reading pace, the walking
distances and the length of each minigame. Optional content adds roughly half an hour.

| Ch. | Main path (min, est.) | Spotlight | Activities | Quiet beat | Ends on |
|---|---|---|---|---|---|
| 0 | under 1 | all eight, on the steps | | | "Six hours earlier." |
| 1 | 9 | Toma, Ian and Silvia, Ishita, Anisha | the pastry war; walking Ishita to SM14; moulinette | KB1's lobby, by the glass | "Karim has it." |
| 2 | 13 | Karim, Joaquin, Mme Dupont | babyfoot 1v1 or 2v2; coffee machine; lost & found | KB1's planter wall at 18:55 | the note signed "C." and the sunset |
| 3 | 12 | Cristina (near-misses), Ishita, Ian and Silvia, Toma | the message flood and the finder; a tour of three places out of six; the pastry summit; the playlist pick | the courtyard steps; the Under's sofa | Joaquin: "21:00. Memory on." |
| 4 | 15 | Joaquin, Cristina, Anisha | kebab orders; sound search; "1, 2, 3, ACU!"; night moulinette | KB1's stairwell | "MOULINETTE: OK" and the steps |
| 5 | 4 | everyone | the group photo; who gets the other AirPod | the steps, with friends | credits, then the *plink* |
| | about 50 | | | | |

Chapter 5 is short by design: it has no errand and consists of the night's payoffs.

### 3.5 Chapter by chapter

Every goal is a to-do line in Mano's voice with a reason ("Help Anisha beat the moulinette. Then she talks."). The
HUD shows only the main line; the journal shows the whole list with the finished lines struck through. At most one
main and two optional lines are active at a time and there are never three fetch steps in a row; the headless quest
test checks both. Optional content (sit-downs, ducks, photo spots, side stories) is listed in §3.8, §3.9 and §4.1.

Cold open, "23:41". The cour Pasteur steps at night under Toma's fairy lights. Three shots: a wide of the eight on
the steps; Mano's open palm holding out one AirPod while he says "Want one?"; his face lit by his phone, and a
freeze. A thought, "Okay. How did I get here?", then "Six hours earlier." Who the AirPod is offered to is not shown
until the final choice. A chapter-select replay skips the cold open and the dream.

Chapter 1, "Mono" (17:42 to 18:29).

1. The chapter card writes "jeudi 15 octobre / 17:42 / Amphi 4", then the dream clip (§7) and the wake-up. A
   blurred Karim bends near the seats. Mano's phone, at 1 %, shows two message previews (Toma: "tonight 23:00, the
   steps. you're on speaker + playlist"; Anisha: "KO KO KO") and dies on screen at 17:43.
2. Toma describes the AirPod, then: "Tonight. 23:00. The steps. You promised." Mano does not remember what he
   promised, and Toma will not say. Toma sends him to Anisha in SM14, who "sees everything". Mano's thought: "Left
   ear only. This is a crime."
3. Outside the amphi, Ian calls out "Mano! Settle this." The pastry war (pain au chocolat or chocolatine) sits on
   the main path, with a third answer that dodges it.
4. In the passage, Ishita is looking for SM14, and Mano, for once, knows the way. She walks behind him across rue
   Pasteur and up the stairs.
5. At SM14 she lends him her disposable camera for a photo-club challenge: ten photos of campus life tonight, back
   to her at 23:00 on the steps. From her he learns he is "the playlist" for Toma's plan. Photo spots open.
6. Anisha's moulinette, then Anisha's sincere moment, then the clue (Karim picked up something white by Mano's
   seat) and a euro for the coffee machine. ACU Léo confiscates Inès's chocolatine, which sets up chapter 4.

The chapter ends when the moulinette passes. The optional to-dos "Remember what I promised Toma" and "Charge my
phone" carry over into the next chapters.

Chapter 2, "Lost & Found" (18:30 to 19:04).

1. The Under. Joaquin, new this year, has lost to Karim four times and calls it data. Babyfoot against Karim, alone
   or with a partner: the pastry ally, Joaquin, or nobody. Karim admits he dropped the AirPod at the lost & found.
   Mano's phone goes on the BDE's charging strip for an hour. Joaquin's tip for later: hit the left side of the
   coffee machine.
2. The coffee law. The accueil has a "back in 5 min" note. Mme Dupont is in the cafeteria and will not open the box
   before her second coffee. The machine costs two euros: Anisha's euro and one from the Under's sofa.
3. The lost & found. Five joke AirPods and an empty slot with a note: "Took the M one to find its owner. C." No pod
   is the right one. Mme Dupont remembers a polite new student who brought the first coffee. The journal gains "C.
   took my AirPod to give it back to me. Who is C.?"
4. Rue Pasteur at 18:55. The sun is on the axis of the street and the street lamps come on. If Mano invited the
   survivor, he is there to see it. A film photo and the planter-wall sit-down are offered.

Mano's closing thought: "Somebody's been looking for me all evening. That's... new."

Chapter 3, "Blue Hour" (19:10 to 20:44).

1. The chapter opens at the Under's bar. Karim hands back the phone, charged, and the missed messages land: 43 at
   once, readable or skippable. The promise was the playlist, one song for the end of the night. C. is Cristina.
   The finder app says "cafeteria, 19:12".
2. Near-misses. Cristina's note by the cafeteria till says they waited until 19:15 and went to the Under; it is
   19:20 and Mano has just come from there. Karim saw Cristina five minutes ago. Then a text from an unknown
   number: "At the kebab with Joaquin at 21:00. Bring proof it's yours." Cristina is never on screen in this
   chapter.
3. Ishita's tour. She follows Mano and asks for three places that matter to him, out of six: his amphi seat, the
   Under's sofa, the sticker column, the bike rack, the vending machines, KB1's glass bays. Each stop has a memory
   from Mano, her reaction and an optional film photo. Her favourite comes back in chapter 5.
4. The pastry summit in the cafeteria. The argument was about a shared report. Mano buys the last pastry of the day
   and splits it: "It's the same pastry." The chapter 1 choice decides who apologises first.
5. The playlist with Toma on the steps. Three songs, each previewed for ten seconds; the pick plays in the finale
   and under the credits. Then Toma's sincere moment about why tonight matters.
6. Rue Pasteur's east end at 20:40, under a fade to night. The group chat: "21:00. Memory on."

The tour, the summit and the playlist can be done in any order.

Chapter 4, "Sauce Samouraï" (21:00 to 23:40).

1. Mano meets Cristina and Joaquin: "You're C.?" / "You're M.?" The proof is the left AirPod, with the same M and
   the same chewed stem. Joaquin is captain of the kebab run for the steps, Mano is "the memory", and the order
   minigame follows. The kebab shop itself is round the corner and never shown.
2. Joaquin's sincere moment. Then the handover: Cristina's pocket is empty. The finder app says "the Under, 20:31".
   Joaquin takes the food to the steps and Cristina follows Mano back to the Under.
3. The sound search during the BDE's sound check. The AirPod is between the sofa's cushions, next to the fossilised
   chip. A "Stereo" banner, a few seconds of music in both ears, and Cristina's sincere moment.
4. Anisha's SOS lands on top of the music: exercise five, deadline 23:42, starving. Mano puts both AirPods in the
   case. This is the turn of the story.
5. "1, 2, 3, ACU!": the kebab goes into SM14 past ACU Léo. A cut to 23:05, then the night moulinette, which says OK
   at 23:38. Anisha's second sincere moment, then "The steps. Now."

Chapter 5, "Stereo" (23:41 to 00:10).

1. All eight on the steps, 41 minutes late for Toma's plan, with a reason. The night's payoffs play as short lines,
   each with a fallback: the pastry, the wrong sauces, Ishita's favourite place, Anisha's submission, the proof,
   the babyfoot partner, Chloé's list, the ducks, the survivor.
2. Toma's toast to the three new ones.
3. The group photo: the last exposure on Ishita's camera, framed by the game, followed by Ishita's sincere moment.
4. Free play on the steps: an optional last sit-down, then "Want one?" to any of the seven. Each friend has their
   own reply. The playlist song plays.
5. Credits: the camera rises from the steps over the courtyard toward rue Pasteur and KB1's lit windows, the names
   go up the right of the screen and the night's film prints up the left, for 46 seconds.
6. Post-credits, 00:25. Mano alone on rue Pasteur puts both AirPods back in. *plink*, a drain grate, "Where is my
   OTHER one." Mme Dupont, locking up: "Not my problem, sweetie."
7. The recap on the notebook's last page ("à suivre…" and one pen line per choice that mattered), then "Keep
   exploring" on the campus at night, or the title.

### 3.6 The friends' roles

| Character | Role tonight | Wants | Activity | Paid off in |
|---|---|---|---|---|
| Mano (player) | from mono to stereo | his AirPod | everything | the "Want one?" choice |
| Toma | organiser; the voice of the group chat | a welcome night on the steps at 23:00 | the playlist pick (ch. 3), the toast (ch. 5) | the finale song |
| Anisha | under a 23:42 deadline | the moulinette to say OK | moulinette (ch. 1), the kebab delivery and the night moulinette (ch. 4) | "Submitted at 23:38" |
| Ian and Silvia | a comic duo with a real argument underneath | to win the pastry war | pastry war (ch. 1), babyfoot partner (ch. 2), summit (ch. 3) | the shared pastry bag (ch. 5) |
| Ishita | new this year; sees the campus with fresh eyes | ten photos for the photo club | the walk to SM14 (ch. 1), the tour (ch. 3), the film | her favourite place; the prints in the credits |
| Cristina | new this year; has been trying to help all night | to give the AirPod back | notes and near-misses (ch. 3), the sound search (ch. 4) | the proof, the finale |
| Joaquin | new this year; rival turned teammate | to beat Karim; to feed everyone | babyfoot partner (ch. 2), kebab captain (ch. 4) | the sauce jokes (ch. 5) |
| Karim (BDE) | comic antagonist, then host | | babyfoot | the sound check, the party |
| Mme Dupont | the coffee law | her second coffee | coffee; lost & found | locking up after the credits |
| ACU Léo | the rules | | "1, 2, 3, ACU!" | "I saw nothing." |

The side cast is fictional: Chloé, Théo, Yanis, Inès, M. Bernard, the sleeping SUP, the piscine survivor, the
waiting student and the duck whisperer.

Every friend other than Mano has a sincere moment, placed right after a win or a laugh and closed with a small
joke so that nobody feels exposed. Anisha has two, and Ian and Silvia share theirs. In the dialogue files a
`[slot]` tag marks a line written in a friend's own voice, and the validator lists those lines per person.

### 3.7 Ten small choices and where they pay off

| # | Choice | When | Payoff |
|---|---|---|---|
| 1 | Pain au chocolat, chocolatine, or neither | Ch. 1 | which of Ian and Silvia can be the babyfoot partner; who apologises first at the summit; the journal and the recap |
| 2 | Invite the piscine survivor out before the lost & found twist | Ch. 1 and 2 | he watches the sunset at the planter wall and is in the courtyard in chapter 5 |
| 3 | Wake the sleeping SUP with a spare coffee or the air horn | Ch. 2 | in chapter 4 he passed his soutenance, or he asks "Did I miss it?" |
| 4 | Babyfoot partner: Ian or Silvia, Joaquin, or alone | Ch. 2 | banter during the match; a line on the steps; the recap |
| 5 | Sign Chloé's sheet for the Halloween party | Ch. 2 | a line from Toma on the steps |
| 6 | The three places shown to Ishita | Ch. 3 | her favourite on the steps and in the recap |
| 7 | The playlist song, one of three | Ch. 3 | the finale and credits song |
| 8 | Replies in three chat threads: sincere, joking, or silence | Ch. 3 | Toma's lines at the playlist; Cristina's first lines in chapter 4 |
| 9 | The kebab orders, from how the minigame went | Ch. 4 | the sauce jokes on the steps |
| 10 | Who gets the other AirPod, any of the seven | Ch. 5 | that friend's reply, a thought in the post-credits, the recap |

A sticky note with a pencil tick ("Ishita will remember that.") appears after the tour, the playlist, Cristina's
moment and Anisha's.

### 3.8 Collectibles

| Type | Count | Reward |
|---|---|---|
| Golden ducks | 12, split 3/3/2/2/2 over chapters 1 to 5; two night ones glow | eight unlock the merch fit; twelve add a journal page of rubber-duck debugging tips, a line on the steps, and "duck zero" from the student who hid them |
| Ishita's film photos | 10 spots plus the group photo | a count per chapter in the journal; the prints, faded and grainy, run under the credits |
| Moments (sit-downs, §4.1) | 6 | one journal line each in Mano's voice; an extra thought after the sixth |

A photo spot is taken in photo mode by standing near it and framing it, or in the story when Mano is offered the
shot (the tour stops, the sunset). The film has exactly as many exposures as there are spots, and a spot is never
taken twice. Chapter select shows what each chapter still holds. A fourth type, club stickers, is an idea that is
not built.

### 3.9 Side stories

Four optional stories of two to five minutes each, found by walking past them.

1. "Back in 5 min". A student has waited at the accueil since 9:00, is served once Mme Dupont has her coffee, and
   says goodnight in chapter 4.
2. "Is the sun still yellow?" The piscine survivor in SM14 has not been outside since 8:00. Asked before the lost &
   found twist, he comes to the planter wall for the 18:55 sun. After the twist it is too late.
3. "Segmentation fault (core dumped)". The SUP asleep in Amphi 4 has a soutenance at 19:00. He can be woken in
   chapter 2 with a spare coffee or the BDE's babyfoot air horn.
4. "The duck whisperer". The student who hid the ducks gives a hint from four ducks on and a reward at twelve.

Two further ideas are not built: the bike rack's flat tyres as a quest, and a hackathon with free pizza in SM15.

### 3.10 Minigames

The rules come from who plays: the friends themselves, not all of whom play games. A minigame lasts about
ninety seconds, uses one or two inputs, shows its controls on screen and never blocks the story. Failing is short
and funny, and after repeated failures a friend steps in. Each chapter introduces at least one new activity, and
the second chapter carries a high point (babyfoot), because players who give up on a short episodic game tend to do
so right after its first chapter.

All minigames implement `setup(game, opts, done)` and are started from dialogue with `$ minigame <name>`.

| Minigame | Ch. | Play | Help when it goes wrong | File |
|---|---|---|---|---|
| Moulinette, day | 1 | Three rounds of 30 s. A short C function is shown in a tiled terminal; point at the buggy line. A miss costs 6 s. | A failed run ends on "-42" and a retry. | `scripts/minigames/moulinette.gd` |
| Babyfoot | 2 | First to three goals against Karim. In 2v2 Mano works the attack rod and the partner the goal. | Karim is 12 % slower for every game lost, never below 60 %. After two losses the partner says "Switch", takes the attack and scores. | `babyfoot.gd` |
| Coffee machine | 2 | The machine ate the coins: mash E or Space for six seconds to shake it loose. | With Joaquin's tip every shake counts for more. A failed try keeps the coins in the machine. | `coffee.gd` |
| Lost & found | 2 | Inspect five joke AirPods and an empty slot with a note. | There is no right pod by design. After three wrong picks Mme Dupont points at the empty slot. | `lostfound.gd` |
| Kebab orders | 4 | Three rounds from `data/kebab.json`. A ticket shows a friend's name and order (base, sauce, extra) for about 2.5 s; Mano rebuilds it from the menu. In the last round the cook reads all eight orders back and Mano says right or wrong. | Nothing fails. After two wrong tickets Cristina pencils a line under the right word. Wrong orders become jokes in chapter 5. | `kebab.gd` |
| Sound search | 4 | Walk the Under with the finder open. Each ring is a 3D chirp from the AirPod, with a 4 s cooldown and five rings of battery. A ring timed between the sound check's thumps is clear; one under a thump is drowned out. | A five-step signal bar gives the distance without sound. Cristina's phone takes over when the battery is gone, Cristina hints at the sofa after 40 s, and the AirPod catches the light after 70 s. | `findmy.gd` |
| "1, 2, 3, ACU!" | 4 | The playground game "1, 2, 3, soleil" in SM14. Hold forward to sneak round the desks while Léo's back is turned; let go when his footsteps stop and he says "hm?". | Being caught costs a few metres. After three catches Léo gives up and stays at the board. | `soleil.gd` |
| Moulinette, night | 4 | The same game with a coding-style round in the middle (a cast on `malloc`, a `goto`, a fifth argument). A miss costs 4 s. | Anisha gives a hint after 12 s on a round, and takes the keyboard after two failed runs. The night always ends on OK. | `moulinette.gd` |

The moulinette window is an i3-style tiled terminal with square corners, because EPITA's lab machines run NixOS
with i3.

### 3.11 Pacing

The main path alternates talking, exploring, playing and a quiet moment, with one peak per chapter and a valley
after it.

| Ch. | Peak | Valley or turn |
|---|---|---|
| 1 | the moulinette | Anisha's moment; the lobby sit-down |
| 2 | babyfoot | the note signed "C."; the sunset on the street |
| 3 | the phone floods | the tour, the pastry summit, the playlist |
| 4 | kebab orders, then the AirPod found | Anisha's SOS and the AirPods in the case, which is the turn of the story |
| 5 | the choice on the steps | the credits, then the *plink* as a last laugh |

The length follows from the audience. The players are the friends, who play in one evening and want to reach
their own scene. Every friend is therefore on screen, or present through a note or a message, within the first
half hour, and each chapter is a natural stopping point with a save under its card.

The campus is kept small on purpose. The same streets and rooms come back under six lights, with different people
and different lines, so the game grows in time while the map stays the same size.

### 3.12 Writing rules

Mano's inner voice is first person, handwritten, at most two short sentences: observant, warm, self-deprecating.
About 60 % of his look-at lines are funny, 25 % observational and 15 % wistful.

Friends speak in their own phrases. A conversation is mostly laughs, with the sincere moments kept rare.

The dialogue is English and keeps the campus's French words: piscine, moulinette, soutenance, promo, the sauces.
Dates in the notebook are French ("jeudi 15 octobre") and times use the 24-hour clock. The chat has no emoji;
friends use words.

A subtitle card is at most two lines of about 40 characters. A headless check
(`scenes/dev/line_check.tscn`) lays out every card and fails on a third line.

The story data holds 213 cues and about 1,030 dialogue cards, 88 look-at spots, 56 chat messages and 12 overheard
conversations.

## 4. The Life is Strange mood

### 4.1 "AirPod moments": six optional sit-downs

A sit-down is a place where Mano can sit, a song comes up, the camera drifts, and nothing asks him to get up.

| Id | Ch. | Available | Place | Song | Thought |
|---|---|---|---|---|---|
| `sit_bay` | 1 | 17:43 to 18:29 | KB1's lobby, by the glass bays on rue Pasteur | "Morning" | "Rue Pasteur through the glass, all gold. A low-budget film. Still a film." |
| `sit_planter` | 2 | offered at 18:55 | KB1's planter wall, looking down the street at the sun | "Evening" | "Seven minutes of sun left. I'm spending them sitting down. Growth." |
| `sit_steps` | 3 | 19:10 to 20:44 | the courtyard steps as the fairy lights come up | "Almost Bliss" | "Everyone's phone lit up at 18:20. Mine was dead. Story of my night." |
| `sit_sofa` | 3 | 19:10 to 20:44 | the Under's old sofa (on a replay, the player knows what it will swallow) | "Study And Relax" | "This sofa has seen more of the BDE than the BDE has." |
| `sit_stairs` | 4 | after the night moulinette | KB1's stairwell, on the way down | "Morning" | "Both AirPods in the case. The music's coming out of my phone, tiny. Still counts." |
| `sit_final` | 5 | after the group photo | the steps, with friends around | the playlist pick | "One day this will just be 'that school I went to'. Tonight it's the whole world." |

Sitting is one key press. The HUD hides and the picture dips to black for a third of a second while Mano is put on
the seat. Any input stands him up again, and nothing forces him to.

Each sit-down has up to three cameras, stored in `data/world.json`. Camera A is a three-quarter medium at 34°, held
for six seconds. The shot then blends over eight seconds to camera B, a wide at 44° with Mano small in frame, which
orbits slowly or creeps along a line. Camera C, where present, is a four-second detail at 20°.

The song rises from silence over about three and a half seconds while the room's ambience drops, and the
handwritten thought appears two and a half seconds in. Standing up fades the song out. Sitting again resumes it
where it stopped. Each sit-down writes one line in the journal's *moments* tab.

All six songs are currently Kevin MacLeod tracks; §9 covers the planned soundtrack.

### 4.2 Inner voice everywhere

A speaker id `think` carries Mano's thoughts: his handwriting in film white with an outline, no name. A thought
shown while walking is a "bark". It stays for 2.2 s plus 0.05 s per character and never takes the controls. The
narrator voice is kept only for stage sounds such as *plink* and *CLUNK*.

The campus has 88 spots with a thought attached, 74 in `data/world.json` and 14 placed in the level. Each has a
kind that sets the prompt's verb: look, read, listen or grab. About a
quarter have a second line after sunset. Ten of the read spots open a narrow insert shot on what is read.

The wistful lines come from general student feelings: tiredness, deadlines, the campus as a second home. They never
invent private details about real people.

### 4.3 One AirPod: the sound of the whole game

The lost AirPod is the right one, so the design has Mano hear only the left half of every non-diegetic cue until
it is found.

This is planned (V2-12) and not built. Today all music plays in stereo, and the moment the AirPod is found is a
banner, a fanfare and eight seconds of the exploration track.

The planned implementation splits each song offline into a left-only and a right-only file and plays both through
one `AudioStreamSynchronized`, whose per-stream volume lets the right half be faded in or cut live.

In the design, the title and the credits play in full stereo, so nobody thinks their headphones are broken. From
chapter 1 until the AirPod is found, every non-diegetic cue plays in the left ear only, while ambience and voices
stay normal. When it is found, the right half fades in over two seconds. Once both AirPods are in the case there is
no earbud music, only music that exists in the world. In chapter 5 the shared song keeps to the left ear with the
friends' voices on the right, and in the post-credits the right half cuts out at the *plink*.

A "Mono audio" setting sends both halves to both ears.

### 4.4 The light runs out

Six presets in `scripts/level/world_env.gd` (`TIMES`), each a set of differences from the golden-hour defaults.

| Preset | Clock | Sun and moon | Sun colour, energy, angular size | Ambient | Lamps | Lit windows | Grade |
|---|---|---|---|---|---|---|---|
| `golden` | 17:42 | sun 242.3°, 11.5° up | (1.0, 0.74, 0.52), 2.6, 0.8° | 0.75 | string lights 30 %, classrooms on | off | warm highlights, slightly desaturated greens |
| `late_gold` | 18:15 | sun 248.9°, 6.6° | (1.0, 0.63, 0.40), 1.9, 1.0° | 0.62 | string lights 60 % | 0.3 | more amber |
| `last_light` | 18:50 | sun 255.6°, 1.3° | (1.0, 0.50, 0.32), 0.9, 1.4° | 0.50 | street lamps and string lights on | 0.8 | coral highlights, indigo shadows |
| `blue` | 19:25 | sun down; crescent moon at 205.6°, 8.9° | | 0.60, tinted blue | all on | 1.5 | cool, warm only at lamps |
| `night` | 21:30 | no sun, no moon | | 0.20 | all on | 1.5 | deep blue with warm pools |
| `late` | 23:45 | none | | 0.18 | all on | 1.2 | as `night`, warmer highlights |

`WorldEnv.apply_time()` tweens the sun, the ambient light, the fog, the sky and the grade, and dims the lamp groups
and window emission that the level binder finds. The light never comes from lower than 2° of elevation, to avoid
shadow acne on a grazing sun, while the sky keeps the sun's true position.

The sky is a shader (`scripts/fx/sky_blend.gdshader`) that blends two Poly Haven HDRIs for the daylight presets,
each turned so its own sun sits on the real sun's bearing, into a procedural twilight and night sky with a city
glow, a few stars and the crescent moon.

Lamps are grouped as street lamps, string lights and classroom panels. Early in the evening the light is warm
outside and cool inside; after sunset it is the other way round.

Windows of rooms the player never enters use an interior-mapping shader (`scripts/fx/interior.gdshader`) and light
up after dark.

The colour grade is a lookup table rebuilt per preset from a handful of parameters (lift, shadow and highlight
tint, green desaturation, contrast curve).

With the real sun and the real buildings, cour Pasteur has no direct sun at 17:42. The gold lives on KB1's street
front, the upper floors and the sky, and Mano says so on his way to SM14: "KB1 gets all the gold. The courtyard
gets the shade."

### 4.5 Camera grammar

Fields of view are vertical.

| Use | FOV |
|---|---|
| Exploration follow | 52° by default (44° to 70° in the settings), 4.5° wider while jogging |
| Two-shot of a conversation | 34° |
| Over the shoulder and singles | 30° |
| Sit-down medium, wide, detail | 34°, 44°, 20° |
| Insert on something read | 20° by default, set per spot |
| Title | 50°, drifting through 40° round Mano in his seat |

For each line the conversation camera frames the speaker from the candidate angle that sees their face best: over
the listener's shoulder when that view is clear, wider angles round the speaker otherwise. Views blocked by the
level or by someone's head are rejected, a camera too close to a bystander is penalised, and the camera stays on
one side of the line between the two speakers. A second character within seven metres gets the shot when they
speak. In the finale, a line from someone further off cuts to the chapter's group shot of the steps.

When Mano starts a conversation pressed against someone, he first steps back to 1.25 m so the first shot has room.

### 4.6 Lens and grade

| Effect | Value | Where |
|---|---|---|
| Bloom | intensity 0.38, bloom 0.07, HDR threshold 0.9 | `world_env.gd` |
| Lens dirt | a smudge map on the bloom, strength 0.25 outdoors and 0.1 indoors | `world_env.gd` |
| Halation | a red-orange glow round bright edges: 0.05 in daylight, 0.04 to 0.045 after sunset, 0.03 indoors | `post.gdshader` |
| Sun flare | a soft glow and three warm ghosts, hidden when the sun is occluded, faded over 0.15 s, no streaks | `post.gdshader`, `post_layer.gd` |
| Depth of field | a preset per kind of shot (`wide`, `ots`, `single`, `sit`, `insert`), with circular bokeh | `world_env.gd`, `set_focus_preset()` |
| Grain | 0.022 to 0.028 depending on the time of day, renewed 24 times a second | `post_layer.gd` |
| Vignette | 0.22 while exploring, 0.34 in conversations and sit-downs, 0.6 s between the two | `post_layer.gd` |
| Chromatic aberration | 0.0012 at the edges, the upper limit | `post.gdshader` |

### 4.7 Phone, texts, overheard talk, readables, idle life

The phone is a generic device with no brand and no emoji. On the lock screen, a small card bottom-right shows the
time and incoming messages with a two-pulse buzz. From chapter 3 the phone key opens it in Mano's hand with three
apps: Messages (the threads of `dialogue/chat.json`, unread counts, a "Mark all read" row, and Mano's replies as
tone choices), Find (where the right AirPod was last seen, which also pins it on the map) and Music (the songs
heard tonight). Before chapter 3 the key shows a black screen and a thought.

Overheard conversations are twelve two-person exchanges that start when Mano is within six metres with a line of
sight. They show as small grey italics at the bottom left and never take the controls. Some carry soft clues, such
as Karim showing off a "free AirPod".

Twelve spots are things to read: a whiteboard, a door sign, notice boards, posters, Cristina's note. Ten open an
insert shot with shallow focus and Mano's remark.

After twenty seconds standing still, Mano looks around or checks his phone, sometimes with a thought.

### 4.8 Movement over detail

Small movement sells a place better than extra detail. Tree and grass materials sway in a vertex shader with a
phase taken from world position. October leaves fall in cour Pasteur and on rue Pasteur. Dust hangs in the low sun
where it enters Amphi 4.

### 4.9 Guardrails: what the game does not copy

The game uses no Life is Strange names, characters or places, and none of its motifs: no butterflies, deer,
lighthouses or storms. It has no rewind or other powers, no "this action will have consequences" notice and no
choice-statistics screen. It does not use that series' fonts, logos, interaction icons, journal layouts or sticker
designs, an instant camera as the hero's signature, any song from its soundtracks, or its concept art as a
reference to paint over.

The game's own signature is one AirPod, the light running out on a real Thursday in October, Mano's Seyès notebook
in blue ballpoint, golden rubber ducks, moulinette -42, and a friend's film developed only in the credits.

## 5. UI and typography: *le cahier de Mano*

Every full-screen UI is Mano's French school notebook or something stuck into it. Prompts in the world are drawn
with his pen. Subtitles and settings stay in clean print. [ART_DIRECTION.md](ART_DIRECTION.md) has the detail.

### 5.1 Fonts

| Voice | Font | Used for |
|---|---|---|
| Mano's pen | Mynerve | inner voice, objective strip, toasts, journal text, notes |
| Mano's marker | Shantell Sans (variable) | headings, menu items, prompt verbs, banners, chapter times, map labels |
| Print | Atkinson Hyperlegible Next (variable) | subtitles, settings, credits, the phone; the project's default font |
| The machine | Atkinson Hyperlegible Mono | moulinette code and verdicts |

All four are under the SIL Open Font License 1.1; the licence texts are in `assets/fonts/licenses/` and the fonts
are named in the credits. A "Readable fonts" setting draws the pen and marker roles in the print face. The title
logo is set in Shantell Sans.

### 5.2 Palette

| Token | Hex | Role |
|---|---|---|
| `PAPER`, `PAPER_SHADE` | #FAF8F2, #ECE8DE | notebook paper; gutters and shadows |
| `SEYES_LINE`, `SEYES_INTER`, `GRID_5MM`, `MARGIN_RED` | #B9AFDD, #CBD8EE, #BFCDE0, #E0605A | the Seyès ruling, the map's grid sheet, the margin |
| `INK_BLUE` | #233E94 | everything Mano writes (9.0:1 on paper) |
| `INK_RED`, `MARKER_RED`, `INK_GREEN` | #C2302B, #D23A2C, #1D7449 | dates and corrections, the objective loop and focus marks, ticks |
| `INK_BLACK`, `PENCIL` | #25221E, #55565C | marker labels, places not visited yet |
| `FLUO` | #FFE94D | highlighter |
| sticky notes | #FFF07A, #FFC2D6, #C9F1DA | toasts and hints |
| over the 3D scene | text #F7F2E8 with a #120E0A outline | subtitles and thoughts |

Subtitle colours per speaker: Mano #FFD45C, Toma #6FA3FF, Anisha #5FD6A2, Ian #D9A877, Silvia #FFB38A, Ishita
#F28DB2, Cristina #7FD3E6, Joaquin #B8D86B, Karim #FF8C42, Mme Dupont #A99BFF. The name is always written out as
well, so colour never carries the information alone.

### 5.3 Sizes

Sizes are in pixels at 1080p. Subtitles are 38 px at size M, with S, L and XL at 0.84, 1.2 and 1.5 times that. The
inner voice runs slightly larger because Mynerve has a smaller x-height. Choices are 34 px, the prompt verb 30 px
with the live key letter at 22 px, the objective strip 36 px, overheard talk 27 px. Nothing that carries
information is smaller than 22 px in the print face.

### 5.4 Rules

Sentence case everywhere; capitals only for things that are capitals in the world ("EN PANNE", "KO").

The HUD and the menus have no translucent dark rounded panels, no pill buttons, no emoji icons and no arrows
glued onto button text. Emphasis is an underline doodle, a highlighter swipe or the marker.

Imperfection follows rules. Rotation and jitter are seeded, so they are the same on every run, and animated pen
marks "boil" at 8 frames a second.

Motion is paper: the notebook slides up and settles at a slight angle, pages slide, sticky notes land and peel
away, and exits are faster than entries. "Reduce motion" removes the boil, the overshoot and the rotation.

Icons are ballpoint doodles drawn in code in one style. Key letters in prompts are live text taken from the
bindings.

### 5.5 Screens

| Screen | It is |
|---|---|
| Title | the live Amphi 4 at 17:41 (§7) with the logo as a sticker and the menu written in marker on a taped Seyès page. Continue carries a pen note such as "last time: cour Pasteur, 18:03". |
| Loading | the closed notebook with its étiquette ("Nom : Mano", "Matière : retrouver mon AirPod"), a pencil line for progress and one tip on a sticky note |
| Chapter card | a fresh page: the date top-right ruled under in red, the time in marker, the place in pen; about 3.6 s |
| Chapter select | the same taped page, one chapter per line, with what each still holds of ducks, film and moments |
| HUD objective | a torn Seyès strip top-left, shown only when the objective changes or while the journal key is held: the old line struck through in red, the new one written on and held six seconds |
| Toasts | sticky notes top-right, two at most, each with a doodle |
| Area banner | masking tape with the place name in marker |
| Prompt | a small pen ring on the object, a curved leader line, the verb and a sketched keycap; nearest interactable only; hidden in the letterbox |
| Waypoint | off by default; when on, a red-pen target with no distance |
| Control hints | one-off sticky notes the first time each action matters |
| Subtitles | centred, no box, the speaker's name inline in their colour, a short fade; typewriter optional |
| Choices | two to four handwritten options above the subtitle, the focused one circled in red pen; keys 1 to 4 also pick |
| Pause | the closed notebook at an angle, the menu on the étiquette's lines, a sticky note on how the night is going |
| Settings | a printed school form filled in by hand: ticked boxes, pencil marks on printed scales, the chosen word circled, and a live subtitle preview |
| Journal | the open notebook with six tabs: *today*, *people*, *film*, *ducks*, *moments*, *on the side* |
| Map | a page of the notebook (§6) |
| Phone | §4.7 |
| Photo mode | a free camera; a capture saves a picture, or puts a framed spot on Ishita's film |
| Lost & found | the box's felt tray seen close up: each AirPod can be inspected, and the note read |
| Ending | the notebook's last page with "à suivre…" in red marker and the recap in pen |

The journal opens on half-finished Dijkstra notes that trail off into a long sleepy pen stroke, with "17:42, woke
up. ONE AirPod." in the margin. The *people* tab holds one kind line per friend in Mano's voice, which changes as
the night goes on.

## 6. The M map

M opens a page of the notebook. On the left is a 5 mm grid sheet (*petits carreaux*) taped in at a slight angle; on
the right, in pen, where Mano is and today's to-dos.

The sheet is drawn from `assets/levels/campus_plan.json`, which `tools/map/export_plan.py` exports from the level's
own footprints: KB1, 24 rue Pasteur, Paritalie, the courtyard, the covered passages and the rooms. Streets carry
their names and one-way arrows. The scale is one square for four metres, with a scale bar. Page-up is the game's
-Z, so the hand-drawn north arrow points 13.6° clockwise of page-up. The OpenStreetMap credit is written on the
sheet.

Footprints are in pencil with a slight overshoot at the corners. A room is in pencil with a "?" until Mano has
been in it, and inked with its name after that. The courtyard is stippled.

Over the baked sheet a live layer shows Mano as a red dot with a facing tick and "moi", the friends he has met as
dots in their colours with their names, the objective as a red marker loop with a short note, and from chapter 3
the finder's last-seen pin. Labels never overlap: each takes the first free place among a few candidates round its
point, and a test checks it.

The static sheet is drawn once into a `SubViewport` when the map opens. Only the live layer is redrawn, ten times
a second.

The design goes further than the build: floor tabs for the Under and the first floor, zoom and pan, friends as
photo stickers, and line work traced by hand and scanned. These are listed under V2-09 in §12.

## 7. Title and opening sequence

| Step | What the player sees |
|---|---|
| Title | Amphi 4 at 17:41, live in the engine: Mano asleep at his desk, the Dijkstra slide glowing in the low sun, the camera drifting slowly round him. The logo sticker is top-left and the menu is on a taped page bottom-left: Continue, New game, Chapters, Settings, Credits, Quit. |
| New game | A confirmation first if a night is in progress, then a fade to black. |
| Cold open | "23:41" (§3.5), in the engine, in the `late` preset. |
| Caption | "Six hours earlier." |
| Chapter card | "jeudi 15 octobre", "17:42", "Amphi 4" write themselves. |
| The dream | An 8.67 s clip. A single white earbud tips off the top step of the empty amphi in golden dust and tumbles down the aisle steps while the camera glides after it, then the camera drifts up to the notebook on the desk beside Mano. |
| Wake-up | Continues from the clip's last frame on the blurred desk: the focus racks in, the camera eases onto Mano, his eyelids flutter. |
| Toma | The AirPod, the promise, the phone dying. |
| Control | After Toma's scene. |

The opening is built to give the player a question, a laugh, a friend's face and then control within about two
minutes.

The first half of the dream clip, the tumble, is the engine's own render: a deterministic rigid-body simulation of
the earbud, rendered frame by frame with motion blur. The second half, the drift to the notebook, is an
AI-generated clip made between two engine renders of the empty amphi (§10). The two are joined and converted to
Ogg Theora, and the clip plays in a `VideoStreamPlayer` under the post-processing layer so it shares the game's
grain. [PIPELINE.md](PIPELINE.md) describes the process.

The title has no video loop. The live scene is exact and already lit.

## 8. The campus

The level is the real campus on its real footprints. [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md) explains how it was
mapped and [campus_layout.svg](campus_layout.svg) shows the plan. This section lists what the model contains.
Coordinates are game metres.

### 8.1 Frame and sun

+X runs along rue Pasteur toward compass bearing 76.4°, -Z points toward 346.4°, and true north is 13.6° clockwise
from -Z. The origin is at 48.8154047 N, 2.3630521 E, in the middle of rue Pasteur at the west edge of the passage. The
campus is modelled flat; the real street falls about a metre from west to east.

### 8.2 Rue Pasteur

The street is one-way westbound at 30 km/h, with a contraflow cycle lane marked on the south side. The building
lines are ten metres apart, at z = -5 and z = +5. Cars park along the south kerb only. There is a zebra crossing in
front of no. 24 and one speed bump at x = -21.1. Street trees and bollards stand on the south pavement and street
lamps on the north side. The street has a bike rack and no bike-share station. The playable street ends at rue
Émile Zola in the east.

### 8.3 KB1 (the Voltaire building)

KB1 has a three-storey wing on rue Pasteur, a deeper block behind it and, over that block and its two yards, a box
of three floors raised on a storey-high void that tops out at about 22.5 m. The rue Pasteur front is white render
over a grey plinth, with two-storey dark-framed glass bays and a projecting white "KB1" portal. The rue Voltaire
face has a white colonnade, the cobalt ribbed steel box and tilted red-framed balcony boxes. Inside, the game uses
the ground-floor lobby with the accueil, the stairwell, and the first-floor corridor with SM14 and SM15.

### 8.4 Paritalie (the X)

The X-shaped building is extruded from its real 32-point outline, with a roof at 17.5 m. On rue Pasteur it shows
two wing ends with a tree-filled forecourt between them, and a pharmacy at the western one. Its north-east face
borders cour Pasteur and carries the courtyard steps; the cafeteria is on its south-east face.

### 8.5 24 rue Pasteur: passage, east building, courtyard, south side

The covered passage from rue Pasteur into the courtyard is 6.7 m wide, with a gate just inside the street line and
a blue fascia over the opening. The east building, which holds Amphi 4 in the game, is a single storey with a
planted roof. Cour Pasteur covers about 1,030 m². Two two-storey buildings close its south side, and a second
covered passage leads to the south gate on rue Roger Salengro. The Under is the basement reached by a ramp in the
corner of the courtyard.

### 8.6 Neighbours and backdrop

Beyond the playable area the model includes the ARPEJ student residence next to KB1, the apartment buildings west
of KB1, the rue Émile Zola junction, rue Voltaire behind KB1 with its slip road, the périphérique in its cutting
below a concrete balustrade, and rue Roger Salengro beyond the south gate.

### 8.7 Names and signage

"Cour Pasteur" and "the Under" are the names used on campus. Signage uses the building codes: "KB1" on its
portals and "KB 2,3,4" on the passage banner. Dialogue also calls KB1 the Bâtiment Voltaire. Signs are rebuilt
with real fonts.

### 8.8 Placed for the story

The public record gives footprints and heights. It does not say where rooms are. Where SM14, SM15, "Amphi 4", the
cafeteria and the accueil sit inside their buildings, the extent and entrance of the Under, and the furnishing of
the rooms are choices made for the story. A terrace exists on KB1's third floor in reality and is not modelled
(V2-37).

## 9. Music

The game currently plays six tracks by Kevin MacLeod (incompetech.com, CC BY 4.0), credited in the Credits screen
and in `assets/audio/CREDITS.md`.

| Cue | Track |
|---|---|
| Title; the lobby and stairwell sit-downs | "Morning" |
| Exploration by day; the steps sit-down; the moment the AirPod is found | "Almost Bliss" |
| Exploration from dusk on; the sofa sit-down | "Study And Relax" |
| Minigames, except the kebab orders and the sound search, which play without music | "Sneaky Snitch" |
| The Under | "Raving Energy" |
| The planter-wall sit-down | "Evening" |
| Finale and credits | the playlist pick: "Evening", "Almost Bliss" or "Morning" |

Which exploration track plays is data: `data/chapters.json` maps each light preset and zone to a track. A track
that is faded out keeps its position and resumes from there, so exploration music picks up where a minigame
interrupted it. Music drops under dialogue and a little further under a recorded voice line. Ambience is a set of
CC0 loops chosen per zone.

A soundtrack swap (V2-11) is planned and not started. Its aims: tracks from several artists under CC0 or CC BY
instead of one composer for everything; vocal songs for the sit-downs, played once, never looped and never under
dialogue; no comic cue under the minigames; and a "now playing" pen note in the margin whenever a song starts. The
one-AirPod treatment of §4.3 depends on it.

No rain or thunder beds are used: the night stays dry (§4.9).

## 10. Generated assets

Three kinds of material in the game are AI-generated: the second half of the dream clip (§7), the voices of the
fictional staff and students, and the 3D scans behind six of the friends' outfits. The models used and the files
concerned are listed once, in the last section of [PIPELINE.md](PIPELINE.md#ai-generated-material), and credited
in the in-game Credits screen and the [README](../README.md).

The friends' lines are text only. Nothing readable is generated: no lettering, logos, UI marks, icons or map
drawing.

## 11. Systems

[ARCHITECTURE.md](ARCHITECTURE.md) describes the code. This table maps the design to the files that implement it.

| System | What it does | Files |
|---|---|---|
| Chapters and clock | cards, clock, light presets, staging, triggers and to-dos as data; a snapshot per chapter for chapter select | `data/chapters.json`, `scripts/story/chapters.gd`, `scripts/core/game_state.gd` |
| Time of day | presets, the sky blend, lamp groups, window emission, the grade | `scripts/level/world_env.gd`, `scripts/fx/sky_blend.gdshader` |
| Dialogue as data | `.dlg` files: cues, lines with an expression tag, responses, conditions, jumps, `$` commands | `dialogue/`, `scripts/story/dialogue_data.gd`, `scripts/story/story_commands.gd` |
| Thoughts and barks | the `think` speaker and non-blocking lines | `scripts/story/dialogue.gd` |
| Sit-downs | sit mode, per-shot blend speed, drift and orbit | `scripts/main.gd`, `scripts/camera/camera_rig.gd`, `data/world.json` |
| Music and ambience | crossfades, resume positions, ducking, ambience per zone | `scripts/core/sfx.gd`, `data/songs.json` |
| Phone | lock-screen card, Messages, Find, Music | `scripts/ui/phone.gd`, `scripts/story/chat.gd`, `dialogue/chat.json` |
| Notebook screens and journal | title, loading, pause, settings, credits, journal, recap | `scripts/ui/menus.gd`, `scripts/fx/paper.gdshader`, `data/journal.json` |
| Map | the baked sheet and the live layer | `scripts/ui/map_view.gd`, `tools/map/export_plan.py` |
| Staging and follower | where each character stands per chapter; a friend walking behind Mano on his breadcrumb trail | `data/chapters.json` (`stage`), `scripts/actors/npc.gd` |
| Overheard talk | pairs of characters, a cue, a radius and a condition | `scripts/story/overheard.gd`, `dialogue/overheard.dlg` |
| Film and collectibles | photo spots, exposures, per-chapter counts | `scripts/story/film.gd`, `scripts/story/collectibles.gd`, `scripts/fx/film.gdshader` |
| Movement | foliage sway, falling leaves, dust | `scripts/fx/foliage.gdshader`, `scripts/fx/falling_leaves.gd`, `scripts/fx/sun_room.gd` |
| Window interiors | interior mapping on windows of rooms never entered | `scripts/fx/interior.gdshader`, `scripts/fx/interiors.gd` |
| Tests | compile check, dialogue validator, a headless walk of the quest, saves, the map | `tests/` |

## 12. Implementation backlog

Status is one of done, partial or not started. [STATUS.md](STATUS.md) lists known issues.

| Id | Item | Status | Notes |
|---|---|---|---|
| V2-01 | Font roles; removal of template UI chrome | done | |
| V2-02 | HiDPI; mouse look independent of window scale | done | |
| V2-03 | Subtitles and choices in the print voice, no box | done | |
| V2-04 | Real sun, real date, real compass | done | |
| V2-05 | HUD in Mano's pen: objective strip, sticky notes, leader-line prompts, waypoint off | done | |
| V2-06 | Title, chapter cards, loading, pause, settings, ending as notebook objects | done | The logo is typeset in Shantell Sans; a hand-lettered one is still wanted. |
| V2-07 | Dream prologue | done | |
| V2-08 | The notebook journal | partial | Six tabs are built. Not built: taped portraits on the people pages, a messages tab, a clue web. |
| V2-09 | The M map as a notebook page | partial | Drawn from the real footprints, rooms inked once visited, live layer. Not built: floor tabs, zoom and pan, photo stickers, hand-traced line work. |
| V2-10 | Inner voice (`think`) and the first-person rewrite | done | |
| V2-11 | Soundtrack swap and the "now playing" note | not started | Six Kevin MacLeod tracks play (§9). |
| V2-12 | One-AirPod audio and the Mono audio setting | not started | Depends on V2-11 (§4.3). |
| V2-13 | Time-of-day presets, sky blend, lamps, windows, grade | done | |
| V2-14 | Sit-down moments, six spots | done | `sit_bay` is in KB1's lobby on the ground floor. |
| V2-15 | Campus: Paritalie and the south side of rue Pasteur | done | |
| V2-16 | Campus: KB1 volume and both facades | done | |
| V2-17 | Campus: rue Pasteur, the passage, the east building, the south side | done | |
| V2-18 | Campus: neighbours, backdrop and window interiors | done | |
| V2-19 | Dialogue as data, with a validator | done | The game's own `.dlg` format and parser. |
| V2-20 | Chapters, clock, to-do lists, chapter saves | done | |
| V2-21 | Ishita, Cristina and Joaquin on stage; staging and follower | done | |
| V2-22 | Chapter 1 "Mono" | done | |
| V2-23 | Chapter 2 "Lost & Found" and the twist | done | |
| V2-24 | Phone and group chat | done | Messages, Find and Music. |
| V2-25 | Chapter 3 "Blue Hour" | done | |
| V2-26 | Chapter 4 "Sauce Samouraï" and three new minigames | done | The kebab shop is off screen. |
| V2-27 | Cold open, chapter 5 "Stereo", credits, post-credits, recap | done | The recap shows the player's night only. |
| V2-28 | Look-ats, readables and the decal pass | partial | 88 look-ats and ten inserts are built. The decal pass (posters, notices, grime) is not. |
| V2-29 | Lens, grade and movement pass | done | |
| V2-30 | Collectibles and chapter select | done | Club stickers are not built. |
| V2-31 | Overheard talk, idle life, side stories | done | Twelve overheard conversations and four side stories. |
| V2-32 | Performance pass | not started | |
| V2-33 | Robustness: saves, New game confirmation, Back, device-aware prompts | partial | Atomic saves with a backup, save migration and the confirmations are built. Prompts do not yet follow a switch between keyboard and gamepad. |
| V2-34 | Audio mix: limiter, per-room reverb zones, positional emitters | not started | |
| V2-35 | Accessibility settings | partial | Built: subtitle size, readable fonts, typewriter text, reduce motion. Not built: subtitle background, Mono audio, hold instead of mash, a relaxed moulinette timer, toggle jog, invert X, UI scale. |
| V2-36 | Headless tests and autotest plans | done | |
| V2-37 | Stretch: KB1's third-floor terrace | not started | |

## 13. Decisions and open questions

Question numbers are stable ids, cited from code comments as Q8 or Q15. The numbers missing from both lists were
settled without leaving a trace in the game.

### Decided

| Id | Question | Decision |
|---|---|---|
| Q1 | Date | Thursday 15 October 2026. The piscine is a memory in the dialogue, since it is over by October. |
| Q3 | Are Ishita, Cristina and Joaquin new to the group? | Yes, new this year. Toma's plan for the night is to welcome them. |
| Q7 | The kebab shop | Unnamed, "the kebab on the corner", and never shown. |
| Q11 | Private or public | The repository is public and non-commercial. The credits and the README disclose the generated material. |
| Q12 | Which chat app | A generic group chat with no brand. |
| Q13 | Language | English dialogue with the campus's French words and French notebook dates. |
| Q14 | Waypoint | Off by default, switchable in the settings. |
| Q18 | Where the finale happens | The courtyard steps. |
| Q19 | What is on that night | A BDE party in the Under at 23:00. Chloé's sheet is for the Halloween party. |
| Q20 | Real sun or a nudge to keep the courtyard golden | The real sun. `WorldEnv.sun_nudge` stays at 0. |

### Open

- Q4. The real positions of SM14, SM15, the amphitheatre, the cafeteria and the accueil, and how the Under is
  entered. The level places them for the story (§8.8).
- Q6. Reference photos of the machines, signage and posters, which the decal pass (V2-28) needs.
- Q8. A hand-lettered logo, and C.'s note in Cristina's own handwriting. The note is currently set in the pen font
  in Cristina's ink colour.
- Q9. Whether the friends record their own lines. They are text only today.
- Q15. The replacement soundtrack (V2-11), and whether vocal songs play during the sit-downs or only in the
  credits.
- Q16. A "Toma's night" column beside the player's in the recap. `data/recap.json` has a `toma_picks` list for it,
  which is empty.

## 14. Sources

- Sun position and twilight: the NOAA solar position equations, https://gml.noaa.gov/grad/solcalc/
- Moon position and phase: the suncalc algorithm, https://github.com/mourner/suncalc
- Campus geometry: OpenStreetMap (© OpenStreetMap contributors, ODbL, https://www.openstreetmap.org/copyright),
  the French cadastre and IGN BD TOPO (Licence Ouverte 2.0). See [CAMPUS_LAYOUT.md](CAMPUS_LAYOUT.md).
- Skies and textures: Poly Haven and ambientCG (CC0).
- Fonts: SIL Open Font License 1.1, texts in `assets/fonts/licenses/`.
- Music, sound, characters and animation: `assets/audio/CREDITS.md`, `assets/characters/CREDITS.md` and
  `assets/anims/src/CREDITS.md`.
