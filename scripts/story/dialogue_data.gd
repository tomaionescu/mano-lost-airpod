class_name DialogueData
extends RefCounted
## Dialogue as data (V2-19): the res://dialogue/*.dlg files, parsed once into cues, and compiled on demand into the
## step arrays Dialogue plays (["who", "text", "expr"], {"who", "t", "e", "ask"}, Callable). The format is a small
## subset of Dialogue Manager 4's syntax (docs/ARCHITECTURE.md):
##   ~ talk.anisha                    a cue (an entry point); ids are [a-z0-9_] parts joined by dots
##   anisha: [#smirk] Deal?           a line: speaker, optional expression, text, then optional [if expr] [slot]
##   - Deal                           a response to the line above, with its block indented under it
##   % yanis: one / % yanis: two      a random group: consecutive % lines, one is picked
##   if expr / elif expr / else       a branch, evaluated when the cue reaches it
##   $ set ines = true                a command (StoryCommands.SPEC)
##   => cue  => END  =>< cue          jump (the rest of the queue is replaced), end, or run a cue and come back
##   {{coins}} {{word.party}}         filled in when the card shows ({{song.playlist}}: the title of the song a flag names)
## Indentation is tabs (four spaces count as one). A line whose first non-blank character is # is a comment.
## Branches, random groups, jumps, commands, conditional lines and filled-in text compile to Callables that act on
## the runner (Story: push, jump, end_now, command) when they are reached; the files themselves hold no code.

const DIR := "res://dialogue/"
const RE_CUE := "^[a-z0-9_]+(\\.[a-z0-9_]+)*$"

static var cues := {}        # id -> {"id", "file", "line", "body": Array}
static var files: Array = [] # the .dlg files read, in order
static var errors: Array = []    # "file:line: message"
static var warnings: Array = []
static var _loaded := false
static var _re_line: RegEx = null
static var _re_interp: RegEx = null
static var _think_cache := {}
## The commands a look-at played as barks may run (anything else, a choice or a line by someone else makes it a
## conversation): they act at once and never wait on the screen.
const BARK_CMDS := ["set", "add", "clue", "toast", "sfx", "coin", "hint", "banner", "clock", "lamps"]


# ------------------------------------------------------------------ loading
static func load_all(force := false) -> void:
	if _loaded and not force:
		return
	cues = {}
	files = []
	errors = []
	warnings = []
	_think_cache = {}
	_loaded = true
	var d := DirAccess.open(DIR)
	if d == null:
		errors.append("%s: cannot open the dialogue folder" % DIR)
		return
	var names: Array = []
	for f in d.get_files():
		if f.ends_with(".dlg"):
			names.append(f)
	names.sort()
	for f in names:
		files.append(DIR + f)
		parse_text(FileAccess.get_file_as_string(DIR + f), DIR + f)


static func has_cue(id: String) -> bool:
	load_all()
	return cues.has(id)


## Parses one file's text into `cues` (errors and warnings collected, never fatal).
static func parse_text(text: String, file: String) -> void:
	var lines: Array = []   # [{indent, text, ln}]
	var mixed := false
	var raw := text.split("\n")
	for i in raw.size():
		var l := String(raw[i]).trim_suffix("\r")
		var body := l.strip_edges(true, false)
		if body.strip_edges() == "" or body.begins_with("#"):
			continue
		var lead := l.substr(0, l.length() - body.length())
		var tabs := lead.count("\t")
		var spaces := lead.count(" ")
		if tabs > 0 and spaces > 0:
			mixed = true
		if spaces % 4 != 0:
			errors.append("%s:%d: indentation of %d spaces (use tabs, or four spaces per level)" % [file, i + 1, spaces])
		lines.append({"indent": tabs + spaces / 4, "text": body.strip_edges(false, true), "ln": i + 1})
	if mixed:
		warnings.append("%s: mixes tabs and spaces in its indentation" % file)
	var i := 0
	while i < lines.size():
		var L: Dictionary = lines[i]
		if not L.text.begins_with("~ "):
			errors.append("%s:%d: text outside a cue (a file starts with '~ cue.id')" % [file, L.ln])
			i += 1
			continue
		if L.indent != 0:
			errors.append("%s:%d: a cue header must not be indented" % [file, L.ln])
		var id := String(L.text.substr(2)).strip_edges()
		if not _re(RE_CUE).search(id):
			errors.append("%s:%d: bad cue id '%s'" % [file, L.ln, id])
		var j := i + 1
		while j < lines.size() and not (lines[j].text.begins_with("~ ") and lines[j].indent == 0):
			j += 1
		var res := _block(lines.slice(i + 1, j), 0, 0, file)
		if cues.has(id):
			errors.append("%s:%d: cue '%s' is defined twice (first in %s:%d)" % [file, L.ln, id, cues[id].file, cues[id].line])
		else:
			cues[id] = {"id": id, "file": file, "line": L.ln, "body": res[0]}
		i = j


