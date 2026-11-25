extends "res://scripts/dev/hair_still_viewer.gd"
## Dev: hair_still_viewer that also writes, per character, its skinned meshes as posed for the shots (CPU skinning of
## every surface: rest and posed vertex positions, indices, material names) and each shot's camera, so a frame's
## pixels can be traced back to the strand cards that cover them (tools/out/hf7r1_work/gpick.py).
## Godot --path . res://scenes/dev/hair_dump_viewer.tscn -- <stems> shots=<dir> [still=<s>]
## Writes res://shots/<dir>/<stem>.hdump (binary) and <stem>_cams.json.

var _cams := {}
var _dumped := false


func _load_next() -> void:
	_cams = {}
	_dumped = false
	super()


func _set_shot() -> void:
	super()
	var t := _cam.global_transform
	var vp := get_viewport().get_visible_rect().size
	_cams[String(_shots[_shot][0])] = {
		"basis": [t.basis.x.x, t.basis.x.y, t.basis.x.z, t.basis.y.x, t.basis.y.y, t.basis.y.z,
				t.basis.z.x, t.basis.z.y, t.basis.z.z],
		"origin": [t.origin.x, t.origin.y, t.origin.z], "fov": _cam.fov, "keep_aspect": _cam.keep_aspect,
		"vp": [vp.x, vp.y]}
	var dir := ProjectSettings.globalize_path(preload("res://scripts/dev/autotest.gd").shots_dir())
	var f := FileAccess.open("%s/%s_cams.json" % [dir, stems[_idx]], FileAccess.WRITE)
	f.store_string(JSON.stringify(_cams))
	f.close()


func _process(dt: float) -> void:
	if not _dumped and _frame >= 24 and _rig:
		_dumped = true
		_dump()
	super(dt)


func _dump() -> void:
	var dir := ProjectSettings.globalize_path(preload("res://scripts/dev/autotest.gd").shots_dir())
	var f := FileAccess.open("%s/%s.hdump" % [dir, stems[_idx]], FileAccess.WRITE)
	var n := 0
	for mi in _all_meshes(_rig):
		if mi.mesh == null or not mi.is_visible_in_tree():
			continue
		var skel: Skeleton3D = mi.get_node_or_null(mi.skeleton) as Skeleton3D
		var skin := mi.skin
		var binds: Array[Transform3D] = []
		if skel and skin:
			for b in skin.get_bind_count():
				var bi := skin.get_bind_bone(b)
				if bi < 0:
					bi = skel.find_bone(skin.get_bind_name(b))
				binds.append(skel.get_bone_global_pose(bi) * skin.get_bind_pose(b))
		for s in mi.mesh.get_surface_count():
			var arr := mi.mesh.surface_get_arrays(s)
			var vs: PackedVector3Array = arr[Mesh.ARRAY_VERTEX]
			var idx: PackedInt32Array = arr[Mesh.ARRAY_INDEX] if arr[Mesh.ARRAY_INDEX] != null else PackedInt32Array()
			var posed := PackedFloat32Array()
			var rest := PackedFloat32Array()
			posed.resize(vs.size() * 3)
			rest.resize(vs.size() * 3)
			var bones = arr[Mesh.ARRAY_BONES]
			var weights = arr[Mesh.ARRAY_WEIGHTS]
			var skinned: bool = binds.size() > 0 and bones != null and weights != null and bones.size() > 0
			var k: int = (bones.size() / vs.size()) if skinned else 0
			var xf: Transform3D = skel.global_transform if skinned else mi.global_transform
			for i in vs.size():
				var v := vs[i]
				rest[i * 3] = v.x
				rest[i * 3 + 1] = v.y
				rest[i * 3 + 2] = v.z
				var p := Vector3.ZERO
				if skinned:
					var wsum := 0.0
					for j in k:
						var w: float = weights[i * k + j]
						if w > 0.0:
							p += (binds[bones[i * k + j]] * v) * w
							wsum += w
					if wsum > 0.0:
						p /= wsum
					else:
						p = v
				else:
					p = v
				p = xf * p
				posed[i * 3] = p.x
				posed[i * 3 + 1] = p.y
				posed[i * 3 + 2] = p.z
			var mat := mi.mesh.surface_get_material(s)
			var mname := "%s|%s" % [mi.name, mat.resource_name if mat else ""]
			f.store_pascal_string(mname)
			f.store_32(vs.size())
			f.store_buffer(rest.to_byte_array())
			f.store_buffer(posed.to_byte_array())
			f.store_32(idx.size())
			f.store_buffer(idx.to_byte_array())
			# per vertex UV (2) and colour (4), zeros where the surface has none
			var uvs := PackedFloat32Array()
			uvs.resize(vs.size() * 2)
			if arr[Mesh.ARRAY_TEX_UV] != null:
				var u: PackedVector2Array = arr[Mesh.ARRAY_TEX_UV]
				for i in u.size():
					uvs[i * 2] = u[i].x
					uvs[i * 2 + 1] = u[i].y
			var cols := PackedFloat32Array()
			cols.resize(vs.size() * 4)
			if arr[Mesh.ARRAY_COLOR] != null:
				var c: PackedColorArray = arr[Mesh.ARRAY_COLOR]
				for i in c.size():
					cols[i * 4] = c[i].r
					cols[i * 4 + 1] = c[i].g
					cols[i * 4 + 2] = c[i].b
					cols[i * 4 + 3] = c[i].a
			f.store_buffer(uvs.to_byte_array())
			f.store_buffer(cols.to_byte_array())
			n += 1
	f.close()
	print("hair_dump: ", stems[_idx], " ", n, " surfaces")


static func _all_meshes(n: Node, out: Array[MeshInstance3D] = []) -> Array[MeshInstance3D]:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_all_meshes(c, out)
	return out
