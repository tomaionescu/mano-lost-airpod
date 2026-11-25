class_name Chat
extends RefCounted
## Mano's messages (V2-24): dialogue/chat.json read once (threads, messages in delivery batches, replies), and
## what his phone holds now, from the flags it saves in: flags.chat_batches (delivered batches), flags.chat_read
## (thread -> messages seen), flags.chat_sent (his own replies) and the reply flags (reply_steps...: a tone, or ""
## for silence). Everything here is a function of GameState.flags and the data, so the phone (scripts/ui/phone.gd),
## the story (`$ phone flood`) and the headless tests use the same rules. Songs (data/songs.json) live here too:
## the phone's Music list and the song titles the story prints ({{song.<flag>}}).

const FILE := "res://dialogue/chat.json"
const SONGS := "res://data/songs.json"

static var data := {}
static var songs := {}
static var _by_thread := {}   # thread -> [message index into data.messages], in file order


static func load_data(force := false) -> void:
	if not data.is_empty() and not force:
		return
	data = _read(FILE)
	songs = _read(SONGS)
	_by_thread = {}
	var msgs: Array = data.get("messages", [])
	for i in msgs.size():
		var t := String(msgs[i].get("thread", ""))
		if not _by_thread.has(t):
			_by_thread[t] = []
		_by_thread[t].append(i)


