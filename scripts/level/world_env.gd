class_name WorldEnv
extends Node3D
## Lighting rig: the time-of-day sky (two HDRIs blended into a procedural twilight and city-night sky,
## scripts/fx/sky_blend.gdshader), the real sun of Thursday 15 October 2026, AgX tonemapping, GI, AO, fog,
## bloom and a colour grade per time of day. apply_time() moves between the TIMES presets and dims the lamp
## groups and lit windows LevelBinder found (bind_level()); set_interior() multiplies on top, and set_place() adds
## what the place being filmed changes (PLACES: exposure and the conversation fill per zone).
## The lens (docs/DESIGN.md §4.6): bloom through a lens-dirt glow map, depth of field per kind of shot
## (set_focus_preset()) with circle bokeh, and the values post_layer.gd reads (halation, grain, sun flare).
## Quality presets come from GameState.settings.quality (low / medium / high / ultra).

signal time_changed(time_name: String)

## The game frame (docs/CAMPUS_LAYOUT.md §2): +X runs along rue Pasteur toward compass bearing 76.4°, so true north
## is 13.6° clockwise from -Z. Origin 48.8154047 N, 2.3630521 E.
const FRAME_BEARING := 76.4
const HDRIS := ["res://assets/hdri/suburban_parking_area_2k.hdr", "res://assets/hdri/venice_sunset_2k.hdr"]
## u of each HDRI's own sun (its brightest texels, both about 3° up); the sky turns each panorama so that
## point sits on the real sun's bearing
const HDRI_SUN_U := [0.600, 0.600]
const DEFAULT_TIME := "golden"
## The light never comes from lower than this (no shadow acne on a grazing sun); the sky keeps the true position.
const MIN_SHADOW_ELEV := 2.0
## Compass degrees added to the sun's azimuth in every preset. 0 is the real sun; -14.6 puts it where v1 had it,
## which lights cour Pasteur at 17:42. autotest takes sun_nudge=<deg>.
var sun_nudge := 0.0

## Values every preset starts from; TIMES only lists what differs. sun / moon: [compass azimuth, elevation] in
## degrees, a negative elevation is under the horizon (the light is then off). ambient scales the sky's light
## (ambient, reflections and SDFGI, which ignores Environment.ambient_light_energy). Sky colours are linear.
const TIME_DEFAULTS := {
	"sun": [242.3, 11.5], "sun_color": Color(1.0, 0.74, 0.52), "sun_energy": 2.6, "sun_size": 0.8, "sun_disk": 1.0, "sun_fog": 1.1,
	"moon": [224.9, -1.0], "moon_glow": 0.0,
	"pano_t": 0.0, "sky_energy": 1.0, "sky_tint": Color(1, 1, 1), "night": 0.0,
	"zenith": Color(0.004, 0.006, 0.014), "horizon": Color(0.04, 0.03, 0.025), "glow": 0.0, "city": 0.0, "stars": 0.0,
	"ambient": 0.75, "ambient_tint": Color(1, 1, 1), "ambient_fill": Color(0, 0, 0),
	"fog_color": Color(0.86, 0.72, 0.6), "fog_energy": 0.5, "fog_scatter": 0.3, "fog_density": 0.0016, "vol_density": 0.008,
	"lamps": {"street_lamps": 0.0, "string_lights": 0.3, "classroom": 1.0}, "windows": 0.0,
	"exposure": 1.0, "contrast": 1.04, "saturation": 1.02, "halation": 0.05, "grain": 0.022,
	"convo_fill": 0.0, "convo_fill_color": Color(1.0, 0.9, 0.8),
	"grade": {"lift": 0.03, "shadow_tint": Vector3(-0.012, 0.004, 0.028), "high_tint": Vector3(0.03, 0.012, -0.03),
		"green_desat": 0.18, "curve": 0.22},
}
## the ambient every preset is measured against: golden's, which the HDRI was tuned for
const AMBIENT_REF := 0.75

