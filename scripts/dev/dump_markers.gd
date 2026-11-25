extends SceneTree
## Dev: print anchors and the props around them.
func _init():
	var root: Node3D = (load("res://assets/levels/campus.glb") as PackedScene).instantiate()
	get_root().add_child(root)
	await process_frame
	var anchors := {}
	var props := []
	_walk(root, anchors, props)
	for a in anchors:
		var xf: Transform3D = anchors[a]
		var f := xf.basis.z
		print("ANCHOR %s pos=%s yaw=%.2f fwd=%s" % [a, xf.origin, atan2(f.x, f.z), f])
		for p in props:
			var d: float = (p[1] as Transform3D).origin.distance_to(xf.origin)
			if d < 2.2:
				var pf: Vector3 = (p[1] as Transform3D).basis.z
				print("    near %s d=%.2f pos=%s yaw=%.2f" % [p[0], d, (p[1] as Transform3D).origin, atan2(pf.x, pf.z)])
	quit()

func _walk(n: Node, anchors: Dictionary, props: Array) -> void:
	var nm := String(n.name)
	if nm.begins_with("ANCHOR_") or nm.begins_with("SPOT_coffee") or nm.begins_with("NPC_madame"):
		anchors[nm] = (n as Node3D).global_transform
	elif nm.begins_with("PROP_"):
		props.append([nm, (n as Node3D).global_transform])
	for c in n.get_children():
		_walk(c, anchors, props)
