class_name Interiors
extends RefCounted
## Interior-mapped windows (docs/DESIGN.md V2-18). The level exports the windows of rooms nobody enters with an
## M_window_<kind> material; LevelBinder swaps each for the shared ShaderMaterial of its kind
## (res://scripts/fx/interior.gdshader) and lists it with the lit windows, so WorldEnv sets its
## `emission_energy` with the time of day like the room cards.

const SHADER := preload("res://scripts/fx/interior.gdshader")

## Shader parameters per kind; anything left out keeps the shader's default.
const KINDS := {
	# offices and classrooms: KB1's upper floors, Paritalie, the south buildings (frames are modelled)
	"office": {"kind": 0.0, "room_depth": 5.5, "floor_below": 0.9, "ceiling_above": 0.4, "side_margin": 0.9,
		"blinds_chance": 0.45, "cool_share": 0.65, "day_level": 0.2, "lit_scale": 1.0},
	# flats and student rooms behind modelled PVC frames (ARPEJ, 11 rue Pasteur, 29-31 rue Roger Salengro)
	"flat": {"kind": 1.0, "room_depth": 4.2, "floor_below": 0.95, "ceiling_above": 0.35, "side_margin": 0.7,
		"blinds_chance": 0.2, "curtains_chance": 0.55, "tv_chance": 0.25, "cool_share": 0.15, "day_level": 0.17,
		"lit_scale": 1.0, "wall_a": Color(0.88, 0.82, 0.72), "wall_b": Color(0.74, 0.8, 0.78),
		"floor_b": Color(0.55, 0.4, 0.27)},
	# the same on the backdrop's lean windows: the shader draws the white frame and the mullion
	"flat_lean": {"kind": 1.0, "room_depth": 4.2, "floor_below": 0.95, "ceiling_above": 0.35, "side_margin": 0.7,
		"blinds_chance": 0.2, "curtains_chance": 0.55, "tv_chance": 0.25, "cool_share": 0.15, "day_level": 0.17,
		"frame_width": 0.055, "frame_color": Color(0.9, 0.9, 0.87), "lit_scale": 1.0,
		"wall_a": Color(0.88, 0.82, 0.72), "wall_b": Color(0.74, 0.8, 0.78), "floor_b": Color(0.55, 0.4, 0.27)},
	# French windows that reach the floor (balconies of 13-17 rue Pasteur, ARPEJ)
	"flat_tall": {"kind": 1.0, "room_depth": 4.2, "floor_below": 0.06, "ceiling_above": 0.4, "side_margin": 0.7,
		"blinds_chance": 0.15, "curtains_chance": 0.6, "tv_chance": 0.25, "cool_share": 0.15, "day_level": 0.17,
		"lit_scale": 1.0, "wall_a": Color(0.9, 0.86, 0.78), "wall_b": Color(0.78, 0.8, 0.84)},
	# the hotels on rue Voltaire: sheer curtains drawn, warm lamps
	"hotel": {"kind": 2.0, "room_depth": 4.5, "floor_below": 0.9, "ceiling_above": 0.35, "side_margin": 0.6,
		"blinds_chance": 0.0, "curtains_chance": 0.8, "cool_share": 0.05, "day_level": 0.15,
		"frame_width": 0.06, "frame_color": Color(0.2, 0.21, 0.23), "curtain_color": Color(0.8, 0.74, 0.62),
		"lit_scale": 1.0},
}

static var _cache := {}


## The shared ShaderMaterial for a level material named "M_window_<kind>" (unknown kinds use "office").
static func material_for(material_name: String) -> ShaderMaterial:
	var kind := material_name.trim_prefix("M_window_")
	if not KINDS.has(kind):
		kind = "office"
	if _cache.has(kind):
		return _cache[kind]
	var m := ShaderMaterial.new()
	m.shader = SHADER
	m.resource_name = "M_window_" + kind
	var params: Dictionary = KINDS[kind]
	for k in params:
		m.set_shader_parameter(k, params[k])
	_cache[kind] = m
	return m
