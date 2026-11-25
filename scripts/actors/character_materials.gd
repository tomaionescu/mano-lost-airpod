class_name CharacterMaterials
extends RefCounted
## Replaces the plain glTF materials of a character with game shaders, by kind. Mesh and material names are
## "<id>_<kind>_<asset>" (see tools/blender/build_human.py); the material decides per surface, so a scanned
## body (scan_wrap.py) gets skin on its head and hands and fabric everywhere else.

const KINDS := ["skin", "cloth", "hair", "hairshell", "hairunder", "haircap", "brow", "lash", "eye", "cornea", "teeth", "tongue", "glasses"]

static var _pores: Texture2D
static var _hair_shader: Shader = preload("res://scripts/fx/hair.gdshader")
static var _hair_fringe_shader: Shader = preload("res://scripts/fx/hair_fringe.gdshader")
## Scanned hair as strand cards over the scan's shell (tools/blender/hair_scan_cards.py): the cards (their material
## name has "scancards"), the shell as their dark matte underlayer (kind "hairunder") and a scalp cap ("haircap").
static var _hair_scan_shader: Shader = preload("res://scripts/fx/hair_scan.gdshader")
## The cards over the ears, when a build makes them their own surface ("<id>_hair_scancards_ear", style ear_stencil):
## the same shading, but they do not mark the stencil as hair, so the glasses' arms are not drawn over them.
static var _hair_scan_ear_shader: Shader = preload("res://scripts/fx/hair_scan_ear.gdshader")
static var _hair_scan_fringe_shader: Shader = preload("res://scripts/fx/hair_scan_fringe.gdshader")
static var _hair_under_shader: Shader = preload("res://scripts/fx/hair_under.gdshader")
static var _eye_shader: Shader = preload("res://scripts/fx/eye.gdshader")
## Glasses: opaque frames and clear premultiplied lenses (glasses.gdshader), drawn before the scan hair's blended
## passes; a second pass draws the temple arms over the hair grown a few mm above them (glasses_over_hair.gdshader,
## stencil 2 = hair, written by the scan hair's core and underlayer; the skin of a character with glasses writes 0).
static var _glasses_shader: Shader = preload("res://scripts/fx/glasses.gdshader")
static var _glasses_over_hair_shader: Shader = preload("res://scripts/fx/glasses_over_hair.gdshader")
static var _arm_masks := {}
## Per-person finishes the glb does not carry, keyed by the person's id (the meshes' name prefix "<id>_"); anyone not
## listed keeps the defaults. Set as shader uniforms on every pass that has them (_finish).
##  - "glasses" (glasses.gdshader and its arm pass): Mano's frames are dark matte metal (cast.py: #3a3c41, metal 0.85),
##    but a textured frame reaches the glb with metallicFactor 0. As a glossy grey dielectric (roughness 0.22, specular
##    0.8: F0 0.1, its albedo lit like skin) the front bar reads as a flat mid-grey slab, and the endpiece's flat outer
##    facet (one normal over ~30 mm2) mirrors the fill light whole into a bloomed white star.
##    Joaquin's black acetate frames are satin (roughness 0.32, specular 0.45: F0 0.03, a plastic's) instead of the
##    default patent gloss, whose tube-shaped rims draw long sharp white streaks that matte frames never show.
##  - "eye" (eye.gdshader): iris_specular 0, no sheen of the iris' own (it turns brown irises blue at three-quarters,
##    a whitish smear beside the pupil); the cornea shell keeps the eyes' sharp highlights.
##    iris_recolor 1 with iris_color (and a collar round the pupil, iris_inner_*) sets the iris colour directly where
##    the build's (cast.py eye_color, x1.8) renders off: under char_viewer's warm key grey-green irises come out
##    amber and near-black ones light copper. Tuned in glass_probe at one pose.
const FINISH := {
	"mano": {"glasses": {"frame_metallic": 0.85, "frame_roughness": 0.45, "frame_specular": 0.5},
			"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.12, 0.095, 0.08)}},
	"anisha": {"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.17, 0.125, 0.1)}},
	# grey-green with a faint brown collar round the pupil
	"ian": {"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.275, 0.285, 0.245),
			"iris_inner_color": Color(0.3, 0.25, 0.18), "iris_inner_r": 0.42}},
	# grey-green, a little darker and cooler, a hint of olive round the pupil
	"joaquin": {"glasses": {"frame_roughness": 0.32, "frame_specular": 0.45},
			"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.215, 0.24, 0.225),
			"iris_inner_color": Color(0.24, 0.235, 0.18), "iris_inner_r": 0.4}},
	# Toma. Eyes: dark brown irises with no sheen of their own; with the scan's sheen and the cornea's sky reflection
	# over a mid-brown iris they read as flat slate-grey at the Amphi 4 dialogue cameras.
	# Hair (scan cards): near-black curls take the sun and the lamps only as thin glints between their own shadows, so
	# untreated they read as one blue-black mass in Amphi 4. The tint lifts the albedo (most in blue, taking the atlas'
	# warm brown toward a neutral dark brown). The ambient light sees the cards x4.2 and the underlayer x3.5
	# (ambient_gain), warmed toward the hair's own hue (ambient_warm) and a little greener and less blue
	# (ambient_tint): the sky's blue ambient otherwise turns dark hair violet at golden hour and mauve at night.
	# Stronger strand highlights, broken up along the strands (scan_spec1/2_strength, glint_*), keep the curls
	# readable. lock_* shades each lock as a rounded tube with dark gaps between locks and its highlight on its core
	# (hair_scan.gdshaderinc), so the hair shows defined waves from the 1.35 m dialogue camera. glint_near cuts the
	# strand highlight to x0.2 nearer than 0.8 m (full from 1.1 m): up close under a key light it shows as pale foil
	# patches on the top front and zig-zag ribbons on the front and temple locks.
	"toma": {"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.12, 0.08, 0.055)},
			"hair": {"tint": Color(1.65, 1.705, 1.815), "ambient_gain": 4.2, "ambient_warm": 0.8,
					"scan_spec1_strength": 1.5, "scan_spec2_strength": 0.65, "glint_gain": 1.5, "glint_pow": 1.6,
					"glint_max": 2.0, "ambient_tint": Vector3(1.0, 1.08, 0.9),
					"lock_roll": 0.8, "lock_gap": 0.45, "lock_crest": 0.7, "lock_lod": 2.0, "glint_near": 0.2},
			"hairunder": {"ambient_gain": 3.5}},
	# Silvia. Eyes: warm dark brown irises, the whites a little darker (tint) and shaded at the edges and under the lid,
	# lighter lashes and a small resting lid drop (rig, CharacterRig). Glasses: the round asset's leopard print is
	# flattened to plain grey acetate (frame_flat, frame_color), satin, not metal, and its tinted lens gradient is cut to
	# a quarter (lens_tint: at full strength it reads as a milky film over the eyes). The frames are two-tone
	# (frame_grad): dark olive-grey at the top fading to clear at the bottom. The arms are not redrawn over the hair
	# (arm_over_hair 0): long hair covers them.
	"silvia": {"glasses": {"frame_metallic": 0.0, "frame_roughness": 0.32, "frame_specular": 0.45,
			"frame_flat": 1.0, "frame_color": Color(0.522, 0.549, 0.525), "lens_tint": 0.25,
			# the olive-grey holds to just over halfway down the front, then fades to the clear bottom (grad_range); with
			# a fainter bottom (frame_bottom_alpha 0.3) the frames read as thin pale wire
			"frame_grad": 1.0, "frame_top": Color(0.36, 0.39, 0.33), "frame_bottom": Color(0.86, 0.86, 0.83),
			"frame_bottom_alpha": 0.45, "grad_range": Vector2(0.55, 1.0), "arm_over_hair": 0.0,
			# no lens reflection: at the -30 deg dialogue camera a lens mirrors the low sun as a white disc over the
			# eye, and a dimmer, broader reflection veils the top half of the lens. The frames carry the glasses.
			"lens_specular": 0.0, "lens_roughness": 0.3},
			"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.15, 0.095, 0.075),
			"tint": Color(0.85, 0.83, 0.81), "edge_shade": 0.58, "lid_shade": 0.42},
			# Hair (scan cards, light and warm-toned). It takes the lights' full colour (diffuse_light_tint 1,
			# spec_light_tint 0.8): lit partly white at last light it otherwise reads silver-lilac beside an orange-lit
			# face. The direct lights see a paler, less red albedo (direct_sat, direct_tint), or the golden sun turns it
			# copper; under a more saturated sun they see more of its colour again (direct_sat_warm over
			# warm_light_range), so it does not go grey-pink at last light. The ambient light sees it warmer and
			# brighter (ambient_warm, ambient_tint, ambient_gain), which keeps the shaded side apricot under the blue
			# sky instead of mauve-grey. spec_tone with spec_tone_range keeps the highlight off the darker root cards.
			"hair": {"ambient_warm": 1.0, "diffuse_light_tint": 1.0, "spec_light_tint": 0.8, "spec_tone": 1.0,
				"tint": Color(0.86, 0.872, 0.895), "direct_sat": 0.2, "direct_tint": Vector3(0.92, 0.92, 1.25),
				"ambient_tint": Vector3(1.0, 0.96, 0.7), "ambient_gain": 1.9, "spec_tone_range": Vector2(0.26, 0.5),
				"direct_sat_warm": 0.6, "warm_light_range": Vector2(0.8, 0.9)},
			"hairunder": {"ambient_warm": 1.0},
			"lash": {"alpha": 0.6},
			# the teeth take no ambient light: the sky turns the back teeth slate-blue at the mouth's corners
			"teeth": {"no_ambient": true},
			"rig": {"lid_rest": 0.12}},
	# Ishita. Glasses: thin gold metal frames (the round asset's leopard print flattened to gold, metallic) with clear
	# lenses (lens_tint 0: the asset's tinted gradient reads as amber discs with a thick cream edge). Eyes: warm dark
	# brown irises without their own sheen, lighter lashes and a small resting lid drop. Hair (MakeHuman cards): both
	# highlights halved (at full strength they are broad tan bands on black) and the backlit glow cut
	# (scatter_strength: the hair's inner side lights up as a tan patch under the far jaw at the +30 deg dialogue
	# camera). Teeth darker, warmer and less glossy (at the defaults they read silver-white with a glint as she
	# talks). Brow cards darker and denser (brow: the soft edges filled in), so they hold at the dialogue cameras.
	"ishita": {"glasses": {"lens_tint": 0.0, "frame_flat": 1.0, "frame_color": Color(0.78, 0.64, 0.40),
			"frame_metallic": 0.9, "frame_roughness": 0.3},
			"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.20, 0.115, 0.055)},
			"hairgen": {"spec1_strength": 0.1, "spec2_strength": 0.2, "scatter_strength": 0.1},
			"teeth": {"roughness": 0.55, "specular": 0.25, "tint": Color(0.8, 0.75, 0.68)},
			"brow": {"tint": Color(0.42, 0.38, 0.34), "alpha": 2.2},
			"lash": {"alpha": 0.6}, "rig": {"lid_rest": 0.1}},
	# Cristina. Eyes: dark brown irises without their own sheen (with it they render red-brown and blue-grey at
	# three-quarters), lighter lashes and a resting lid drop. Braids (generated cards): highlights halved (glossy tan
	# streaks otherwise), a lighter, less red tint (with cast.py's hair_colors), little darkening at the roots
	# (root_dark) and 3x the ambient light (gen_ambient_gain; the direct lights unchanged): at night in Amphi 4, lit
	# mostly by the ambient, they otherwise read black.
	"cristina": {"eye": {"iris_specular": 0.0, "iris_recolor": 1.0, "iris_color": Color(0.10, 0.065, 0.045)},
			"hairgen": {"spec1_strength": 0.1, "spec2_strength": 0.2, "root_dark": 0.1, "tint": Color(1.25, 1.3, 1.3),
				"gen_ambient_gain": 3.0},
			"lash": {"alpha": 0.7}, "rig": {"lid_rest": 0.24}},
}
static var _hair_shell_shader: Shader = preload("res://scripts/fx/hair_shell.gdshader")
## The strand shader for a scan's sculpted hair shell (hair_shell.gdshader) is experimental: off unless
## "hairshell=shader" is on the command line. Without it a shell gets the plain soft-sheen material (_make).
static var _hair_shell_on := "hairshell=shader" in OS.get_cmdline_user_args()