## Parses the statements at `level` from lines[i]; returns [body, next index].
static func _block(lines: Array, i: int, level: int, file: String) -> Array:
	var body: Array = []
	var rand_open := false
	while i < lines.size():
		var L: Dictionary = lines[i]
		var src := "%s:%d" % [file, L.ln]
		if L.indent < level:
			break
		if L.indent > level:
			errors.append("%s: unexpected indentation" % src)
			i += 1
			continue
		var t: String = L.text
		if t.begins_with("% "):
			var ln := _line(t.substr(2), src)
			if ln.is_empty():
				i += 1
				continue
			if rand_open and not body.is_empty() and body.back().t == "random":
				body.back().lines.append(ln)
			else:
				body.append({"t": "random", "lines": [ln], "src": src})
			rand_open = true
			i += 1
			continue
		rand_open = false
		if t.begins_with("if ") or t == "if":
			var node := {"t": "if", "branches": [], "else": null, "src": src}
			var sub := _block(lines, i + 1, level + 1, file)
			node.branches.append({"cond": t.substr(3).strip_edges(), "body": sub[0], "src": src})
			if String(node.branches[0].cond) == "":
				errors.append("%s: 'if' without a condition" % src)
			i = sub[1]
			while i < lines.size() and lines[i].indent == level:
				var e: String = lines[i].text
				var esrc := "%s:%d" % [file, lines[i].ln]
				if e.begins_with("elif "):
					sub = _block(lines, i + 1, level + 1, file)
					node.branches.append({"cond": e.substr(5).strip_edges(), "body": sub[0], "src": esrc})
					i = sub[1]
				elif e == "else":
					sub = _block(lines, i + 1, level + 1, file)
					node["else"] = sub[0]
					i = sub[1]
					break
				else:
					break
			body.append(node)
			continue
		if t.begins_with("elif ") or t == "else":
			errors.append("%s: '%s' without an 'if' above it" % [src, t.get_slice(" ", 0)])
			i = _block(lines, i + 1, level + 1, file)[1]
			continue
		if t.begins_with("- ") or t == "-":
			var prev = body.back() if not body.is_empty() else null
			var resp := _response(t.substr(1).strip_edges(), src)
			var sub := _block(lines, i + 1, level + 1, file)
			resp["body"] = sub[0]
			if prev == null or prev.t != "line":
				errors.append("%s: a response needs a line right above it" % src)
			else:
				prev.ask.append(resp)
			i = sub[1]
			continue
		if t.begins_with("$ "):
			body.append(_command(t.substr(2).strip_edges(), src))
			i += 1
			continue
		if t.begins_with("=>"):
			var mode := "goto"
			var target := t.substr(2).strip_edges()
			if t.begins_with("=><"):
				mode = "call"
				target = t.substr(3).strip_edges()
			if target == "END":
				mode = "end"
			body.append({"t": "jump", "mode": mode, "target": target, "src": src})
			i += 1
			continue
		var ln := _line(t, src)
		if not ln.is_empty():
			body.append(ln)
		i += 1
	return [body, i]