## Time-of-day presets (docs/DESIGN.md §3.1, §4.4) for the campus (48.8154 N, 2.3631 E, CEST) on Thursday 15 October
## 2026: sun from the NOAA solar equations, moon from suncalc (waxing crescent, 24 % lit, sets 21:09).
## lamps: level per LevelBinder lamp group. windows: emission of the lit room cards. grade: _make_lut().
## Change presets only under a card, a fade or a cut.
const TIMES := {
	"golden": {"clock": "17:42"},
	"late_gold": {"clock": "18:15", "convo_fill": 0.13, "sun": [248.9, 6.6], "sun_color": Color(1.0, 0.63, 0.40), "sun_energy": 1.9, "sun_size": 1.0,
		"sun_fog": 1.2, "pano_t": 0.5, "sky_energy": 0.9, "ambient": 0.62, "fog_color": Color(0.90, 0.64, 0.50), "fog_scatter": 0.5,
		"lamps": {"string_lights": 0.6}, "windows": 0.3,
		"grade": {"lift": 0.036, "high_tint": Vector3(0.042, 0.012, -0.042)}},
	"last_light": {"clock": "18:50", "convo_fill": 0.5, "sun": [255.6, 1.3], "sun_color": Color(1.0, 0.50, 0.32), "sun_energy": 0.9, "sun_size": 1.4,
		"sun_fog": 1.4, "pano_t": 1.0, "sky_energy": 0.75, "ambient": 0.5, "fog_color": Color(0.84, 0.56, 0.52), "fog_scatter": 0.6,
		"lamps": {"street_lamps": 1.0, "string_lights": 1.0}, "windows": 0.8, "exposure": 1.05, "saturation": 1.0,
		"grade": {"lift": 0.035, "shadow_tint": Vector3(-0.008, -0.012, 0.045), "high_tint": Vector3(0.045, 0.0, -0.012)}},
	"blue": {"clock": "19:25", "convo_fill": 2.4, "convo_fill_color": Color(0.86, 0.9, 1.0), "sun": [262.1, -4.6], "sun_energy": 0.0, "sun_disk": 0.0, "moon": [205.6, 8.9], "moon_glow": 1.4,
		"pano_t": 1.0, "sky_energy": 0.2, "sky_tint": Color(0.85, 0.92, 1.15), "night": 0.3,
		"zenith": Color(0.010, 0.018, 0.045), "horizon": Color(0.05, 0.045, 0.06), "glow": 1.0, "city": 0.5, "stars": 0.15,
		"ambient": 0.6, "ambient_tint": Color(0.5, 0.62, 1.0), "ambient_fill": Color(0.025, 0.04, 0.085),
		"fog_color": Color(0.46, 0.52, 0.72), "fog_energy": 0.35, "fog_scatter": 0.0, "vol_density": 0.006,
		"lamps": {"street_lamps": 1.0, "string_lights": 1.0}, "windows": 1.5, "exposure": 1.4, "saturation": 1.04,
		"halation": 0.045, "grain": 0.025,
		"grade": {"lift": 0.03, "shadow_tint": Vector3(-0.03, 0.0, 0.07), "high_tint": Vector3(0.02, 0.008, -0.01), "curve": 0.15}},
	"night": {"clock": "21:30", "convo_fill": 1.8, "convo_fill_color": Color(1.0, 0.86, 0.72), "sun": [286.3, -25.1], "sun_energy": 0.0, "sun_disk": 0.0,
		"night": 1.0, "zenith": Color(0.003, 0.004, 0.008), "horizon": Color(0.02, 0.017, 0.016), "city": 1.0, "stars": 0.6,
		"ambient": 0.2, "ambient_fill": Color(0.018, 0.026, 0.058),
		"fog_color": Color(0.25, 0.28, 0.40), "fog_energy": 0.3, "fog_scatter": 0.0, "vol_density": 0.005,
		"lamps": {"street_lamps": 1.0, "string_lights": 1.0}, "windows": 1.5, "exposure": 1.45, "saturation": 0.98,
		"halation": 0.04, "grain": 0.028,
		"grade": {"lift": 0.025, "shadow_tint": Vector3(-0.022, -0.004, 0.05), "high_tint": Vector3(0.03, 0.01, -0.025), "curve": 0.2}},
	"late": {"clock": "23:45", "convo_fill": 1.8, "convo_fill_color": Color(1.0, 0.86, 0.72), "sun": [320.4, -43.7], "sun_energy": 0.0, "sun_disk": 0.0,
		"night": 1.0, "zenith": Color(0.003, 0.004, 0.008), "horizon": Color(0.018, 0.015, 0.014), "city": 0.9, "stars": 0.7,
		"ambient": 0.18, "ambient_fill": Color(0.017, 0.024, 0.054),
		"fog_color": Color(0.25, 0.28, 0.40), "fog_energy": 0.3, "fog_scatter": 0.0, "vol_density": 0.005,
		"lamps": {"street_lamps": 1.0, "string_lights": 1.0}, "windows": 1.2, "exposure": 1.45, "saturation": 0.98,
		"halation": 0.04, "grain": 0.028,
		"grade": {"lift": 0.025, "shadow_tint": Vector3(-0.02, -0.004, 0.046), "high_tint": Vector3(0.045, 0.016, -0.032), "curve": 0.2}},
}

## Light by place: what the zone the camera is in (LevelBinder.zone_at) changes on top of the time preset.
## keep: the share of the preset's exposure above 1 that the place keeps (a room's lamps do not follow the clock, so
## the night exposure tuned for the street over-exposes a lamp-lit room); gain: exposure on top of that; fill: the
## share of the conversation fill a face gets there. PLACE_IN is every other indoor zone, PLACE_OUT the open air.
## The Under is a dark-walled basement lit by a few coloured lamps, so it is exposed for. Voltaire's corridors and
## stairwell are white walls under ceiling panels.
const PLACE_OUT := {"keep": 1.0, "gain": 1.0, "fill": 1.0}
const PLACE_IN := {"keep": 1.0, "gain": 1.0, "fill": 0.4}
const PLACES := {
	"under": {"keep": 1.0, "gain": 1.5, "fill": 0.45},
	"volt_gf": {"keep": 0.0, "gain": 0.9, "fill": 0.4},
	"volt_f1": {"keep": 0.0, "gain": 0.9, "fill": 0.4},
}
## Seconds the exposure and the fill take to follow the camera into another place; a cut changes them at once.
const PLACE_EASE := 0.6
## The conversation fill is a key light: this many degrees round the face from the lens (to the camera's left,
## little enough to light a face turned either way) and above it, as far from the face as the lens (FILL_DIST: metres
## at least and at most), reaching FILL_REACH times that distance, so the wall behind the face stays in the scene's
## own light.
const FILL_SIDE := 18.0
const FILL_UP := 30.0
const FILL_DIST := [1.2, 3.0]
const FILL_REACH := 1.9