static func apply(root: Node, quality := "high", far := 0.0) -> void:
	var meshes := _meshes(root)
	var has_glasses := meshes.any(func(x: MeshInstance3D) -> bool: return _kind_of(x.name) == "glasses")
	for mi in meshes:
		mi.gi_mode = GeometryInstance3D.GI_MODE_DISABLED   # skinned and moving: receive GI, never voxelised into it
		if far > 0.0:
			# distant people fade out instead of costing skinning + shadows across the whole campus
			mi.visibility_range_end = far
			mi.visibility_range_end_margin = 4.0
			mi.visibility_range_fade_mode = GeometryInstance3D.VISIBILITY_RANGE_FADE_SELF
		# the body mesh is "<id>_body": its kind comes from its materials
		var kind := _kind_of(mi.name)
		# the crowd (far < 50) gets cheaper hair: no soft fringe pass, no hair shadows
		var hero := far == 0.0 or far >= 50.0
		for s in mi.get_surface_override_material_count():
			var src := mi.mesh.surface_get_material(s) as BaseMaterial3D
			var k := _kind_of(src.resource_name) if src else ""
			if k == "":
				k = kind if kind != "" else "cloth"
			var m: Material
			if k == "hair":
				m = _make_hair(src, hero)
				if src and "scancards" in src.resource_name:
					# the import's automatic LODs tear alpha cards apart: always the full card set
					mi.lod_bias = 100.0
					_finish(m, mi.name, k)
				elif m and FINISH.get(mi.name.get_slice("_", 0), {}).has("hairgen"):
					# (FINISH "hairgen", per person: Ishita, Cristina) generated or MakeHuman card hair (hair.gdshader)
					_finish(m, mi.name, "hairgen")
			elif k == "hairunder" and src and src.albedo_texture:
				m = _make_hair_under(src)
				_finish(m, mi.name, k)
			elif k == "eye" and src and src.albedo_texture:
				m = _make_eye(src)
				_finish(m, mi.name, k)
			elif k == "glasses" and src and src.albedo_texture:
				m = _make_glasses(src, mi, s)
				_finish(m, mi.name, k)
			elif k == "hairshell" and src and src.albedo_texture and _hair_shell_on:
				m = _make_hair_shell(src, mi)
			else:
				m = _make(k, src, quality)
				if k == "lash" and m is StandardMaterial3D:
					# (FINISH "lash": alpha, per person; anyone not listed keeps the texture's own)
					var lf: Dictionary = FINISH.get(mi.name.get_slice("_", 0), {}).get("lash", {})
					if lf.has("alpha"):
						var lm := m as StandardMaterial3D
						lm.albedo_color.a *= float(lf["alpha"])
				if k == "brow" and m is StandardMaterial3D:
					# (FINISH "brow": tint, alpha; per person) the brow card's colour x tint and its alpha x alpha (over
					# 1 its soft edges fill in), for brows that otherwise thin out to a faint arc at the dialogue cameras
					var bf: Dictionary = FINISH.get(mi.name.get_slice("_", 0), {}).get("brow", {})
					if not bf.is_empty():
						var brm := m as StandardMaterial3D
						var bt: Color = bf.get("tint", Color(1, 1, 1))
						brm.albedo_color = Color(brm.albedo_color.r * bt.r, brm.albedo_color.g * bt.g,
								brm.albedo_color.b * bt.b, brm.albedo_color.a * float(bf.get("alpha", 1.0)))
				if k == "teeth" and m is StandardMaterial3D:
					# (FINISH "teeth": no_ambient, per person) the teeth lit by the direct lights only, no ambient (sky,
					# GI): under a blue sky the back teeth read slate-blue at the mouth's corners, even darkened and
					# warmed in the texture (face_finish molars) or with the ambient scaled by the texture's lightness
					var tf: Dictionary = FINISH.get(mi.name.get_slice("_", 0), {}).get("teeth", {})
					if tf.get("no_ambient", false):
						(m as StandardMaterial3D).disable_ambient_light = true
					# (FINISH "teeth": roughness, specular, tint; per person) for teeth that read silver-white with a
					# strong glint
					if tf.has("roughness") or tf.has("specular") or tf.has("tint"):
						var tm3 := m as StandardMaterial3D
						tm3.roughness = float(tf.get("roughness", tm3.roughness))
						if tf.has("specular"):
							tm3.set_meta("mouth_specular", float(tf["specular"]))
						if tf.has("tint"):
							var tb: Color = tm3.get_meta("mouth_base")
							var tt: Color = tf["tint"]
							tm3.set_meta("mouth_base", Color(tb.r * tt.r, tb.g * tt.g, tb.b * tt.b, tb.a))
						set_mouth_light(tm3, 0.0)
				if k == "skin" and has_glasses and m is StandardMaterial3D:
					# where the face is in front of hair (an ear), it is not hair: the glasses' arm pass skips it
					var sm := m as StandardMaterial3D
					sm.stencil_mode = BaseMaterial3D.STENCIL_MODE_CUSTOM
					sm.stencil_flags = BaseMaterial3D.STENCIL_FLAG_WRITE
					sm.stencil_compare = BaseMaterial3D.STENCIL_COMPARE_ALWAYS
					sm.stencil_reference = 0
			if _parts_debug and src and src.albedo_texture and k in ["haircap", "hairunder"]:
				m = _parts_debug_material(k, src)
			if m:
				mi.set_surface_override_material(s, m)
		if kind == "":
			kind = "skin"
		# hair cards shade the face and neck for the people you talk to; small parts never cast (glasses frames
		# come out of the shadow map as dark smears across the cheek)
		var casts := kind not in ["lash", "brow", "eye", "cornea", "teeth", "tongue", "haircap", "hair", "glasses"] or (kind == "hair" and hero)
		mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_ON if casts else GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
		if kind == "hairunder" and casts:
			# drawn single-sided (hair_under.gdshader), but a closed volume's shadow all the same
			mi.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_DOUBLE_SIDED


