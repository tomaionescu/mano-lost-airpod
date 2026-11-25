shader_type spatial;
// PROTOTYPE B (not wired into the game): pass 2 of proto_hair_B.gdshader, as hair_fringe.gdshader is for the
// generated cards: only the wispy texels the core dropped, alpha-blended with the depth test on, times the
// card's root fade (COLOR.a). Same broken-up highlights as the core.
render_mode blend_mix, cull_disabled, depth_draw_never, diffuse_burley;

#include "res://scripts/fx/hair_common.gdshaderinc"

uniform float core_threshold : hint_range(0.05, 0.95) = 0.5;
uniform float fringe_opacity : hint_range(0.0, 1.0) = 0.9;
uniform float edge_fade : hint_range(0.0, 1.0) = 0.25;
uniform float glint_pow : hint_range(0.5, 4.0) = 1.3;
uniform float glint_gain : hint_range(0.0, 4.0) = 1.6;

varying float v_facing;
varying float v_glint;

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	v_strand = strand_dir(VERTEX, NORMAL, UV);
	v_facing = smoothstep(0.0, edge_fade, abs(dot(NORMAL, VIEW)));
	float lum = dot(t.rgb, vec3(0.2126, 0.7152, 0.0722));
	v_glint = glint_gain * pow(lum, glint_pow) * pow(t.a, 1.5);
	ALBEDO = hair_albedo(t.rgb, COLOR, UV);
	float a = coverage_alpha(t.a, UV) * COLOR.a;
	ALPHA = a < core_threshold ? (a / core_threshold) * fringe_opacity : 0.0;
	ROUGHNESS = 0.55;
	SPECULAR = 0.2;
}

void light() {
	vec3 spec = vec3(0.0);
	hair_light(v_strand, NORMAL, LIGHT, VIEW, ALBEDO, LIGHT_COLOR, ATTENUATION, DIFFUSE_LIGHT, spec);
	SPECULAR_LIGHT += spec * v_facing * v_glint;
}
