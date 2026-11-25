shader_type spatial;
// Hair cards, pass 1: the dense core, alpha-tested. Opaque pipeline, so it writes depth, sorts correctly
// against itself and casts shadows onto the face and neck. hair_fringe.gdshader adds the soft edges.
render_mode cull_disabled, depth_draw_opaque, diffuse_burley;

#include "res://scripts/fx/hair_common.gdshaderinc"

uniform float core_threshold : hint_range(0.05, 0.95) = 0.5;
// (FINISH "hairgen" gen_ambient_gain, default 1 = off) the ambient light (sky, GI; what SSAO darkens) sees the
// albedo x this, each direct light's diffuse and colour highlight divided back: for dark braids that read
// near-black at night indoors, where the ambient carries most of the light
uniform float gen_ambient_gain : hint_range(0.25, 8.0) = 1.0;

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	v_strand = strand_dir(VERTEX, NORMAL, UV);
	ALBEDO = hair_albedo(t.rgb, COLOR, UV);
	if (gen_ambient_gain != 1.0) {
		ALBEDO *= gen_ambient_gain;
	}
	ALPHA = coverage_alpha(t.a, UV);
	ALPHA_SCISSOR_THRESHOLD = core_threshold;
	ROUGHNESS = 0.55;
	SPECULAR = 0.2;
}

void light() {
	if (gen_ambient_gain != 1.0) {
		vec3 dl = vec3(0.0);
		vec3 sl = vec3(0.0);
		hair_light(v_strand, NORMAL, LIGHT, VIEW, ALBEDO / gen_ambient_gain, LIGHT_COLOR, ATTENUATION, dl, sl);
		DIFFUSE_LIGHT += dl / gen_ambient_gain;
		SPECULAR_LIGHT += sl;
	} else {
		hair_light(v_strand, NORMAL, LIGHT, VIEW, ALBEDO, LIGHT_COLOR, ATTENUATION, DIFFUSE_LIGHT, SPECULAR_LIGHT);
	}
}