## Lens dirt (docs/DESIGN.md §4.6): the bloom is multiplied by this smudge map, at strength 0.25 outdoors and 0.1
## indoors. The map is procedural (tools/py/fx_textures.py), standing in for a photographed smudged phone lens.
const LENS_DIRT := "res://assets/textures/fx/lens_dirt.png"
const LENS_DIRT_OUT := 0.25
const LENS_DIRT_IN := 0.1
## Bloom intensity over clean glass. Godot's glow map darkens the glow where the map is black (mix(1, map,
## strength)), so the intensity is raised by the same factor and only the smudges add glow.
const GLOW_INTENSITY := 0.38
## Halation indoors, whatever the time of day.
const HALATION_IN := 0.03
## Depth of field per kind of shot (docs/DESIGN.md §4.6), for set_focus_preset(): the far blur starts `far` metres
## behind the focus and is full `far_tr` metres later; the near blur starts at `near_k` x the focus (or `near_m`
## metres) and is full `near_tr` metres nearer. "ots": over the shoulder, the listener's shoulder soft in front;
## "single": a clean single or close-up; "sit": a sit-down wide with a soft foreground; "insert": a poster, a
## phone, an object; "wide": two-shots, minigames and v1's look.
const DOF := {
	"wide": {"far": 1.6, "far_tr": 5.0, "amount": 0.06},
	"ots": {"far": 0.8, "far_tr": 3.0, "amount": 0.10, "near_k": 0.6, "near_tr": 0.4},
	"single": {"far": 0.5, "far_tr": 2.0, "amount": 0.14},
	"sit": {"far": 6.0, "far_tr": 15.0, "amount": 0.05, "near_m": 1.2, "near_tr": 0.8},
	"insert": {"far": 0.25, "far_tr": 0.6, "amount": 0.16},
}

var env: Environment
var sun: DirectionalLight3D
var attrs: CameraAttributesPractical
var we: WorldEnvironment
## the current preset, and the true direction toward the sun (it may be under the horizon), for the lens flare
var time_of_day := DEFAULT_TIME
var sun_dir := Vector3(0, 1, 0)

var _sky_mat: ShaderMaterial
var _cur: Dictionary = {}
var _tween: Tween
var _interior := 0.0
var _binder: LevelBinder         # for zone_at(): the place the camera is in
var _place := PLACE_OUT          # the PLACES entry in force, eased toward in _place_now
var _place_now := PLACE_OUT.duplicate()
var _place_cam := Vector3.INF    # where the camera was at the last set_place()
var _luts: Dictionary = {}       # preset -> ImageTexture3D
var _lut_key := ""
var _lamps: Dictionary = {}      # from LevelBinder
var _lamp_mats: Dictionary = {}
var _windows: Array = []
var _sun_fx: Array = []          # LevelBinder.sun_fx: fog volumes and dust that show only while the sun is up
var _sun_fx_lit := -1
var view: WorldView   # set by use_camera()
## The conversation fill: one unshadowed spot from beside and above the lens onto the face being filmed, faded in
## with the conversation; its energy is the preset's convo_fill (0 at golden) times the place's share, so faces
## stay readable at blue hour and at night. No GI, no shadows.
var fill: SpotLight3D
var _fill_a := 0.0