## "who: [#expr] text [if expr] [slot]" -> a line node.
static func _line(t: String, src: String) -> Dictionary:
	if _re_line == null:
		_re_line = RegEx.create_from_string("^([a-z][a-z0-9_]*): (.*)$")
	var m := _re_line.search(t)
	if m == null:
		errors.append("%s: not a line, command or response: '%s'" % [src, t])
		return {}
	var rest := m.get_string(2)
	var node := {"t": "line", "who": m.get_string(1), "text": "", "expr": "", "cond": "", "slot": false, "ask": [], "src": src}
	while rest.begins_with("[#"):
		var close := rest.find("]")
		if close < 0:
			errors.append("%s: unclosed [#expression]" % src)
			break
		node.expr = rest.substr(2, close - 2).strip_edges()
		rest = rest.substr(close + 1).strip_edges(true, false)
	var tail := _tail_tags(rest, src)
	node.text = String(tail[0]).strip_edges()
	node.cond = tail[1]
	node.slot = tail[2]
	if node.text == "":
		errors.append("%s: a line with no text" % src)
	return node


## Strips [if expr] and [slot] off the end: [text, condition, slot].
static func _tail_tags(rest: String, src: String) -> Array:
	var cond := ""
	var slot := false
	while true:
		rest = rest.strip_edges(false, true)
		if rest.ends_with("[slot]"):
			slot = true
			rest = rest.trim_suffix("[slot]")
			continue
		if rest.ends_with("]"):
			var open := rest.rfind("[if ")
			if open >= 0:
				cond = rest.substr(open + 4, rest.length() - open - 5).strip_edges()
				rest = rest.substr(0, open)
				continue
		break
	return [rest, cond, slot]


static func _response(t: String, src: String) -> Dictionary:
	var tail := _tail_tags(t, src)
	if String(tail[0]).strip_edges() == "":
		errors.append("%s: a response with no label" % src)
	return {"label": String(tail[0]).strip_edges(), "cond": tail[1], "slot": tail[2], "body": [], "src": src}


## "$ minigame moulinette sit_at=pcSeat win=c1.ok" -> {t: cmd, name, args, kw, src, raw}. Arguments are typed:
## "quoted" is a String, true/false a bool, digits a number, anything else a bare word (String); key=value goes
## into kw. A lone "=" is skipped, so `$ set choco = "pac"` reads as [choco, "pac"].
static func _command(t: String, src: String) -> Dictionary:
	var toks := tokens(t)
	var node := {"t": "cmd", "name": "", "args": [], "kw": {}, "src": src, "raw": t}
	if toks.is_empty():
		errors.append("%s: an empty command" % src)
		return node
	node.name = String(toks[0])
	for k in range(1, toks.size()):
		var raw := String(toks[k])
		if raw == "=":
			continue
		if _quoted(raw):
			node.args.append(_unquote(raw))
			continue
		var eq := raw.find("=")
		if eq > 0 and raw.substr(0, eq).is_valid_identifier():
			var val := raw.substr(eq + 1)
			node.kw[raw.substr(0, eq)] = _unquote(val) if _quoted(val) else literal(val, false)
			continue
		node.args.append(literal(raw, false))
	return node


## Splits a command line on blanks outside "quotes"; the quotes (and \" escapes) are kept in the tokens.
static func tokens(t: String) -> Array:
	var out: Array = []
	var cur := ""
	var quoted := false
	var i := 0
	while i < t.length():
		var c := t[i]
		if quoted and c == "\\" and i + 1 < t.length():
			cur += c + t[i + 1]
			i += 2
			continue
		if c == "\"":
			quoted = not quoted
			cur += c
		elif not quoted and (c == " " or c == "\t"):
			if cur != "":
				out.append(cur)
			cur = ""
		else:
			cur += c
		i += 1
	if quoted:
		errors.append("unclosed quote in '%s'" % t)
	if cur != "":
		out.append(cur)
	return out


static func _quoted(s: String) -> bool:
	return s.length() >= 2 and s.begins_with("\"") and s.ends_with("\"")