static func _kind_of(n: String) -> String:
	for t in n.split("_"):
		if t in KINDS:
			return t
	return ""


## Dev: "hairdebug=uv" on the command line draws the scan hair's cards unlit, red by UV.y (root 0 -> tip 1),
## green by the card's strip (UV.x), blue on back faces, alpha-tested on the atlas at full resolution;
## "hairdebug=alpha": red by UV.y, green by the filtered atlas alpha (as the game samples it), blue on back faces.
static var _hair_debug := "hairdebug=uv" in OS.get_cmdline_user_args() or "hairdebug=alpha" in OS.get_cmdline_user_args()
const _HAIR_DEBUG_CODE := """shader_type spatial;
render_mode unshaded, cull_disabled, depth_draw_opaque;
uniform sampler2D albedo_tex : filter_linear_mipmap_anisotropic;
uniform bool show_alpha = false;
void fragment() {
	float a = texture(albedo_tex, UV).a;
	ALBEDO = vec3(UV.y, show_alpha ? a : floor(UV.x * 8.0) / 8.0, FRONT_FACING ? 0.0 : 1.0);
	ALPHA = (show_alpha ? max(a, 0.02) : textureLod(albedo_tex, UV, 0.0).a) * smoothstep(0.0, 0.3, COLOR.a);
	ALPHA_SCISSOR_THRESHOLD = show_alpha ? 0.01 : 0.5;
}
"""


