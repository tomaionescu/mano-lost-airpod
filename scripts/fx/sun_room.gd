extends Node3D
## A room the low sun comes into (docs/DESIGN.md §4.8): a FogVolume, so the sunlight draws shafts across it, and sparse
## dust motes (dust_mote.gdshader) that only show where the sun reaches them. LevelBinder makes one per
## LevelBinder.SUN_ROOMS zone; WorldEnv shows it only while the sun is up (set_lit), and only while the camera is in
## or near the room: through the walls nobody sees it, and a fog volume in view still costs its froxels. The volume
## spans the zone's footprint from its floor up to the ceiling found over its centre (level collision), so it
## follows the building.

## Seconds a mote lives (it fades in and out), and the most motes one room gets.
const DUST_LIFETIME := 16.0
const DUST_MAX := 3000
## How far outside the room the camera may be and still see it (a look through the door), and how often it checks.
const NEAR := 3.0
const CHECK_EVERY := 0.25

var fog: FogVolume
var dust: GPUParticles3D

var _box: AABB
var _room := AABB()
var _lit := true
var _near := false
var _check := 0.0
var _density := 0.03
var _dust_per_m3 := 0.1


func _init(box: AABB, density: float, dust_per_m3: float) -> void:
	_box = box
	_density = density
	_dust_per_m3 = dust_per_m3


func _ready() -> void:
	# the level's collision only answers queries after it has been through a physics step
	await get_tree().physics_frame
	await get_tree().physics_frame
	var c := _box.get_center()
	var space := get_world_3d().direct_space_state
	var top := _box.end.y
	var up := space.intersect_ray(PhysicsRayQueryParameters3D.create(c, c + Vector3.UP * 15.0, 1))
	if not up.is_empty():
		top = maxf(top, (up.position as Vector3).y - 0.05)
	var room := AABB(_box.position, Vector3(_box.size.x, top - _box.position.y, _box.size.z))
	_room = room.grow(NEAR)
	position = room.get_center()
	if _density > 0.0:
		fog = FogVolume.new()
		fog.shape = RenderingServer.FOG_VOLUME_SHAPE_BOX
		fog.size = room.size
		var m := FogMaterial.new()
		m.density = _density
		m.albedo = Color(1.0, 0.96, 0.9)
		m.edge_fade = 0.25
		fog.material = m
		add_child(fog)
	var n := mini(int(room.size.x * room.size.y * room.size.z * _dust_per_m3), DUST_MAX)
	if n > 0:
		dust = _make_dust(room.size, n)
		add_child(dust)
	_near = _camera_near()
	set_lit(_lit)


## Shown while the sun is up (WorldEnv) and the camera is near: hidden fog and dust cost nothing. The dust keeps
## drifting while the camera is away (a few thousand specks, cheap), so the room is never empty when Mano walks in.
func set_lit(on: bool) -> void:
	_lit = on
	visible = on and _near
	if dust and dust.emitting != on:
		dust.emitting = on


func _process(dt: float) -> void:
	_check -= dt
	if _check > 0.0 or _room.size == Vector3.ZERO:
		return
	_check = CHECK_EVERY
	var near := _camera_near()
	if near != _near:
		_near = near
		set_lit(_lit)


func _camera_near() -> bool:
	var cam := get_viewport().get_camera_3d()
	return cam != null and _room.has_point(cam.global_position)


func _make_dust(size: Vector3, n: int) -> GPUParticles3D:
	var p := GPUParticles3D.new()
	var pm := ParticleProcessMaterial.new()
	pm.emission_shape = ParticleProcessMaterial.EMISSION_SHAPE_BOX
	pm.emission_box_extents = size * 0.5
	pm.direction = Vector3.UP
	pm.spread = 180.0
	pm.initial_velocity_min = 0.0
	pm.initial_velocity_max = 0.02
	pm.gravity = Vector3(0.0, -0.002, 0.0)
	# slow eddies, so the motes drift and turn instead of falling
	pm.turbulence_enabled = true
	pm.turbulence_noise_strength = 1.0
	pm.turbulence_noise_scale = 3.0
	pm.turbulence_noise_speed_random = 0.3
	pm.turbulence_influence_min = 0.01
	pm.turbulence_influence_max = 0.03
	pm.scale_min = 0.6
	pm.scale_max = 1.4
	var fade := Gradient.new()
	fade.set_offset(0, 0.0)
	fade.set_color(0, Color(1, 1, 1, 0))
	fade.set_offset(1, 1.0)
	fade.set_color(1, Color(1, 1, 1, 0))
	fade.add_point(0.15, Color(1, 1, 1, 1))
	fade.add_point(0.85, Color(1, 1, 1, 1))
	var ramp := GradientTexture1D.new()
	ramp.gradient = fade
	pm.color_ramp = ramp
	p.process_material = pm
	var quad := QuadMesh.new()
	# a mote only reads when it covers a few pixels: 2 cm is a speck at 2-4 m, sub-pixel (gone) beyond
	quad.size = Vector2(0.022, 0.022)
	var mat := ShaderMaterial.new()
	mat.shader = preload("res://scripts/fx/dust_mote.gdshader")
	quad.material = mat
	p.draw_pass_1 = quad
	p.amount = n
	p.lifetime = DUST_LIFETIME
	p.preprocess = DUST_LIFETIME
	p.randomness = 0.5
	p.fixed_fps = 30
	p.interpolate = true
	p.local_coords = false
	p.visibility_aabb = AABB(-size * 0.5 - Vector3.ONE, size + Vector3.ONE * 2.0)
	p.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
	p.gi_mode = GeometryInstance3D.GI_MODE_DISABLED
	return p
