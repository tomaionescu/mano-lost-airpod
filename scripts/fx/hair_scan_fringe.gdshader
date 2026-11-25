shader_type spatial;
// Strand cards over a scan's hair shell, pass 2 (next_pass of hair_scan.gdshader), as hair_fringe.gdshader is for
// the generated cards: only the wispy texels the core dropped, alpha-blended over it with the depth test on, times
// the card's root fade (COLOR.a). Same shading as the core (hair_scan.gdshaderinc). The scalp cap (kind "haircap")
// draws before it (lower render_priority), so these soft edges lie over the dark roots, not under them; so do
// glasses (render_priority -2, CharacterMaterials), so wisps in front of a lens are not painted over by it.
render_mode blend_mix, cull_disabled, depth_draw_never, diffuse_burley;

#include "res://scripts/fx/hair_common.gdshaderinc"
#include "res://scripts/fx/hair_scan.gdshaderinc"

uniform float fringe_opacity : hint_range(0.0, 1.0) = 0.9;

void fragment() {
	vec4 t = texture(albedo_tex, UV);
	NORMAL = scan_frontal(NORMAL, FRONT_FACING);
	v_back = FRONT_FACING ? 0.0 : 1.0;
	v_strand = scan_strand(VERTEX, NORMAL, UV, BINORMAL);
	v_spec = scan_glint(t, UV, COLOR, NORMAL, VIEW) * scan_glint_near(VERTEX);
	vec3 sc, hue;
	scan_spec_colors(UV, sc, hue);
	v_spec_col = sc;
	v_hue = hue;
	ALBEDO = scan_albedo(t.rgb, COLOR, UV);
	if (ambient_warm > 0.0 || ambient_gain != 1.0) {
		vec3 k;
		ALBEDO = scan_warm_albedo(ALBEDO, hue, k);
		v_alb_k = k;
	}
	float a =scan_coverage_alpha(t.a, UV, VERTEX) * scan_root_fade(COLOR.a, UV) * scan_edge_on(VERTEX, NORMAL, VIEW);
	ALPHA = a < core_threshold ? (a / core_threshold) * fringe_opacity : 0.0;
	// (lock_roll > 0 only) each lock lit as a rounded tube, as in the core pass
	NORMAL = scan_lock_normal(NORMAL, UV, VERTEX, TANGENT);
	ROUGHNESS = 0.6;
	SPECULAR = 0.0;
}

void light() {
	vec3 spec = vec3(0.0);
	vec3 d0 = DIFFUSE_LIGHT;
	scan_hair_light(v_strand, NORMAL, LIGHT, VIEW, v_spec_col, v_hue, LIGHT_COLOR, ATTENUATION, v_back,
			DIFFUSE_LIGHT, spec);
	if (ambient_warm > 0.0 || ambient_gain != 1.0) {
		DIFFUSE_LIGHT = d0 + (DIFFUSE_LIGHT - d0) * scan_direct_k(v_alb_k, ALBEDO, v_hue, LIGHT_COLOR);
	}
	SPECULAR_LIGHT += spec * v_spec;
}
