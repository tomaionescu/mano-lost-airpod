extends CanvasLayer
## Full-screen lens finish drawn under the UI (post.gdshader, docs/DESIGN.md §4.6): the vignette closes in during
## conversations and sit-downs (it follows the letterbox), the film grain changes 24 times a second, halation and
## grain come from the time of day, and the sun flares when it is in frame outdoors and no building hides it.

const GRAIN_TEX := "res://assets/textures/fx/grain.png"
const VIGNETTE_PLAY := 0.22
const VIGNETTE_CINE := 0.34
const VIGNETTE_TWEEN := 0.6   # seconds from one to the other
const GRAIN_FPS := 24.0
const FLARE_FADE := 0.15      # seconds

## Set by main.gd: the time of day, indoors or out (halation, grain, flare) and the letterbox (vignette).
var world_env: WorldEnv
var hud: HUD
## A shot that is cinematic without the letterbox (a sit-down, an insert): the vignette closes in all the same.
var cinematic := false

var _rect: ColorRect
var _mat: ShaderMaterial
var _v1 := false
var _grain_on := true
var _grain_frame := -1
var _vignette := VIGNETTE_PLAY
var _flare := 0.0


func _ready() -> void:
	layer = 1
	process_priority = 1001   # after the WorldView has placed its camera for this frame: the flare reads it
	add_to_group(WorldView.POST_GROUP)   # on HiDPI it runs inside the 3D view, at its resolution
	_v1 = WorldEnv.lens_v1()
	_rect = ColorRect.new()
	_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_mat = ShaderMaterial.new()
	_mat.shader = load("res://scripts/dev/post_v1.gdshader" if _v1 else "res://scripts/fx/post.gdshader")
	if not _v1:
		_mat.set_shader_parameter("grain_tex", load(GRAIN_TEX))
	_rect.material = _mat
	add_child(_rect)
	GameState.settings_changed.connect(_apply)
	_apply()


func _apply() -> void:
	_grain_on = GameState.settings.get("film_grain", true)
	if _v1:
		_mat.set_shader_parameter("grain", 0.028 if _grain_on else 0.0)


func _process(dt: float) -> void:
	if _v1:
		_mat.set_shader_parameter("time_seed", float(Time.get_ticks_msec() % 100000) * 0.013)
		return
	var gf := int(Time.get_ticks_msec() * GRAIN_FPS / 1000.0)
	if gf != _grain_frame:
		_grain_frame = gf
		# R2 low-discrepancy steps: each grain frame lands far from the one before
		_mat.set_shader_parameter("grain_offset", Vector2(fposmod(gf * 0.7548777, 1.0), fposmod(gf * 0.5698403, 1.0)))
	_mat.set_shader_parameter("grain", (world_env.grain() if world_env else 0.025) if _grain_on else 0.0)
	var target := lerpf(VIGNETTE_PLAY, VIGNETTE_CINE, _cinematic())
	_vignette = move_toward(_vignette, target, dt * (VIGNETTE_CINE - VIGNETTE_PLAY) / VIGNETTE_TWEEN)
	_mat.set_shader_parameter("vignette", _vignette)
	if world_env:
		_mat.set_shader_parameter("halation", world_env.halation())
	_update_flare(dt)


## 0 while exploring, 1 in a conversation, a cutscene or a sit-down: how far the letterbox is in.
func _cinematic() -> float:
	if cinematic:
		return 1.0
	if hud == null or hud.root == null:
		return 0.0
	var vp := hud.root.get_viewport_rect().size
	var full := (vp.y - vp.x / 2.39) * 0.5
	return clampf(hud.letterbox_height() / full, 0.0, 1.0) if full > 1.0 else 0.0


## The sun's place on screen, and a flare faded in over FLARE_FADE while it is in frame, outdoors and not behind
## a building (level collision; the shader also checks the frame is bright there, for trees and people).
func _update_flare(dt: float) -> void:
	var want := 0.0
	var cam := get_viewport().get_camera_3d()
	if world_env and cam:
		var k := world_env.flare_strength()
		var far := cam.global_position + world_env.sun_dir * 500.0
		if k > 0.0 and not cam.is_position_behind(far):
			var uv := cam.unproject_position(far) / get_viewport().get_visible_rect().size
			var edge := minf(minf(uv.x, 1.0 - uv.x), minf(uv.y, 1.0 - uv.y))
			if edge > 0.0:
				var q := PhysicsRayQueryParameters3D.create(cam.global_position, far, 1)
				if cam.get_world_3d().direct_space_state.intersect_ray(q).is_empty():
					want = k * smoothstep(0.0, 0.05, edge)
			_mat.set_shader_parameter("sun_uv", uv)
		_mat.set_shader_parameter("flare_tint", world_env.flare_tint())
	_flare = lerpf(_flare, want, 1.0 - exp(-dt / FLARE_FADE))
	_mat.set_shader_parameter("flare", _flare)
