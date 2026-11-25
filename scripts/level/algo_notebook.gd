class_name AlgoNotebook
extends Node3D
## Mano's algo notebook, open on the desk beside him for the opening's wake-up (docs/DESIGN.md §7): a small Seyès cahier
## (two 17 x 22 cm pages curving into the gutter, a navy cover under them) with the Dijkstra notes he was taking when
## he fell asleep (tools/py/notebook_tex.py), and his ballpoint across the right page. Built from code; the origin is
## the middle of the gutter on the desk top, the page tops point to local -Z (away from whoever sits at it).

const TEX := "res://assets/textures/notebook_algo/notebook_algo.png"
const W := 0.34    # both pages, metres
const D := 0.22
const COVER := 0.004   # how far the cover shows round the pages


func _ready() -> void:
	var paper := StandardMaterial3D.new()
	if ResourceLoader.exists(TEX):
		paper.albedo_texture = load(TEX)
	else:
		paper.albedo_color = Color("#faf8f2")
	paper.roughness = 0.88
	paper.cull_mode = BaseMaterial3D.CULL_DISABLED
	paper.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	var pages := MeshInstance3D.new()
	pages.name = "Pages"
	pages.mesh = _pages_mesh()
	pages.material_override = paper
	add_child(pages)
	var cover := StandardMaterial3D.new()
	cover.albedo_color = Color(0.08, 0.14, 0.33)
	cover.roughness = 0.42
	_box("Cover", Vector3(W + 2.0 * COVER, 0.002, D + 2.0 * COVER), Vector3(0, 0.001, 0), cover)
	var edge := StandardMaterial3D.new()
	edge.albedo_color = Color(0.9, 0.89, 0.85)
	edge.roughness = 0.9
	for s in [-1.0, 1.0]:   # the stacks of pages under each side, inset from the gutter where the pages dip
		_box("Stack", Vector3(W * 0.5 - 0.03, 0.006, D - 0.004), Vector3(s * (W * 0.25 + 0.015), 0.005, 0), edge)
	_pen()


## Height of the page surface `d` metres from the gutter: down in the gutter, up over the first 3.5 cm, then flat.
static func _lift(d: float) -> float:
	return 0.0035 + 0.0075 * sin(clampf(d / 0.035, 0.0, 1.0) * PI * 0.5) - 0.0012 * smoothstep(0.12, 0.17, d)


func _pages_mesh() -> ArrayMesh:
	var st := SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var nu := 48
	var nv := 6
	for j in nv + 1:
		for i in nu + 1:
			var u := float(i) / nu
			var v := float(j) / nv
			var x := (u - 0.5) * W
			var d := absf(x)
			var slope := (_lift(d + 0.001) - _lift(maxf(d - 0.001, 0.0))) / 0.002 * signf(x)
			st.set_normal(Vector3(-slope, 1.0, 0.0).normalized())
			st.set_uv(Vector2(u, v))
			st.add_vertex(Vector3(x, _lift(d), (v - 0.5) * D))
	for j in nv:
		for i in nu:
			var a := j * (nu + 1) + i
			var b := a + 1
			var c := a + nu + 1
			var e := c + 1
			for k in [a, b, c, b, e, c]:
				st.add_index(k)
	return st.commit()


func _box(n: String, size: Vector3, at: Vector3, mat: Material) -> void:
	var mi := MeshInstance3D.new()
	mi.name = n
	var bm := BoxMesh.new()
	bm.size = size
	mi.mesh = bm
	mi.position = at
	mi.material_override = mat
	add_child(mi)


## A clear hexagonal ballpoint with a blue cap, lying across the right page at a slant.
func _pen() -> void:
	var pen := Node3D.new()
	pen.name = "Pen"
	pen.position = Vector3(0.085, _lift(0.085) + 0.0042, 0.035)
	pen.rotation = Vector3(0, deg_to_rad(-28.0), deg_to_rad(90.0))
	add_child(pen)
	var barrel := StandardMaterial3D.new()
	barrel.albedo_color = Color(0.86, 0.89, 0.93)
	barrel.roughness = 0.12
	barrel.metallic_specular = 0.7
	var cap := StandardMaterial3D.new()
	cap.albedo_color = Color(0.11, 0.24, 0.66)
	cap.roughness = 0.35
	var parts := [[0.0042, 0.13, 0.0, barrel, 6], [0.0046, 0.034, 0.075, cap, 12], [0.0018, 0.012, -0.071, barrel, 8]]
	for p in parts:
		var mi := MeshInstance3D.new()
		var cm := CylinderMesh.new()
		cm.top_radius = p[0]
		cm.bottom_radius = p[0] if p[2] >= 0.0 else 0.0006
		cm.height = p[1]
		cm.radial_segments = p[4]
		cm.rings = 1
		mi.mesh = cm
		mi.position = Vector3(0, p[2], 0)
		mi.material_override = p[3]
		pen.add_child(mi)
