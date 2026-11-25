extends "res://scripts/dev/char_viewer.gd"
## Dev: char_viewer with the idle clip held still at one time ("still=<seconds>", default 2.0), so two builds of a
## character can be compared shot for shot (the idle tree's time at each shot depends on the frame times, and the
## head turned differently from run to run). Godot --path . res://scenes/dev/hair_still_viewer.tscn -- <stems> shots=<dir>


func _load_next() -> void:
	super()
	var t := 2.0
	for a in OS.get_cmdline_user_args():
		if a.begins_with("still="):
			t = float(a.substr(6))
	if _rig and _rig.anim_player and _rig.has_clip("idle"):
		_rig.tree.active = false
		_rig.anim_player.play(_rig._clips["idle"])
		_rig.anim_player.seek(t, true)
		_rig.anim_player.speed_scale = 0.0