## Dev: "hairdebug=parts" draws the scan hair's scalp cap unlit magenta (its own alpha: texture x vertex alpha) and
## its underlayer unlit cyan, the cards as usual: what shows between and below the cards.
static var _parts_debug := "hairdebug=parts" in OS.get_cmdline_user_args()


static func _parts_debug_material(kind: String, src: BaseMaterial3D) -> Material:
	var m := ShaderMaterial.new()
	m.shader = Shader.new()
	if kind == "haircap":
		m.shader.code = """shader_type spatial;
render_mode unshaded, blend_mix, depth_draw_never, cull_back;
uniform sampler2D albedo_tex : filter_linear_mipmap;
void fragment() {
	ALBEDO = vec3(1.0, 0.0, 1.0);
	ALPHA = texture(albedo_tex, UV).a * COLOR.a;
}
"""
		m.render_priority = -1
	else:
		m.shader.code = """shader_type spatial;
render_mode unshaded, cull_back;
void fragment() {
	ALBEDO = vec3(0.0, 0.9, 0.9);
}
"""
	m.set_shader_parameter("albedo_tex", src.albedo_texture)
	return m


static func _make_hair(src: BaseMaterial3D, hero: bool) -> Material:
	if src == null or src.albedo_texture == null:
		return null
	var scan := "scancards" in src.resource_name
	if scan and _hair_debug:
		var dbg := ShaderMaterial.new()
		dbg.shader = Shader.new()
		dbg.shader.code = _HAIR_DEBUG_CODE
		dbg.set_shader_parameter("albedo_tex", src.albedo_texture)
		dbg.set_shader_parameter("show_alpha", "hairdebug=alpha" in OS.get_cmdline_user_args())
		return dbg
	var core := ShaderMaterial.new()
	core.shader = _hair_shader
	if scan:
		core.shader = _hair_scan_ear_shader if src.resource_name.ends_with("_scancards_ear") else _hair_scan_shader
	core.set_shader_parameter("albedo_tex", src.albedo_texture)
	core.set_shader_parameter("tint", src.albedo_color)
	if hero:
		var fringe := ShaderMaterial.new()
		fringe.shader = _hair_scan_fringe_shader if scan else _hair_fringe_shader
		fringe.set_shader_parameter("albedo_tex", src.albedo_texture)
		fringe.set_shader_parameter("tint", src.albedo_color)
		core.next_pass = fringe
	return core


