class_name FallingLeaves
extends GPUParticles3D
## October leaves falling from every tree crown on campus (docs/DESIGN.md §4.8) in one particle system:
## scripts/fx/leaves.gdshader moves them, leaf_card.gdshader draws them. LevelBinder makes it from the tree props.
## Once the level's collision is in the physics space, the ground around each trunk is baked by raycasts, so a
## leaf lands on the road, the sidewalk, a bench or a picnic table instead of at the foot of its tree.

const ATLAS := "res://assets/textures/fx/leaves_fall.png"
const MAX_CROWNS := 32   # leaves.gdshader MAX_CROWNS
const CELL := 0.5        # metres per ground-map texel
const REACH := 5.5       # how far from its trunk a leaf may land
## Particles per crown: a leaf falls for 5-10 s of its 30 s cycle, so about five are in the air under each tree,
## half of them hidden in the crown or dark against it (6-12 on screen in the street or the courtyard).
const PER_CROWN := 20

var _crowns: Array = []   # [{centre: Vector3, radius: float, ground: float, birch: bool}]
var _pm: ShaderMaterial


func _init(crowns: Array) -> void:
	_crowns = crowns.slice(0, MAX_CROWNS)


func _ready() -> void:
	_pm = ShaderMaterial.new()
	_pm.shader = load("res://scripts/fx/leaves.gdshader")
	var c4 := PackedVector4Array()
	var info := PackedVector4Array()
	var box := AABB()
	for i in _crowns.size():
		var c: Dictionary = _crowns[i]
		c4.append(Vector4(c.centre.x, c.centre.y, c.centre.z, c.radius))
		info.append(Vector4(c.ground, 1.0 if c.birch else 0.0, 0.0, 0.0))
		var b := AABB(c.centre - Vector3(REACH, c.centre.y - c.ground + 1.0, REACH), Vector3(REACH, 0.0, REACH) * 2.0)
		b = b.expand(c.centre + Vector3.UP * (c.radius + 1.0))
		box = b if i == 0 else box.merge(b)
	_pm.set_shader_parameter("crown_count", _crowns.size())
	_pm.set_shader_parameter("crowns", c4)
	_pm.set_shader_parameter("crown_info", info)
	process_material = _pm
	var quad := QuadMesh.new()
	var mat := ShaderMaterial.new()
	mat.shader = load("res://scripts/fx/leaf_card.gdshader")
	mat.set_shader_parameter("atlas", load(ATLAS))
	quad.material = mat
	draw_pass_1 = quad
	# a leaf lives up to ~25 s (the slowest from the top of a plane tree, then 3 s on the ground)
	lifetime = 30.0
	amount = maxi(_crowns.size() * PER_CROWN, 8)
	preprocess = 20.0
	fixed_fps = 30
	interpolate = true
	local_coords = false
	cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	visibility_aabb = box
	await get_tree().physics_frame
	await get_tree().physics_frame
	_bake_ground(box)


## Ground heights around each trunk (level collision only: not people), as a float texture for the shader.
func _bake_ground(box: AABB) -> void:
	var w := int(ceilf(box.size.x / CELL))
	var h := int(ceilf(box.size.z / CELL))
	if w <= 0 or h <= 0 or w * h > 4_000_000:
		return
	var img := Image.create(w, h, false, Image.FORMAT_RF)
	img.fill(Color(-100.0, 0.0, 0.0))
	var space := get_world_3d().direct_space_state
	var q := PhysicsRayQueryParameters3D.new()
	q.collision_mask = 1
	var r := int(REACH / CELL)
	for c: Dictionary in _crowns:
		var cx := int((c.centre.x - box.position.x) / CELL)
		var cz := int((c.centre.z - box.position.z) / CELL)
		for iz in range(maxi(cz - r, 0), mini(cz + r + 1, h)):
			for ix in range(maxi(cx - r, 0), mini(cx + r + 1, w)):
				if (ix - cx) * (ix - cx) + (iz - cz) * (iz - cz) > r * r or img.get_pixel(ix, iz).r > -50.0:
					continue
				var x := box.position.x + (ix + 0.5) * CELL
				var z := box.position.z + (iz + 0.5) * CELL
				# from under the crown (a trunk the ray starts inside does not count) down past the trunk's foot
				q.from = Vector3(x, c.ground + 2.5, z)
				q.to = Vector3(x, c.ground - 3.0, z)
				var hit := space.intersect_ray(q)
				if not hit.is_empty():
					img.set_pixel(ix, iz, Color(hit.position.y, 0.0, 0.0))
	_pm.set_shader_parameter("ground", ImageTexture.create_from_image(img))
	_pm.set_shader_parameter("ground_rect", Vector4(box.position.x, box.position.z, 1.0 / (w * CELL), 1.0 / (h * CELL)))