func _ready() -> void:
	env = Environment.new()
	var sky := Sky.new()
	# the shader turns each panorama itself (sky_rotation stays 0, so EYEDIR is game space); custom uniforms
	# put the radiance in incremental mode: it only updates when apply_time() changes the sky
	_sky_mat = ShaderMaterial.new()
	_sky_mat.shader = load("res://scripts/fx/sky_blend.gdshader")
	for i in HDRIS.size():
		if ResourceLoader.exists(HDRIS[i]):
			var pano: Texture2D = load(HDRIS[i])
			_sky_mat.set_shader_parameter("pano_a" if i == 0 else "pano_b", pano)
			_sky_mat.set_shader_parameter("haze_a" if i == 0 else "haze_b", _haze_of(pano))
		else:
			push_warning("WorldEnv: missing %s, the sky will be dark" % HDRIS[i])
	sky.sky_material = _sky_mat
	sky.radiance_size = Sky.RADIANCE_SIZE_256
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_sky_contribution = 1.0
	env.ambient_light_energy = 0.75
	env.reflected_light_source = Environment.REFLECTION_SOURCE_SKY
	env.tonemap_mode = Environment.TONE_MAPPER_AGX
	env.tonemap_exposure = 1.0
	env.tonemap_agx_white = 6.0
	env.tonemap_agx_contrast = 1.25
	# bloom (docs/DESIGN.md §4.6): highlights from just under 1, soft and wide, a little over everything, through the
	# lens-dirt map (its strength follows set_interior())
	var v1 := lens_v1()
	env.glow_enabled = true
	env.glow_normalized = true
	env.glow_intensity = 0.32 if v1 else GLOW_INTENSITY
	env.glow_strength = 0.9
	env.glow_bloom = 0.04 if v1 else 0.07
	env.glow_hdr_threshold = 1.0 if v1 else 0.9
	env.glow_hdr_scale = 1.5
	env.glow_blend_mode = Environment.GLOW_BLEND_MODE_SOFTLIGHT
	var levels := [0.0, 0.0, 1.0, 0.8, 0.6, 0.4, 0.2] if v1 else [0.0, 0.0, 1.0, 0.9, 0.7, 0.5, 0.3]
	for i in range(1, 8):
		env.set("glow_levels/%d" % i, levels[i - 1])
	if not v1 and ResourceLoader.exists(LENS_DIRT):
		env.glow_map = load(LENS_DIRT)
	# atmosphere: light haze lit by the sun, aerial perspective on distant buildings
	env.fog_enabled = true
	env.fog_light_color = Color(0.86, 0.72, 0.6)
	env.fog_light_energy = 0.5
	env.fog_sun_scatter = 0.35
	env.fog_density = 0.0016
	env.fog_aerial_perspective = 0.55
	env.fog_sky_affect = 0.15
	env.fog_height = -2.0
	env.fog_height_density = 0.0
	env.volumetric_fog_density = 0.008
	env.volumetric_fog_albedo = Color(0.95, 0.88, 0.8)
	env.volumetric_fog_anisotropy = 0.72
	env.volumetric_fog_length = 48.0
	env.volumetric_fog_gi_inject = 0.6
	env.volumetric_fog_sky_affect = 0.1
	env.volumetric_fog_temporal_reprojection_enabled = true
	# grade: contrast, saturation and the LUT come from the time-of-day preset
	env.adjustment_enabled = true
	env.adjustment_brightness = 1.0
	we = WorldEnvironment.new()
	we.environment = env
	attrs = CameraAttributesPractical.new()
	attrs.dof_blur_amount = 0.06
	we.camera_attributes = attrs
	add_child(we)

	sun = DirectionalLight3D.new()
	sun.name = "Sun"
	sun.light_bake_mode = Light3D.BAKE_STATIC   # cheaper in SDFGI; apply_time() rebuilds the GI after a change
	sun.shadow_enabled = true
	sun.shadow_bias = 0.03
	sun.shadow_normal_bias = 1.2
	sun.shadow_blur = 1.2
	sun.directional_shadow_mode = DirectionalLight3D.SHADOW_PARALLEL_4_SPLITS
	sun.directional_shadow_max_distance = 90.0
	sun.directional_shadow_blend_splits = true
	sun.directional_shadow_fade_start = 0.85
	add_child(sun)
	fill = SpotLight3D.new()
	fill.name = "ConvoFill"
	fill.shadow_enabled = false
	fill.light_bake_mode = Light3D.BAKE_DISABLED
	fill.light_specular = 0.2
	fill.spot_range = 7.0
	fill.spot_attenuation = 0.8
	fill.spot_angle = 28.0
	fill.spot_angle_attenuation = 1.6
	fill.visible = false
	add_child(fill)
	for arg in OS.get_cmdline_user_args():
		if arg.begins_with("sun_nudge="):   # dev: compare the real sun with a nudged one (see sun_nudge)
			sun_nudge = float(arg.substr(10))
	apply_time(DEFAULT_TIME)
	GameState.settings_changed.connect(apply_quality)
	get_window().dpi_changed.connect(apply_quality)   # moved between a Retina and a 1x screen
	apply_quality()


## The gameplay camera: on a HiDPI screen the world renders through a WorldView at one pixel per point.
func use_camera(cam: Camera3D) -> void:
	if view == null:
		view = WorldView.new(cam)
		view.name = "WorldView"
		view.changed.connect(apply_quality)
		add_child(view)
	apply_quality()


## The viewport that renders the 3D: the WorldView's at one pixel per point, or the window's.
func view_port() -> Viewport:
	return view.viewport if view and view.is_active() else get_viewport()


func apply_quality() -> void:
	var q: String = GameState.settings.get("quality", "high")
	var vp := view_port()
	var res_scale := 0.62
	match q:
		"low":
			env.sdfgi_enabled = false
			env.ssil_enabled = false
			env.ssao_enabled = true
			env.volumetric_fog_enabled = false
			env.ssr_enabled = false
			RenderingServer.directional_shadow_atlas_set_size(2048, true)
			res_scale = 0.5
		"medium":
			env.sdfgi_enabled = false
			env.ssil_enabled = true
			env.ssao_enabled = true
			env.volumetric_fog_enabled = true
			env.ssr_enabled = false
			RenderingServer.directional_shadow_atlas_set_size(4096, true)
			res_scale = 0.58
		"high", "ultra":
			env.sdfgi_enabled = true
			env.ssil_enabled = true
			env.ssao_enabled = true
			env.volumetric_fog_enabled = true
			env.ssr_enabled = q == "ultra"
			RenderingServer.directional_shadow_atlas_set_size(4096, true)
			res_scale = 0.77 if q == "ultra" else 0.62
	vp.scaling_3d_mode = Viewport.SCALING_3D_MODE_FSR2
	vp.scaling_3d_scale = res_scale if vp != get_viewport() else hidpi_scale(res_scale, vp.scaling_3d_mode)
	env.ssao_radius = 1.4
	env.ssao_intensity = 1.8
	env.ssao_power = 1.6
	env.ssao_detail = 0.6
	env.ssao_horizon = 0.06
	env.ssao_light_affect = 0.15
	env.ssil_radius = 4.0
	env.ssil_intensity = 0.9
	env.ssil_normal_rejection = 1.0
	env.sdfgi_use_occlusion = true
	env.sdfgi_read_sky_light = true
	env.sdfgi_cascades = 4
	env.sdfgi_min_cell_size = 0.15
	env.sdfgi_y_scale = Environment.SDFGI_Y_SCALE_75_PERCENT
	env.sdfgi_energy = 0.9
	env.sdfgi_bounce_feedback = 0.4
	env.ssr_max_steps = 48
	env.ssr_fade_in = 0.2
	env.ssr_fade_out = 2.0
	# depth of field only runs in shots (conversations, sit-downs, inserts, photo mode): round bokeh, high quality
	# with jitter (the temporal upscaler smooths it) where it can be afforded
	if not lens_v1():
		RenderingServer.camera_attributes_set_dof_blur_bokeh_shape(RenderingServer.DOF_BOKEH_CIRCLE)
		var dq: int = {"low": RenderingServer.DOF_BLUR_QUALITY_LOW, "medium": RenderingServer.DOF_BLUR_QUALITY_MEDIUM}.get(q, RenderingServer.DOF_BLUR_QUALITY_HIGH)
		RenderingServer.camera_attributes_set_dof_blur_quality(dq as RenderingServer.DOFBlurQuality, q in ["high", "ultra"])


