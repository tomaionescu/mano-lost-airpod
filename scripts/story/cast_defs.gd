class_name CastDefs
extends RefCounted
## Who is who: display names, subtitle colours, models, behaviour, and fallback placements
## (fixed coordinates) used when the level has no NPC_<id> marker. Who is on campus when is story data
## (data/world.json npc_when, data/chapters.json "stage"), and so are the lines (res://dialogue/).
## `staged_only`: the character has no place of their own; they are on campus only where a chapter's "stage" (or a
## `$ stage` command) puts them (V2-21: Ishita, Cristina and Joaquin). `pos` is then only a fallback.

const SPEAKERS := {
	"mano": {"name": "Mano", "color": Color("#ffd45c")},
	"nar": {"name": "", "color": Color("#e8e2d4")},
	"think": {"name": "", "color": Color("#e8e2d4")},   # Mano's inner voice (V2-10): unnamed, in his pen
}

static func npc_defs() -> Array:
	return [
		{"id": "toma", "name": "Toma", "model": "toma_fit1", "pos": Vector3(17.55, -0.9, 14.33), "yaw": PI, "sit": true, "color": Color("#6fa3ff"), "range": 2.3},
		{"id": "prof", "name": "M. Bernard", "model": "prof", "pos": Vector3(18.2, -2.4, 7.4), "yaw": 0.0, "color": Color("#d2b48c"), "range": 2.6, "talk_clip": "talk_idle", "chatting": true},
		{"id": "sleeper", "name": "Sleepy SUP", "model": "lucas", "pos": Vector3(24.5, -1.5, 12.43), "yaw": PI, "sit": true, "sleep": true, "no_look": true, "color": Color("#f0a35e")},
		{"id": "ian", "name": "Ian", "model": "ian", "pos": Vector3(5.0, 0.0, 28.0), "yaw": PI / 2, "color": Color("#d9a877"), "range": 2.3, "talk_clip": "talk_idle", "chatting": true},
		{"id": "silvia", "name": "Silvia", "model": "silvia", "pos": Vector3(7.0, 0.0, 28.0), "yaw": -PI / 2, "color": Color("#ffb38a"), "range": 2.3, "talk_clip": "talk_idle", "chatting": true},
		{"id": "yanis", "name": "Yanis", "model": "yanis", "pos": Vector3(10, 0, 20), "yaw": 0.0, "color": Color("#9fb3c8"),
			"path": [Vector3(10, 0, 20), Vector3(22, 0, 27), Vector3(16, 0, 33), Vector3(4, 0, 31), Vector3(2.2, 0, 27.5)]},
		{"id": "theo", "name": "Théo", "model": "theo", "pos": Vector3(-6.2, 0.81, 19.0), "yaw": 2.6, "sit": true, "color": Color("#b6c4d6")},
		{"id": "anisha", "name": "Anisha", "model": "anisha", "pos": Vector3(-12.25, 3.6, -19.98), "yaw": PI, "sit": true, "sit_clip": "typing", "color": Color("#5fd6a2"), "range": 2.1},
		{"id": "acu", "name": "ACU Léo", "model": "acu", "pos": Vector3(-14, 3.6, -14), "yaw": PI / 2, "color": Color("#ff6b5b"),
			"path": [Vector3(-14, 3.6, -14), Vector3(6, 3.6, -14)], "loop": false},
		{"id": "student2", "name": "Piscine survivor", "model": "student2", "pos": Vector3(1.75, 3.6, -17.18), "yaw": PI, "sit": true, "sit_clip": "typing", "color": Color("#4cd07d")},
		{"id": "ines", "name": "Inès", "model": "ines", "pos": Vector3(-7.9, 3.6, -22.98), "yaw": PI, "sit": true, "sit_clip": "typing", "color": Color("#ff7ab8")},
		{"id": "karim", "name": "Karim (BDE)", "model": "karim", "pos": Vector3(15, -3.6, 45.1), "yaw": 0.0, "color": Color("#ff8c42"), "range": 2.3, "talk_clip": "talk_idle"},
		{"id": "chloe", "name": "Chloé (BDE)", "model": "chloe", "pos": Vector3(4.25, -3.6, 43.1), "yaw": PI / 2, "sit": true, "color": Color("#3fd6b5")},
		# when each of Mme Dupont's two spots is on campus: data/world.json npc_when (main._spawn_npcs)
		{"id": "madame", "name": "Mme Dupont", "model": "madame", "pos": Vector3(-4.2, 0.02, 40.2), "yaw": 2.2, "color": Color("#a99bff"), "range": 2.4},
		{"id": "madame2", "name": "Mme Dupont", "model": "madame", "pos": Vector3(-3.4, 0.0, -24.25), "yaw": 0.0, "color": Color("#a99bff"), "range": 2.5},
		{"id": "student3", "name": "SPE student", "model": "student3", "pos": Vector3(-6.4, 0.02, 34.6), "yaw": 0.6, "sit": true, "color": Color("#c18cff")},
		{"id": "waiting", "name": "Waiting student", "model": "crowd5", "pos": Vector3(-7, 0.0, -7.7), "yaw": PI, "sit": true, "color": Color("#c4ccd4")},
		# the side story "The duck whisperer" (docs/DESIGN.md §3.9): the student who hid the twelve golden ducks, by a
		# picnic table in cour Pasteur (no level marker: this is their place)
		{"id": "whisperer", "name": "Duck whisperer", "model": "crowd7", "pos": Vector3(13.4, 0.0, 29.7), "yaw": deg_to_rad(-140.0), "color": Color("#d8c39a"), "range": 2.0},
		# the three new friends (V2-21, docs/DESIGN.md §3.6): new to the group this year; on stage only where a chapter puts them
		{"id": "ishita", "name": "Ishita", "model": "ishita", "pos": Vector3(4.6, 0.0, 11.2), "yaw": -PI / 2, "color": Color("#f28db2"), "range": 2.3, "talk_clip": "talk_idle", "staged_only": true},
		{"id": "cristina", "name": "Cristina", "model": "cristina", "pos": Vector3(-9.6, 0.0, 44.8), "yaw": 0.0, "color": Color("#7fd3e6"), "range": 2.3, "talk_clip": "talk_idle", "staged_only": true},
		{"id": "joaquin", "name": "Joaquin", "model": "joaquin", "pos": Vector3(13.4, -3.6, 47.2), "yaw": 2.2, "color": Color("#b8d86b"), "range": 2.3, "talk_clip": "talk_idle", "staged_only": true},
	]


static func crowd_models() -> Array:
	return ["crowd1", "crowd2", "crowd3", "crowd4", "crowd5", "crowd6", "crowd7", "crowd8"]
