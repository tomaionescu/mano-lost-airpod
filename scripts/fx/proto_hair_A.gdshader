shader_type spatial;
// PROTOTYPE A (not wired in: nothing uses this file yet). Scan-shaped hair cards, pass 1: hair.gdshader plus the
// card's layer, which proto_hair_A_grow.py writes into the vertex colour's alpha (0 = innermost card, next to the
// scalp; 1 = the outer surface of the scan's hair volume). Inner cards are shadowed by the outer ones in real hair:
// they keep only a fraction of the specular and get darker, so the many stacked layers don't add up to a grey sheen
// (the Blender proxy renders showed exactly that with a uniform specular). hair_gen cards have alpha 1, so they
// would render exactly as with hair.gdshader. hair_fringe.gdshader would need the same two lines for the soft pass.
// Untested in Godot: the prototype was only rendered in Blender (EEVEE).
render_mode cull_disabled, depth_draw_opaque, diffuse_burley;

#include "res://scripts/fx/hair_common.gdshaderinc"

uniform float core_threshold : hint_range(0.05, 0.95) = 0.5;
uniform float inner_spec : hint_range(0.0, 1.0) = 0.2;      // specular kept by the innermost layer
uniform float inner_dark : hint_range(0.0, 1.0) = 0.0;      // extra darkening (0: the grower already bakes depth AO into rgb)

varying float v_layer_spec;

void vertex() {
	float layer = COLOR.a;
	v_layer_spec = mix(inner_spec, 1.0, layer * layer);
}

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	v_strand = strand_dir(VERTEX, NORMAL, UV);
	vec4 c = COLOR;
	c.rgb *= mix(1.0 - inner_dark, 1.0, COLOR.a);
	ALBEDO = hair_albedo(t.rgb, c, UV);
	ALPHA = coverage_alpha(t.a, UV);
	ALPHA_SCISSOR_THRESHOLD = core_threshold;
	ROUGHNESS = 0.55;
	SPECULAR = 0.2;
}

void light() {
	vec3 dl = vec3(0.0);
	vec3 sl = vec3(0.0);
	hair_light(v_strand, NORMAL, LIGHT, VIEW, ALBEDO, LIGHT_COLOR, ATTENUATION, dl, sl);
	DIFFUSE_LIGHT += dl;
	SPECULAR_LIGHT += sl * v_layer_spec;
}
