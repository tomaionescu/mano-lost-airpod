shader_type spatial;
// Hair cards, pass 2 (next_pass of hair.gdshader): only the wispy texels the core pass dropped, alpha-blended
// over it with the depth test on. Gives soft strand edges without the grain of dithered transparency.
render_mode blend_mix, cull_disabled, depth_draw_never, diffuse_burley;

#include "res://scripts/fx/hair_common.gdshaderinc"

uniform float core_threshold : hint_range(0.05, 0.95) = 0.5;
uniform float fringe_opacity : hint_range(0.0, 1.0) = 0.9;
// (FINISH "hairgen" gen_ambient_gain, default 1 = off: Cristina; as in hair.gdshader)
uniform float gen_ambient_gain : hint_range(0.25, 8.0) = 1.0;

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	v_strand = strand_dir(VERTEX, NORMAL, UV);
	ALBEDO = hair_albedo(t.rgb, COLOR, UV);
	if (gen_ambient_gain != 1.0) {
		ALBEDO *= gen_ambient_gain;
	}
	float a = coverage_alpha(t.a, UV);
	ALPHA = a < core_threshold ? (a / core_threshold) * fringe_opacity : 0.0;
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