## The presets are tuned for one window pixel per point. Without a WorldView, a HiDPI (Retina) window has
## scale² as many pixels, so the 3D buffer shrinks by the screen scale (the upscaler and post effects still
## run at the window size, which is why the game uses a WorldView); never below what the upscaler accepts.
static func hidpi_scale(base: float, mode: Viewport.Scaling3DMode) -> float:
	var s := base / WorldView.pixels_per_point()
	var lo := 0.25   # FSR2 has no hard floor; past 4x per axis it smears
	if mode == Viewport.SCALING_3D_MODE_METALFX_TEMPORAL and RenderingServer.get_rendering_device():
		var m := RenderingServer.get_rendering_device().limit_get(RenderingDevice.LIMIT_METALFX_TEMPORAL_SCALER_MIN_SCALE) / 1000000.0
		if m > 0.0 and m < 1.0:
			lo = m
	return clampf(s, lo, 1.0)


## Depth of field toward a focus distance (metres), or off: the v1 far blur ("wide").
func set_focus(distance: float, on: bool) -> void:
	set_focus_preset("wide" if on else "", distance)


## Depth of field for a kind of shot (a DOF key) focused `focus` metres away; "" (or an unknown kind) turns it off.
func set_focus_preset(kind: String, focus: float) -> void:
	var p: Dictionary = DOF.get("wide" if lens_v1() and kind != "" else kind, {})
	attrs.dof_blur_far_enabled = not p.is_empty()
	attrs.dof_blur_near_enabled = p.has("near_k") or p.has("near_m")
	if p.is_empty():
		return
	attrs.dof_blur_far_distance = focus + float(p.far)
	attrs.dof_blur_far_transition = p.far_tr
	attrs.dof_blur_amount = p.amount
	if attrs.dof_blur_near_enabled:
		attrs.dof_blur_near_distance = float(p.near_m) if p.has("near_m") else focus * float(p.near_k)
		attrs.dof_blur_near_transition = p.near_tr


## The DOF kind a shot gets from its lens when the caller names none (CameraRig.set_shot): long lenses are
## singles (an insert when the subject is under a metre away), 28-31° is over the shoulder, wider is "wide".
static func dof_kind(fov: float, focus: float) -> String:
	if fov <= 22.0:
		return "insert" if focus < 1.0 else "single"
	if fov <= 27.0:
		return "single"
	if fov <= 31.0:
		return "ots"
	return "wide"


## Waking-up blur: 1 = everything soft, 0 = only a gentle far blur behind `focus`.
func set_wake_blur(t: float, focus: float) -> void:
	attrs.dof_blur_far_enabled = true
	attrs.dof_blur_far_distance = lerpf(0.05, focus + 0.8, 1.0 - t)
	attrs.dof_blur_far_transition = lerpf(0.5, 3.0, 1.0 - t)
	attrs.dof_blur_near_enabled = t > 0.01
	attrs.dof_blur_near_distance = lerpf(focus * 1.5, 0.05, 1.0 - t)
	attrs.dof_blur_near_transition = 0.3
	attrs.dof_blur_amount = lerpf(0.06, 0.22, t)


## Exterior vs interior: indoors the sky contributes less and lamps carry the scene.
func set_interior(amount: float) -> void:
	_interior = clampf(amount, 0.0, 1.0)
	_apply_atmosphere()


# ------------------------------------------------------------------ lens values for post_layer.gd
## Dev A/B: "lens=v1" on the command line keeps v1's lens and stillness (its bloom, depth of field and post
## finish; no lens dirt, foliage sway, falling leaves, dust or fog volumes), to compare looks and frame times.
static func lens_v1() -> bool:
	return "lens=v1" in OS.get_cmdline_user_args()


## Strength of the film halation now: the preset's outdoors, HALATION_IN indoors.
func halation() -> float:
	return lerpf(float(_cur.get("halation", 0.05)), HALATION_IN, _interior)


## Film grain amount of the current preset.
func grain() -> float:
	return float(_cur.get("grain", 0.025))


## How strongly the sun can flare now (0..1): its light, faded at the horizon; nothing indoors.
func flare_strength() -> float:
	if not sun.visible:
		return 0.0
	var k := clampf(0.35 + 0.65 * sun.light_energy / 2.6, 0.0, 1.0)
	return k * smoothstep(-0.01, 0.04, sun_dir.y) * (1.0 - _interior)


## The flare's colour: warm white toward the sun's colour.
func flare_tint() -> Color:
	return Color(1.0, 0.8, 0.6).lerp(sun.light_color, 0.5)