static func _unquote(s: String) -> String:
	if not _quoted(s):
		return s
	return s.substr(1, s.length() - 2).replace("\\\"", "\"").replace("\\\\", "\\")


## A bare word as a value: true, false, a number, else the word itself.
static func literal(s: String, quoted: bool):
	if quoted:
		return s
	if s == "true":
		return true
	if s == "false":
		return false
	if s.is_valid_int():
		return int(s)
	if s.is_valid_float():
		return float(s)
	return s


static func _re(pattern: String) -> RegEx:
	return RegEx.create_from_string(pattern)


# ------------------------------------------------------------------ compiling
## The steps of a cue for Dialogue.say(), acting on `runner` (Story, or a test's stand-in) when they run. `ctx`
## carries {"crowd": "crowd3"}: the `crowd` speaker becomes whoever Mano is talking to.
static func steps(cue: String, runner, ctx := {}) -> Array:
	load_all()
	if not cues.has(cue):
		push_error("DialogueData: no cue '%s'" % cue)
		return []
	return compile(cues[cue].body, runner, ctx)


static func compile(body: Array, runner, ctx := {}) -> Array:
	var out: Array = []
	for n: Dictionary in body:
		match String(n.t):
			"line":
				out.append(_compile_line(n, runner, ctx))
			"random":
				var group: Array = n.lines
				out.append(func():
					var pick: Dictionary = group[randi() % group.size()]
					runner.push([_compile_line(pick, runner, ctx)]))
			"if":
				out.append(func():
					for b in n.branches:
						if Conditions.eval(String(b.cond)):
							runner.push(compile(b.body, runner, ctx))
							return
					if n["else"] != null:
						runner.push(compile(n["else"], runner, ctx)))
			"cmd":
				out.append(func(): runner.command(n, ctx))
			"jump":
				var target := String(n.target)
				match String(n.mode):
					"end":
						out.append(func(): runner.end_now())
					"call":
						out.append(func(): runner.push(steps(target, runner, ctx)))
					_:
						out.append(func(): runner.jump(steps(target, runner, ctx)))
	return out


## A line with nothing to decide is a plain step; one with a condition, {{…}} or conditional responses is
## built when it is reached.
static func _compile_line(n: Dictionary, runner, ctx: Dictionary):
	var dynamic := String(n.cond) != "" or String(n.text).contains("{{")
	for r in n.ask:
		if String(r.cond) != "" or String(r.label).contains("{{"):
			dynamic = true
	if not dynamic:
		return _step(n, runner, ctx)
	return func():
		if String(n.cond) != "" and not Conditions.eval(String(n.cond)):
			return
		runner.push([_step(n, runner, ctx)])


static func _step(n: Dictionary, runner, ctx: Dictionary):
	var who := speaker(String(n.who), ctx)
	var text := format(String(n.text))
	if n.ask.is_empty():
		return [who, text, String(n.expr)] if String(n.expr) != "" else [who, text]
	var ask: Array = []
	for r in n.ask:
		if String(r.cond) != "" and not Conditions.eval(String(r.cond)):
			continue
		ask.append([format(String(r.label)), compile(r.body, runner, ctx)])
	return {"who": who, "t": text, "e": String(n.expr), "ask": ask}


static func speaker(who: String, ctx: Dictionary) -> String:
	if who == "crowd" and ctx.has("crowd"):
		return String(ctx.crowd)
	return who


## "{{coins}}" -> the flag's value, "{{word.party}}" -> data/words.json. Whole-number values print as integers.
static func format(text: String) -> String:
	if not text.contains("{{"):
		return text
	if _re_interp == null:
		_re_interp = RegEx.create_from_string("\\{\\{\\s*([a-z0-9_.]+)\\s*\\}\\}")
	var out := text
	for m in _re_interp.search_all(text):
		var key := m.get_string(1)
		var v
		if key.begins_with("word."):
			v = WorldData.word(key.substr(5))
		elif key.begins_with("song."):
			# the title of the song whose stem a flag holds: {{song.playlist}} -> "Evening" (data/songs.json)
			v = Chat.song_title(String(GameState.flags.get(key.substr(5), GameState.flag_default(key.substr(5)))))
		else:
			v = GameState.flags.get(key, GameState.flag_default(key))
		if v is float and v == floorf(v):
			v = int(v)
		out = out.replace(m.get_string(0), str(v))
	return out