static func _make_hair_under(src: BaseMaterial3D) -> Material:
	var m := ShaderMaterial.new()
	m.shader = _hair_under_shader
	m.set_shader_parameter("albedo_tex", src.albedo_texture)
	return m


static func _make_glasses(src: BaseMaterial3D, mi: MeshInstance3D, surface: int) -> Material:
	var m := ShaderMaterial.new()
	m.shader = _glasses_shader
	m.set_shader_parameter("albedo_tex", src.albedo_texture)
	m.set_shader_parameter("tint", src.albedo_color)
	m.set_shader_parameter("frame_metallic", src.metallic)
	# (its G: the temple arms' specular anti-aliasing)
	m.set_shader_parameter("arm_mask", _arm_mask(mi.mesh, surface))
	# before the scan hair's blended fringe (0) and scalp cap (-1): wisps in front of a lens blend over it
	m.render_priority = -2
	var arms := ShaderMaterial.new()
	arms.shader = _glasses_over_hair_shader
	arms.set_shader_parameter("albedo_tex", src.albedo_texture)
	arms.set_shader_parameter("tint", src.albedo_color)
	arms.set_shader_parameter("frame_metallic", src.metallic)
	arms.set_shader_parameter("arm_mask", _arm_mask(mi.mesh, surface))
	arms.render_priority = -2
	m.next_pass = arms
	var gf: Dictionary = FINISH.get(mi.name.get_slice("_", 0), {}).get("glasses", {})
	if float(gf.get("frame_grad", 0.0)) > 0.0:
		m.set_shader_parameter("grad_mask", _grad_mask(mi.mesh, surface))
	return m


