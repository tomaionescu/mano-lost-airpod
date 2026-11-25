class_name WorldView
extends Node
## HiDPI: the 3D world renders at one pixel per screen point in a SubViewport that is drawn under the UI,
## so text and UI are drawn at the Retina screen's native resolution while the 3D costs what it did in a 1x
## window. The upscaler (FSR2), glow, DOF and tonemapping all run at the output size, so dividing
## `scaling_3d_scale` alone keeps the 3D buffer small but still doubles the frame time at 3840 px.
## Active only when the window has more than one pixel per point; otherwise the root renders the 3D itself.
## The gameplay camera stays in the root (HUD projection, audio listener); a mirror camera renders here.

signal changed

## CanvasLayers in this group (the lens finish) are moved into the 3D view so they run at its resolution.
const POST_GROUP := "world_post"

var source: Camera3D
var viewport: SubViewport
var _cam: Camera3D
var _layer: CanvasLayer
var _rect: TextureRect
var _active := false
var _post_homes := {}   # CanvasLayer -> its parent outside the view


func _init(cam: Camera3D) -> void:
	source = cam


func _ready() -> void:
	process_priority = 1000   # after the camera rig has placed the camera for this frame
	viewport = SubViewport.new()
	viewport.name = "World3D"
	viewport.render_target_update_mode = SubViewport.UPDATE_DISABLED
	viewport.audio_listener_enable_3d = false
	viewport.gui_disable_input = true
	add_child(viewport)
	_cam = Camera3D.new()
	_cam.name = "Mirror"
	_cam.physics_interpolation_mode = Node.PHYSICS_INTERPOLATION_MODE_OFF
	viewport.add_child(_cam)
	_cam.current = true
	_layer = CanvasLayer.new()
	_layer.layer = -100
	add_child(_layer)
	_rect = TextureRect.new()
	_rect.set_anchors_preset(Control.PRESET_FULL_RECT)
	_rect.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_rect.stretch_mode = TextureRect.STRETCH_SCALE
	_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_rect.texture = viewport.get_texture()
	_layer.add_child(_rect)
	get_tree().root.size_changed.connect(_refresh)
	get_window().dpi_changed.connect(_refresh)
	set_process(false)   # _refresh() turns the mirror on with the view
	_refresh()


func is_active() -> bool:
	return _active


## Window pixels per screen point: 2 on a Retina Mac with HiDPI allowed, 1 otherwise. macOS converts window
## coordinates with the largest scale of all screens, so that is the one to use there.
static func pixels_per_point() -> float:
	if OS.get_name() == "macOS":
		return maxf(DisplayServer.screen_get_max_scale(), 1.0)
	return maxf(DisplayServer.screen_get_scale(), 1.0)


func _refresh() -> void:
	var root := get_tree().root
	var ppp := pixels_per_point()
	var want := ppp > 1.01 and DisplayServer.get_name() != "headless"
	if want:
		var sz := Vector2i((Vector2(root.size) / ppp).round())
		if viewport.size != sz:
			viewport.size = sz
	if want == _active:
		return
	_active = want
	if _active:
		_copy_settings(root)
	root.disable_3d = _active
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS if _active else SubViewport.UPDATE_DISABLED
	_layer.visible = _active
	set_process(_active)
	_move_post_layers.call_deferred()   # their parent may still be adding children
	_sync_camera(true)
	changed.emit()


## The root viewport carries the project's 3D settings (shadow atlas, AA, filtering); a SubViewport has its own.
func _copy_settings(from: Viewport) -> void:
	for p in ["msaa_3d", "screen_space_aa", "use_taa", "use_debanding", "use_occlusion_culling", "mesh_lod_threshold",
			"texture_mipmap_bias", "anisotropic_filtering_level", "fsr_sharpness", "vrs_mode", "use_hdr_2d",
			"positional_shadow_atlas_size", "positional_shadow_atlas_16_bits", "positional_shadow_atlas_quad_0",
			"positional_shadow_atlas_quad_1", "positional_shadow_atlas_quad_2", "positional_shadow_atlas_quad_3"]:
		viewport.set(p, from.get(p))


func _move_post_layers() -> void:
	if _active:
		for n in get_tree().get_nodes_in_group(POST_GROUP):
			if n is CanvasLayer and n.get_parent() != viewport:
				_post_homes[n] = n.get_parent()
				n.reparent(viewport, false)
	else:
		for n in _post_homes:
			if is_instance_valid(n) and is_instance_valid(_post_homes[n]):
				n.reparent(_post_homes[n], false)
		_post_homes.clear()


func _process(_dt: float) -> void:
	_sync_camera(false)


func _sync_camera(all: bool) -> void:
	if source == null or not is_instance_valid(source):
		return
	_cam.global_transform = source.global_transform
	if _cam.fov != source.fov:
		_cam.fov = source.fov
	if all or _cam.near != source.near or _cam.far != source.far:
		_cam.near = source.near
		_cam.far = source.far
	if all:
		_cam.cull_mask = source.cull_mask
		_cam.keep_aspect = source.keep_aspect
		_cam.h_offset = source.h_offset
		_cam.v_offset = source.v_offset
	if _cam.attributes != source.attributes:
		_cam.attributes = source.attributes
	if _cam.environment != source.environment:
		_cam.environment = source.environment