# ------------------------------------------------------------------ thoughts that do not stop play (V2-10)
## A stage sound on the narrator's channel: the whole line is *between asterisks* ("*plink*", "*CLUNK*").
static func is_stage_sound(text: String) -> bool:
	var t := text.strip_edges()
	return t.length() >= 3 and t.begins_with("*") and t.ends_with("*")


## A cue made only of Mano's thoughts (`think`, and stage sounds) with no choice and only BARK_CMDS commands, in
## every branch and through every jump: main.interact() plays it as barks, so Mano is never frozen by a look-at.
static func is_think_only(cue: String) -> bool:
	load_all()
	if _think_cache.has(cue):
		return _think_cache[cue]
	_think_cache[cue] = false   # a jump back into itself is not think-only
	var ok: bool = cues.has(cue) and _think_body(cues[cue].body)
	_think_cache[cue] = ok
	return ok


static func _think_line(n: Dictionary) -> bool:
	return n.get("ask", []).is_empty() and (String(n.who) == "think" or (String(n.who) == "nar" and is_stage_sound(String(n.text))))


static func _think_body(body: Array) -> bool:
	for n: Dictionary in body:
		match String(n.t):
			"line":
				if not _think_line(n):
					return false
			"random":
				for l in n.lines:
					if not _think_line(l):
						return false
			"if":
				for b in n.branches:
					if not _think_body(b.body):
						return false
				if n["else"] != null and not _think_body(n["else"]):
					return false
			"cmd":
				if not String(n.name) in BARK_CMDS:
					return false
			"jump":
				if String(n.mode) != "end" and not is_think_only(String(n.target)):
					return false
	return true


# ------------------------------------------------------------------ walking the data
## Every card the data can show, once: {who, text, expr, cue, src, slot, interp}. Response labels are not cards.
static func cards() -> Array:
	load_all()
	var out: Array = []
	for id in cues:
		_cards_in(cues[id].body, id, out)
	return out


static func _cards_in(body: Array, cue: String, out: Array) -> void:
	for n: Dictionary in body:
		match String(n.t):
			"line":
				out.append({"who": n.who, "text": n.text, "expr": n.expr, "cue": cue, "src": n.src, "slot": n.slot,
					"interp": String(n.text).contains("{{"), "cond": n.cond})
				for r in n.ask:
					_cards_in(r.body, cue, out)
			"random":
				for l in n.lines:
					out.append({"who": l.who, "text": l.text, "expr": l.expr, "cue": cue, "src": l.src, "slot": l.slot,
						"interp": String(l.text).contains("{{"), "cond": l.cond})
			"if":
				for b in n.branches:
					_cards_in(b.body, cue, out)
				if n["else"] != null:
					_cards_in(n["else"], cue, out)


## Every node of a kind ("cmd", "jump", "line", "if", "random") with the cue it is in: [[cue, node], ...].
static func nodes(kind: String) -> Array:
	load_all()
	var out: Array = []
	for id in cues:
		_nodes_in(cues[id].body, id, kind, out)
	return out


static func _nodes_in(body: Array, cue: String, kind: String, out: Array) -> void:
	for n: Dictionary in body:
		if String(n.t) == kind:
			out.append([cue, n])
		match String(n.t):
			"line":
				for r in n.ask:
					if kind == "response":
						out.append([cue, r])
					_nodes_in(r.body, cue, kind, out)
			"random":
				if kind == "line":
					for l in n.lines:
						out.append([cue, l])
			"if":
				for b in n.branches:
					if kind == "branch":
						out.append([cue, b])
					_nodes_in(b.body, cue, kind, out)
				if n["else"] != null:
					_nodes_in(n["else"], cue, kind, out)