## (a person's FINISH glasses frame_grad only) one texel per vertex (by VERTEX_ID), R: how far down the front of the
## frame (within 35 mm of its front in the rest pose, as _arm_mask's) the vertex is, 0 at its top to 1 at its bottom;
## 0 on the arms.
static func _grad_mask(mesh: Mesh, surface: int) -> Texture2D:
	var verts: PackedVector3Array = mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
	var z_cut := mesh.get_aabb().end.z - 0.035
	var y_top := -INF
	var y_bot := INF
	for v in verts:
		if v.z >= z_cut:
			y_top = maxf(y_top, v.y)
			y_bot = minf(y_bot, v.y)
	var w := 256
	var img := Image.create(w, maxi(1, ceili(verts.size() / float(w))), false, Image.FORMAT_R8)
	for i in verts.size():
		if verts[i].z >= z_cut and y_top > y_bot:
			img.set_pixel(i % w, i / w, Color((y_top - verts[i].y) / (y_top - y_bot), 0, 0))
	return ImageTexture.create_from_image(img)


## One texel per vertex of a glasses surface (read by VERTEX_ID). R (glasses_over_hair.gdshader): 1 on the temple
## arms in front of the ears, the vertices 35 mm or more behind the front of the frame in the rest pose (characters
## face +Z) and no further back than the arm's level stretch (within 4 mm of its highest point: past it the earpiece
## bends down behind the ear), 0 on the front frame, the lenses and the earpieces. Drawn behind the ear too, the
## earpiece shows through the hair over it from behind, a dotted bright line (the crown view). G (glasses.gdshader's
## specular anti-aliasing): 1 on the whole temple arm, earpiece included, 0 on the front frame and lenses.
static func _arm_mask(mesh: Mesh, surface: int) -> Texture2D:
	var key := "%d:%d" % [mesh.get_instance_id(), surface]
	if _arm_masks.has(key):
		return _arm_masks[key]
	var verts: PackedVector3Array = mesh.surface_get_arrays(surface)[Mesh.ARRAY_VERTEX]
	var z_cut := mesh.get_aabb().end.z - 0.035
	# per side: the end of the arm's level stretch (the deepest vertex within 4 mm of its top)
	var y_top := [-INF, -INF]
	for v in verts:
		if v.z < z_cut:
			var s := 0 if v.x < 0.0 else 1
			y_top[s] = maxf(y_top[s], v.y)
	var z_back := [INF, INF]
	for v in verts:
		if v.z < z_cut:
			var s := 0 if v.x < 0.0 else 1
			if v.y > y_top[s] - 0.004:
				z_back[s] = minf(z_back[s], v.z - 0.002)
	var w := 256
	var img := Image.create(w, maxi(1, ceili(verts.size() / float(w))), false, Image.FORMAT_RG8)
	for i in verts.size():
		var s := 0 if verts[i].x < 0.0 else 1
		if verts[i].z < z_cut:
			img.set_pixel(i % w, i / w, Color(1.0 if verts[i].z >= z_back[s] else 0.0, 1, 0))
	var tex := ImageTexture.create_from_image(img)
	_arm_masks[key] = tex
	return tex