static func _read(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_error("Chat: %s is missing" % path)
		return {}
	var j := JSON.new()
	if j.parse(FileAccess.get_file_as_string(path)) != OK or not j.data is Dictionary:
		push_error("Chat: %s does not parse: %s (line %d)" % [path, j.get_error_message(), j.get_error_line()])
		return {}
	return j.data


# ------------------------------------------------------------------ data
static func batches() -> Array:
	load_data()
	return data.get("batches", [])


static func threads() -> Dictionary:
	load_data()
	return data.get("threads", {})


static func thread_ids() -> Array:
	return threads().keys()


static func title(thread: String) -> String:
	return DialogueData.format(String(threads().get(thread, {}).get("title", thread.capitalize())))


static func messages() -> Array:
	load_data()
	return data.get("messages", [])


static func replies() -> Array:
	load_data()
	return data.get("replies", [])


## The display name of a message's sender: the cast's name, "Mano", or a classmate's from_name.
static func sender_name(m: Dictionary) -> String:
	if m.has("from_name"):
		return String(m.from_name)
	var who := String(m.get("from", ""))
	if who == "mano":
		return "Mano"
	for d in CastDefs.npc_defs():
		if d.id == who:
			return String(d.name).get_slice(" (", 0)
	return who.capitalize()


static func sender_color(m: Dictionary) -> Color:
	var who := String(m.get("from", ""))
	if CastDefs.SPEAKERS.has(who):
		return CastDefs.SPEAKERS[who].color
	for d in CastDefs.npc_defs():
		if d.id == who:
			return d.color
	return Color("#c9d1d9")


# ------------------------------------------------------------------ the phone's state (in the flags)
static func delivered() -> Array:
	return GameState.flags.get("chat_batches", [])


static func is_delivered(batch: String) -> bool:
	return batch in delivered()


## Delivers `batch` and every batch before it in chatjson's order that has not landed yet; returns the messages
## that just landed, in order.
static func deliver(batch: String) -> Array:
	var order := batches()
	var upto := order.find(batch)
	if upto < 0:
		push_warning("Chat: no batch '%s' in %s" % [batch, FILE])
		return []
	var have: Array = delivered().duplicate()
	var fresh: Array = []
	for i in upto + 1:
		var b := String(order[i])
		if b in have:
			continue
		have.append(b)
		for m in messages():
			if String(m.get("batch", "")) == b:
				fresh.append(m)
	GameState.flags["chat_batches"] = have
	return fresh


## A thread's messages delivered so far, with Mano's sent replies and the reactions to them in their place:
## [{from|from_name, at, text, photo?, mine?}], in order.
static func thread(thread_id: String) -> Array:
	load_data()
	var pairs: Array = []   # [message, order]: sent replies and reactions go after the messages before them
	var have := delivered()
	for i in _by_thread.get(thread_id, []):
		var m: Dictionary = messages()[i]
		if String(m.get("batch", "")) in have:
			pairs.append([m, pairs.size()])
	for s in GameState.flags.get("chat_sent", []):
		if s is Dictionary and String(s.get("thread", "")) == thread_id and not bool(s.get("silent", false)):
			pairs.append([s, pairs.size()])
	pairs.sort_custom(func(a, b):
		var ta := Conditions.minutes(String(a[0].get("at", "00:00")))
		var tb := Conditions.minutes(String(b[0].get("at", "00:00")))
		return ta < tb or (ta == tb and int(a[1]) < int(b[1])))
	var out: Array = []
	for p in pairs:
		out.append(p[0])
	return out


static func read_count(thread_id: String) -> int:
	var r = GameState.flags.get("chat_read", {})
	return int(r.get(thread_id, 0)) if r is Dictionary else 0


static func unread(thread_id: String) -> int:
	return maxi(0, thread(thread_id).size() - read_count(thread_id))


static func total_unread() -> int:
	var n := 0
	for t in thread_ids():
		n += unread(String(t))
	return n


static func mark_read(thread_id: String) -> void:
	var r = GameState.flags.get("chat_read", {})
	if not r is Dictionary:
		r = {}
	r = r.duplicate()
	r[thread_id] = thread(thread_id).size()
	GameState.flags["chat_read"] = r


static func mark_all_read() -> void:
	for t in thread_ids():
		mark_read(String(t))


## The threads that have something in them, most recent first.
static func active_threads() -> Array:
	var out: Array = []
	for t in thread_ids():
		if not thread(String(t)).is_empty():
			out.append(String(t))
	out.sort_custom(func(a, b): return _last_at(a) > _last_at(b))
	return out


static func _last_at(thread_id: String) -> int:
	var ms := thread(thread_id)
	return Conditions.minutes(String(ms.back().get("at", "00:00"))) if not ms.is_empty() else -1


# ------------------------------------------------------------------ replies
## The reply Mano can send in this thread now (its batch delivered, its flag still ""), or {}.
static func pending_reply(thread_id: String) -> Dictionary:
	for r in replies():
		if String(r.get("thread", "")) == thread_id and is_delivered(String(r.get("after", ""))) \
				and String(GameState.flags.get(String(r.get("flag", "")), "")) == "" and not _answered(String(r.get("id", ""))):
			return r
	return {}


static func _answered(id: String) -> bool:
	for s in GameState.flags.get("chat_sent", []):
		if s is Dictionary and String(s.get("reply", "")) == id:
			return true
	return false


## Sends option `i` of reply `r`: the tone goes into its flag ("silent" leaves it ""), Mano's text and the
## friends' reactions into the thread, at `at`. Returns the reactions (to buzz them in one after the other).
static func answer(r: Dictionary, i: int, at: String) -> Array:
	var opts: Array = r.get("options", [])
	if i < 0 or i >= opts.size():
		return []
	var o: Dictionary = opts[i]
	var tone := String(o.get("tone", "silent"))
	var sent: Array = GameState.flags.get("chat_sent", []).duplicate()
	if tone == "silent":
		sent.append({"thread": r.thread, "reply": r.id, "silent": true, "at": at})
		GameState.flags["chat_sent"] = sent
		return []
	GameState.flags[String(r.flag)] = tone
	sent.append({"thread": r.thread, "reply": r.id, "from": "mano", "at": at, "text": DialogueData.format(String(o.get("text", ""))), "mine": true})
	var reacts: Array = []
	for re in o.get("reactions", []):
		var m := {"thread": r.thread, "reply": r.id, "from": String(re.get("from", "")), "at": at, "text": DialogueData.format(String(re.get("text", "")))}
		sent.append(m)
		reacts.append(m)
	GameState.flags["chat_sent"] = sent
	GameState.flags_changed.emit()
	return reacts


# ------------------------------------------------------------------ songs
static func song_title(stem: String) -> String:
	load_data()
	return String(songs.get("songs", {}).get(stem, {}).get("title", stem.capitalize()))


static func song_artist(stem: String) -> String:
	load_data()
	return String(songs.get("songs", {}).get(stem, {}).get("artist", ""))


static func song_known(stem: String) -> bool:
	load_data()
	return songs.get("songs", {}).has(stem)


## A song counts for the phone's Music list (not the minigames' cue).
static func song_listed(stem: String) -> bool:
	load_data()
	return song_known(stem) and bool(songs.get("songs", {}).get(stem, {}).get("heard", true))


## A track started: noted once in flags.songs_heard (the phone's Music list, later the credits).
static func heard(stem: String) -> void:
	if stem == "" or not song_listed(stem):
		return
	var h: Array = GameState.flags.get("songs_heard", [])
	if not stem in h:
		h = h.duplicate()
		h.append(stem)
		GameState.flags["songs_heard"] = h