# ------------------------------------------------------------------ time of day
## Moves to a TIMES preset over `seconds` (0 = at once). Call it only under a card, a fade, a sit-down or a cut:
## the static GI is rebuilt at the end, which takes a few frames. The name is kept in GameState.flags.time,
## so a save restores it.
func apply_time(time_name: String, seconds := 0.0) -> void:
	if not TIMES.has(time_name):
		push_warning("WorldEnv: unknown time of day '%s'" % time_name)
		return
	GameState.flags["time"] = time_name
	if time_name == time_of_day and not _cur.is_empty() and _tween == null:
		return
	time_of_day = time_name
	var to := _state_of(time_name)
	if _tween:
		_tween.kill()
		_tween = null
	if seconds <= 0.0 or _cur.is_empty():
		_cur = to
		_apply_state(_cur)
		_refresh_gi()
	else:
		var from := _cur
		var step := func(k: float) -> void:
			_cur = _mix(from, to, k)
			_apply_state(_cur)
		_tween = create_tween().set_pause_mode(Tween.TWEEN_PAUSE_PROCESS)   # a chapter card may pause the game
		_tween.tween_method(step, 0.0, 1.0, seconds)
		_tween.tween_callback(_end_tween)
	time_changed.emit(time_name)


## Every frame from main.gd: `on` while a conversation is filmed. The light stands off the lens axis (FILL_SIDE,
## FILL_UP), so it models the face instead of flattening it, and points at what the shot looks at; it fades in and
## out over 0.4 s. The place sets its share (PLACES: 40 % in a lamp-lit room).
func set_convo_fill(on: bool, cam: Camera3D, dt: float, look = null) -> void:
	var energy := float(_cur.get("convo_fill", 0.0)) if not _cur.is_empty() else 0.0
	_fill_a = move_toward(_fill_a, 1.0 if on and energy > 0.0 else 0.0, dt / 0.4)
	fill.visible = _fill_a > 0.001 and energy > 0.0
	if not fill.visible or cam == null:
		return
	var xf := cam.global_transform
	var at: Vector3 = look if look is Vector3 else xf.origin - xf.basis.z * 1.5
	var arm := xf.origin - at
	var d := clampf(arm.length(), FILL_DIST[0], FILL_DIST[1])
	var flat := Vector3(arm.x, 0.0, arm.z)
	flat = flat.normalized() if flat.length() > 0.01 else xf.basis.z
	var up := deg_to_rad(FILL_UP)
	fill.look_at_from_position(at + (flat.rotated(Vector3.UP, deg_to_rad(-FILL_SIDE)) * cos(up) + Vector3.UP * sin(up)) * d, at, Vector3.UP)
	fill.spot_range = d * FILL_REACH
	fill.light_energy = energy * _fill_a * float(_place_now.fill)
	fill.light_color = _cur.get("convo_fill_color", Color(1.0, 0.9, 0.8))


## Every frame from CameraRig: where the camera is. The zone it is in picks the PLACES entry; between zones (a
## stairwell, a crane shot over the roofs) the last indoor place holds while Mano is indoors. Exposure and fill
## ease to the new place over PLACE_EASE seconds, or change at once when the camera jumped (a cut, a teleport).
func set_place(cam_pos: Vector3, dt: float) -> void:
	var id := String(_binder.zone_at(cam_pos).get("id", "")) if _binder else ""
	if id != "":
		_place = PLACES.get(id, PLACE_IN if LevelBinder.INTERIORS.has(id) else PLACE_OUT)
	elif _interior < 0.5:
		_place = PLACE_OUT
	var k := 1.0 if cam_pos.distance_to(_place_cam) > 2.0 else 1.0 - exp(-dt / PLACE_EASE)
	_place_cam = cam_pos
	for key in _place:
		_place_now[key] = lerpf(_place_now[key], _place[key], k)
	_apply_exposure()


func _apply_exposure() -> void:
	if not _cur.is_empty():
		env.tonemap_exposure = lerpf(1.0, _cur.exposure, _place_now.keep) * float(_place_now.gain)


func _end_tween() -> void:
	_tween = null
	_refresh_gi()


## Takes the lamp groups and lit-window materials LevelBinder found and sets them to the current time.
func bind_level(b: LevelBinder) -> void:
	_binder = b
	_lamps = b.lamps
	_lamp_mats = b.lamp_materials
	_windows = b.window_materials
	_sun_fx = b.sun_fx
	_sun_fx_lit = -1
	if not _cur.is_empty():
		_apply_lamps(_cur)
		_apply_sun_fx()


## One lamp group to `level` (now or over `seconds`) on top of the current preset, until the next apply_time():
## e.g. the street lamps coming on at 18:55 in last_light. The GI bounce of the group is not rebuilt.
func set_lamps(group: String, level: float, seconds := 0.0) -> void:
	if _cur.is_empty():
		return
	var lamps: Dictionary = (_cur.lamps as Dictionary).duplicate()
	var from: float = lamps.get(group, 1.0)
	var step := func(k: float) -> void:
		lamps[group] = lerpf(from, level, k)
		_cur["lamps"] = lamps
		_apply_lamps(_cur)
	if seconds <= 0.0:
		step.call(1.0)
	else:
		create_tween().tween_method(step, 0.0, 1.0, seconds)


## The lamp groups the level has (see LevelBinder.LAMP_GROUPS).
func lamp_groups() -> Array:
	return _lamps.keys()