static func _make_eye(src: BaseMaterial3D) -> Material:
	var m := ShaderMaterial.new()
	m.shader = _eye_shader
	m.set_shader_parameter("albedo_tex", src.albedo_texture)
	return m


## The person's FINISH for this kind of surface, on each pass of m that has the uniform (the glasses' arm pass has
## the frame's uniforms, not the lens').
static func _finish(m: Material, mesh_name: String, kind: String) -> void:
	var person: Dictionary = FINISH.get(mesh_name.get_slice("_", 0), {})
	var f: Dictionary = person.get(kind, {})
	var mat := m
	while not f.is_empty() and mat is ShaderMaterial:
		var sm := mat as ShaderMaterial
		var names := sm.shader.get_shader_uniform_list().map(func(u: Dictionary) -> String: return u.name)
		for p in f:
			if p in names:
				sm.set_shader_parameter(p, f[p])
		mat = mat.next_pass


static func _make_hair_shell(src: BaseMaterial3D, mi: MeshInstance3D) -> Material:
	var m := ShaderMaterial.new()
	m.shader = _hair_shell_shader
	m.set_shader_parameter("albedo_tex", src.albedo_texture)
	m.set_shader_parameter("tint", src.albedo_color)
	if src.normal_enabled and src.normal_texture:
		m.set_shader_parameter("normal_tex", src.normal_texture)
		m.set_shader_parameter("has_normal", true)
	# the crown: top centre of the shell, a little behind its middle (hair grows back from the forehead)
	var bb := mi.mesh.get_aabb()
	var c := bb.get_center()
	m.set_shader_parameter("crown", Vector3(c.x, bb.end.y - 0.02, c.z - 0.02))
	return m


