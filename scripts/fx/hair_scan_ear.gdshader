shader_type spatial;
// Strand cards lying on or just over an ear (hair_scan_cards.py style key ear_stencil: the cards' faces over the
// ears are their own surface, material "<id>_hair_scancards_ear"). The same as hair_scan.gdshader except the
// stencil: it writes 0 ("not hair"), as the skin of a character with glasses does. glasses_over_hair.gdshader draws
// the temple arms again over hair that lies a few mm above them (a real arm presses the hair at the temple flat);
// over the ear the hair lies over the arm (hair_scan_cards.glasses_arms leaves it unpressed there), and that pass
// would draw the earpiece's highlight across the strands lying on the ear. Its shadow and fringe pass are the
// cards' own (next_pass hair_scan_fringe.gdshader, CharacterMaterials).
render_mode cull_disabled, depth_draw_opaque, diffuse_burley;
stencil_mode write, compare_always, 0;

#include "res://scripts/fx/hair_common.gdshaderinc"
#include "res://scripts/fx/hair_scan.gdshaderinc"

uniform vec2 shadow_cut_z = vec2(0.005, 0.025);

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
	ALPHA = scan_coverage_alpha(t.a, UV, VERTEX) * scan_root_fade(COLOR.a, UV) * scan_edge_on(VERTEX, NORMAL, VIEW);
	ALPHA_SCISSOR_THRESHOLD = core_threshold;
	if (IN_SHADOW_PASS) {
		ALPHA *= 1.0 - UV2.x * (1.0 - smoothstep(shadow_cut_z.x, shadow_cut_z.y, UV2.y - 0.5));
	}
	// (lock_roll > 0 only) each lock lit as a rounded tube, as in hair_scan.gdshader
	NORMAL = scan_lock_normal(NORMAL, UV, VERTEX, TANGENT);
	ROUGHNESS = 0.6;
	SPECULAR = 0.0;
}

void light() {
	vec3 spec = vec3(0.0);
	scan_hair_light(v_strand, NORMAL, LIGHT, VIEW, v_spec_col, v_hue, LIGHT_COLOR, ATTENUATION, v_back,
			DIFFUSE_LIGHT, spec);
	SPECULAR_LIGHT += spec * v_spec;
}