## Unit vector toward a point of the sky given as a compass azimuth (degrees clockwise from true north) and an
## elevation, in game space (+X toward bearing FRAME_BEARING, Y up).
static func sky_dir(azimuth: float, elevation: float) -> Vector3:
	var a := deg_to_rad(azimuth - FRAME_BEARING)   # 0 along +X, positive toward +Z
	var e := deg_to_rad(elevation)
	return Vector3(cos(a) * cos(e), sin(e), sin(a) * cos(e))


## Compass bearing (degrees from true north) of a horizontal game-space direction, e.g. for a map's north arrow.
static func bearing_of(dir: Vector3) -> float:
	return fposmod(rad_to_deg(atan2(dir.z, dir.x)) + FRAME_BEARING, 360.0)


func _state_of(time_name: String) -> Dictionary:
	var s := TIME_DEFAULTS.duplicate(true)
	var p: Dictionary = TIMES[time_name]
	for k in p:
		if s.get(k) is Dictionary:
			(s[k] as Dictionary).merge(p[k], true)
		else:
			s[k] = p[k]
	s["name"] = time_name
	s["sun_dir"] = sky_dir(s.sun[0] + sun_nudge, s.sun[1])
	s["moon_dir"] = sky_dir(s.moon[0], s.moon[1])
	return s


## Blend of two resolved presets; the grade (a LUT) switches halfway.
static func _mix(a: Dictionary, b: Dictionary, k: float) -> Dictionary:
	var out := b.duplicate()
	for key in b:
		var va = a.get(key)
		var vb = b[key]
		if (va is float or va is int) and (vb is float or vb is int):
			out[key] = lerpf(va, vb, k)
		elif va is Color and vb is Color:
			out[key] = (va as Color).lerp(vb, k)
		elif va is Vector3 and vb is Vector3:
			out[key] = (va as Vector3).slerp(vb, k)
		elif key == "lamps":
			var l := {}
			for g in vb:
				l[g] = lerpf(va.get(g, 1.0), vb[g], k)
			out[key] = l
	if k < 0.5:
		out["name"] = a.name
		out["grade"] = a.grade
	return out


func _apply_state(s: Dictionary) -> void:
	sun_dir = s.sun_dir
	var energy: float = s.sun_energy
	sun.visible = energy > 0.001 and sun_dir.y > -0.02
	sun.light_energy = energy
	sun.light_color = s.sun_color
	sun.light_angular_distance = s.sun_size
	sun.light_volumetric_fog_energy = s.sun_fog
	if sun.visible:
		var light_dir := sun_dir
		var lo := sin(deg_to_rad(MIN_SHADOW_ELEV))
		if light_dir.y < lo:
			var flat := Vector3(light_dir.x, 0.0, light_dir.z).normalized()
			light_dir = flat * cos(deg_to_rad(MIN_SHADOW_ELEV)) + Vector3.UP * lo
		sun.look_at_from_position(Vector3.ZERO, -light_dir, Vector3.UP)
	# each HDRI turned so its own sun sits on the real sun's bearing (yaw about +Y, as atan2(x, z))
	var want := atan2(sun_dir.x, sun_dir.z)
	var m := _sky_mat
	m.set_shader_parameter("yaw_a", want - (PI - TAU * HDRI_SUN_U[0]))
	m.set_shader_parameter("yaw_b", want - (PI - TAU * HDRI_SUN_U[1]))
	m.set_shader_parameter("pano_t", s.pano_t)
	m.set_shader_parameter("energy", s.sky_energy)
	m.set_shader_parameter("pano_tint", _vec(s.sky_tint))
	m.set_shader_parameter("sun_dir", sun_dir)
	m.set_shader_parameter("sun_color", _vec((s.sun_color as Color).srgb_to_linear()))
	m.set_shader_parameter("sun_disk", s.sun_disk)
	m.set_shader_parameter("night_t", s.night)
	m.set_shader_parameter("zenith", _vec(s.zenith))
	m.set_shader_parameter("horizon", _vec(s.horizon))
	m.set_shader_parameter("glow", s.glow)
	m.set_shader_parameter("city", s.city)
	m.set_shader_parameter("stars", s.stars)
	m.set_shader_parameter("moon_dir", s.moon_dir)
	m.set_shader_parameter("moon", s.moon_glow if (s.moon_dir as Vector3).y > -0.01 else 0.0)
	m.set_shader_parameter("ambient_gain", s.ambient / AMBIENT_REF)
	m.set_shader_parameter("ambient_tint", _vec(s.ambient_tint))
	m.set_shader_parameter("ambient_fill", _vec(s.ambient_fill))
	env.fog_light_color = s.fog_color
	env.fog_light_energy = s.fog_energy
	env.fog_sun_scatter = s.fog_scatter
	_apply_exposure()
	env.adjustment_contrast = s.contrast
	env.adjustment_saturation = s.saturation
	if _lut_key != s.name:
		_lut_key = s.name
		if not _luts.has(_lut_key):
			_luts[_lut_key] = _make_lut(s.grade)
		env.adjustment_color_correction = _luts[_lut_key]
	_apply_atmosphere()
	_apply_lamps(s)
	_apply_sun_fx()


## The sunbeam rooms (LevelBinder.SUN_ROOMS) only while the sun shines.
func _apply_sun_fx() -> void:
	var lit := 1 if sun.visible and sun_dir.y > 0.0 else 0
	if lit == _sun_fx_lit:
		return
	_sun_fx_lit = lit
	for n in _sun_fx:
		if is_instance_valid(n):
			n.set_lit(lit == 1)


