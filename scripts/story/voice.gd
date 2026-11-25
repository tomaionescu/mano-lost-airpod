class_name VoiceLines
extends RefCounted
## Recorded subtitle cards. A card's voice file is res://assets/audio/voice/<key>.ogg, listed in
## manifest.json as {key: {speaker, text, file, seconds, env}}; `env` is the jaw opening at ENV_RATE Hz (0..1)
## that CharacterRig.lip_sync() plays back. Lines have no ids, so the key is the voice's speaker id + "_" +
## the first 10 hex digits of sha1("<speaker>|<exact card text>"): when a line's text changes, its key finds no
## file and the card stays silent. Built by tools/py/voice_build.py; only fictional NPCs have files
## (the friends' lines never get a synthetic voice).

const DIR := "res://assets/audio/voice/"
const MANIFEST := DIR + "manifest.json"
const ENV_RATE := 30.0
## Speakers that share one set of recordings: the crowd's models by build (cast.py), Mme Dupont's second spot.
const ALIAS := {
	"madame2": "madame",
	"crowd1": "crowd_m", "crowd3": "crowd_m", "crowd5": "crowd_m", "crowd7": "crowd_m",
	"crowd2": "crowd_f", "crowd4": "crowd_f", "crowd6": "crowd_f", "crowd8": "crowd_f",
}

static var _manifest = null


static func speaker_of(who: String) -> String:
	return String(ALIAS.get(who, who))


static func key(who: String, text: String) -> String:
	var s := speaker_of(who)
	return s + "_" + (s + "|" + text).sha1_text().substr(0, 10)


static func manifest() -> Dictionary:
	if _manifest == null:
		_manifest = {}
		if FileAccess.file_exists(MANIFEST):
			var d = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST))
			if d is Dictionary:
				_manifest = d
	return _manifest


## The card's recording: {key, stream, seconds, env: PackedFloat32Array}, or {} when it has none.
static func find(who: String, text: String) -> Dictionary:
	if who == "nar" or who == "think" or who == "":
		return {}
	var k := key(who, text)
	var e: Dictionary = manifest().get(k, {})
	if e.is_empty():
		return {}
	var path := DIR + String(e.get("file", k + ".ogg"))
	if not ResourceLoader.exists(path):
		return {}
	var stream := load(path) as AudioStream
	if stream == null:
		return {}
	return {"key": k, "stream": stream, "seconds": float(e.get("seconds", stream.get_length())),
		"env": PackedFloat32Array(e.get("env", []))}
