@tool
extends EditorScenePostImport
# Post-import step for the campus level and prop glbs (set via import_script/path in their .import files).
# glTF COLOR_0 multiplies the base colour, but Godot's importer leaves vertex_color_use_as_albedo off,
# so the baked grime / macro variation would be ignored without this.
# Level parts named far_* (the backdrop beyond the playable streets) cast no shadows and stay out of SDFGI.

func _post_import(scene: Node) -> Object:
	_walk(scene)
	return scene

func _walk(n: Node) -> void:
	if n is MeshInstance3D and String(n.name).begins_with("far_"):
		var far := n as MeshInstance3D
		far.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		far.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	if n is MeshInstance3D and n.mesh:
		var m: Mesh = n.mesh
		for i in m.get_surface_count():
			if (m.surface_get_format(i) & Mesh.ARRAY_FORMAT_COLOR) == 0:
				continue
			var mat := m.surface_get_material(i) as BaseMaterial3D
			if mat:
				mat.vertex_color_use_as_albedo = true
	for c in n.get_children():
		_walk(c)