func _apply_atmosphere() -> void:
	if _cur.is_empty():
		return
	env.ambient_light_energy = AMBIENT_REF * lerpf(1.0, 0.6, _interior)   # the preset's ambient is in the sky
	env.fog_density = _cur.fog_density * lerpf(1.0, 0.375, _interior)
	env.volumetric_fog_density = _cur.vol_density * lerpf(1.0, 0.5, _interior)
	if env.glow_map:
		env.glow_map_strength = lerpf(LENS_DIRT_OUT, LENS_DIRT_IN, _interior)
		env.glow_intensity = GLOW_INTENSITY / (1.0 - env.glow_map_strength)


## Lamp groups scale their exported energy (0 hides the light, so it costs nothing); bulbs and lamp heads
## follow; the room cards take the preset's absolute emission.
func _apply_lamps(s: Dictionary) -> void:
	var levels: Dictionary = s.lamps
	for g in _lamps:
		var k: float = levels.get(g, 1.0)
		for l in _lamps[g]:
			if is_instance_valid(l):
				l.light_energy = float(l.get_meta("base_energy", 1.0)) * k
				l.visible = k > 0.001
	for g in _lamp_mats:
		var k: float = levels.get(g, 1.0)
		for mat in _lamp_mats[g]:
			mat.emission_energy_multiplier = float(mat.get_meta("base_emission", 1.0)) * k
	for mat in _windows:
		if mat is ShaderMaterial:
			mat.set_shader_parameter("emission_energy", s.windows)
		else:
			mat.emission_energy_multiplier = s.windows


## The sun and the lamps are static lights in SDFGI (cheaper), so their bounce does not follow a change of
## time by itself: SDFGI is dropped for two frames and rebuilt.
func _refresh_gi() -> void:
	if not env.sdfgi_enabled or not is_inside_tree():
		return
	env.sdfgi_enabled = false
	await get_tree().process_frame
	await get_tree().process_frame
	env.sdfgi_enabled = GameState.settings.get("quality", "high") in ["high", "ultra"]


static func _vec(c: Color) -> Vector3:
	return Vector3(c.r, c.g, c.b)


## What the sky shows under the horizon instead of a panorama's own ground: the mean colour of its horizon band
## (2-10° up, the sun capped as in the shader) at the mean brightness of its ground. Linear RGB.
static func _haze_of(pano: Texture2D) -> Vector3:
	var img := pano.get_image()
	if img == null:
		return Vector3(0.1, 0.1, 0.1)
	if img.is_compressed():
		img.decompress()
	var w := img.get_width()
	var h := img.get_height()
	var lum := Vector3(0.2126, 0.7152, 0.0722)
	var band := Vector3.ZERO
	var n := 0
	for y in range(int(h * 80.0 / 180.0), int(h * 88.0 / 180.0)):
		for x in range(0, w, 8):
			var c := _vec(img.get_pixel(x, y))
			band += c * minf(1.0, 6.0 / maxf(c.dot(lum), 0.0001))
			n += 1
	var ground := 0.0
	var m := 0
	for y in range(int(h * 0.6), int(h * 0.9), 4):
		for x in range(0, w, 16):
			ground += _vec(img.get_pixel(x, y)).dot(lum)
			m += 1
	band /= maxf(n, 1)
	return band * (ground / maxf(m, 1)) / maxf(band.dot(lum), 0.0001)


## 17³ grading LUT, applied after tonemapping: green desaturated toward olive, split toning (shadows and
## highlights), a gentle filmic S and lifted blacks.
func _make_lut(g: Dictionary) -> ImageTexture3D:
	var n := 17
	var lift: float = g.get("lift", 0.018)
	var shadow_tint: Vector3 = g.get("shadow_tint", Vector3.ZERO)
	var high_tint: Vector3 = g.get("high_tint", Vector3.ZERO)
	var green_desat: float = g.get("green_desat", 0.0)
	var curve: float = g.get("curve", 0.18)
	var images: Array[Image] = []
	for b in n:
		var img := Image.create(n, n, false, Image.FORMAT_RGB8)
		for gr in n:
			for r in n:
				var c := Vector3(r, gr, b) / float(n - 1)
				var lum := c.dot(Vector3(0.2126, 0.7152, 0.0722))
				if green_desat > 0.0:
					# foliage hues (yellow-green to green) lose some saturation, so trees read olive, not lime
					var col := Color(c.x, c.y, c.z)
					var w := clampf(1.0 - absf(col.h - 0.27) / 0.12, 0.0, 1.0) * col.s
					c = c.lerp(Vector3.ONE * lum, green_desat * w)
				var shadow := clampf(1.0 - lum * 2.2, 0.0, 1.0)
				var high := clampf((lum - 0.45) * 1.8, 0.0, 1.0)
				c += shadow_tint * shadow
				c += high_tint * high
				c = c.lerp(c * c * (Vector3.ONE * 3.0 - 2.0 * c), curve)
				c = c * (1.0 - lift * 1.4) + Vector3.ONE * lift
				img.set_pixel(r, gr, Color(clampf(c.x, 0, 1), clampf(c.y, 0, 1), clampf(c.z, 0, 1)))
		images.append(img)
	var tex := ImageTexture3D.new()
	tex.create(Image.FORMAT_RGB8, n, n, n, false, images)
	return tex