static func _make(kind: String, src: BaseMaterial3D, quality: String) -> Material:
	if src == null:
		return null
	var m := StandardMaterial3D.new()
	m.albedo_texture = src.albedo_texture
	m.albedo_color = src.albedo_color
	m.normal_enabled = src.normal_enabled
	m.normal_texture = src.normal_texture
	m.texture_filter = BaseMaterial3D.TEXTURE_FILTER_LINEAR_WITH_MIPMAPS_ANISOTROPIC
	match kind:
		"skin":
			m.roughness = 0.55
			m.metallic_specular = 0.36
			m.subsurf_scatter_enabled = quality != "low"
			m.subsurf_scatter_strength = 0.32
			m.subsurf_scatter_skin_mode = true
			m.subsurf_scatter_transmittance_enabled = quality == "ultra"
			m.subsurf_scatter_transmittance_color = Color(0.9, 0.35, 0.25)
			m.subsurf_scatter_transmittance_depth = 0.08
			m.rim_enabled = true
			m.rim = 0.12
			m.rim_tint = 0.6
			# fine skin relief, mapped in model space: one UV atlas spans the whole body, so UV-mapped
			# pores would come out a centimetre wide
			m.detail_enabled = true
			m.detail_blend_mode = BaseMaterial3D.BLEND_MODE_MUL
			m.detail_normal = _pore_normal()
			m.detail_uv_layer = BaseMaterial3D.DETAIL_UV_2
			m.uv2_triplanar = true
			m.uv2_scale = Vector3(8, 8, 8)
		"eye":
			# sclera + iris; the wet look comes from the cornea shell on top
			m.roughness = 0.35
			m.metallic_specular = 0.3
			m.albedo_color = Color(0.92, 0.9, 0.88)
		"cornea":
			m.albedo_texture = null
			# premultiplied: black albedo adds nothing, only the specular highlight shows
			m.albedo_color = Color(0, 0, 0, 0.0)
			m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			m.blend_mode = BaseMaterial3D.BLEND_MODE_PREMULT_ALPHA
			m.roughness = 0.06
			# a mirror at full strength paints the bright windows over the iris (dark eyes read as pale blue)
			m.metallic_specular = 0.35
			m.cull_mode = BaseMaterial3D.CULL_BACK
			# behind a lens: drawn before glasses (-2) so a tinted lens tints it
			m.render_priority = -3
		"haircap":
			# generated hair (hair_gen.py): the root colour is in the vertex colours, no texture; scanned hair
			# (hair_scan_cards.py): a mask texture in the head's UVs (where the head's texture is hair, minus a
			# centre part's gap; its colour the person's dark roots) x the vertex alpha (where hair may grow)
			m.albedo_color = Color(1, 1, 1)
			m.vertex_color_use_as_albedo = true
			m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA   # soft hairline under the cards
			m.roughness = 0.75
			m.metallic_specular = 0.2
			if src.albedo_texture:
				# before the scan cards' blended fringe pass (render_priority 0), so their soft edges lie over it
				m.render_priority = -1
		"brow", "lash":
			# small and close to the skin: blended edges read as hair, dithering reads as grain
			m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
			m.roughness = 0.8
			m.metallic_specular = 0.3
			# behind a lens and under a fringe: before glasses (-2), the scalp cap (-1) and the hair's soft edges (0)
			m.render_priority = -3
		"glasses":
			m.metallic = src.metallic
			m.roughness = 0.22
			m.metallic_specular = 0.8
			if src.albedo_texture:
				m.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA_DEPTH_PRE_PASS
		"hairshell":
			# a scan's sculpted hair (scan_wrap.py): one solid shell, so a soft sheen instead of strand highlights
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
			m.roughness = 0.66
			m.metallic_specular = 0.25
			m.rim_enabled = true
			m.rim = 0.2
			m.rim_tint = 0.6
		"teeth":
			m.roughness = 0.28
			m.metallic_specular = 0.6
			_mouth_occlusion(m)
		"tongue":
			m.roughness = 0.35
			m.subsurf_scatter_enabled = true
			m.subsurf_scatter_strength = 0.4
			_mouth_occlusion(m)
		_:
			# fabric: soft sheen at grazing angles, very little specular; double-sided so hems and cuffs never show holes
			m.cull_mode = BaseMaterial3D.CULL_DISABLED
			m.roughness = 0.88
			if src.roughness_texture:
				# scanned clothes carry their own roughness (leather shoes vs mohair vs denim)
				m.roughness_texture = src.roughness_texture
				m.roughness_texture_channel = src.roughness_texture_channel
				m.roughness = 1.0
			m.metallic_specular = 0.25
			m.rim_enabled = true
			m.rim = 0.35
			m.rim_tint = 0.85
	return m


## Inside a closed mouth no light reaches the teeth: seen through the lips' resting gap they read as a dark line,
## not a white one. CharacterRig.set_mouth_light() brightens them as the jaw opens or a grin parts the lips.
static func _mouth_occlusion(m: StandardMaterial3D) -> void:
	m.set_meta("mouth_base", m.albedo_color)
	m.set_meta("mouth_specular", m.metallic_specular)
	set_mouth_light(m, 0.0)


static func set_mouth_light(m: StandardMaterial3D, light: float) -> void:
	var base: Color = m.get_meta("mouth_base")
	var f := lerpf(0.22, 0.92, clampf(light, 0.0, 1.0))
	m.albedo_color = Color(base.r * f, base.g * f, base.b * f, base.a)
	m.metallic_specular = float(m.get_meta("mouth_specular")) * lerpf(0.25, 1.0, clampf(light, 0.0, 1.0))


static func _pore_normal() -> Texture2D:
	if _pores:
		return _pores
	var noise := FastNoiseLite.new()
	noise.noise_type = FastNoiseLite.TYPE_CELLULAR
	noise.frequency = 0.35
	noise.cellular_return_type = FastNoiseLite.RETURN_DISTANCE
	var tex := NoiseTexture2D.new()
	tex.width = 512
	tex.height = 512
	tex.seamless = true
	tex.as_normal_map = true
	tex.bump_strength = 0.9
	tex.noise = noise
	_pores = tex
	return tex


static func _meshes(n: Node, out: Array[MeshInstance3D] = []) -> Array[MeshInstance3D]:
	if n is MeshInstance3D:
		out.append(n)
	for c in n.get_children():
		_meshes(c, out)
	return out
