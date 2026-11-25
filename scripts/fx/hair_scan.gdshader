shader_type spatial;
// Strand cards over a scan's hair shell (tools/blender/hair_scan_cards.py), pass 1: the dense core, alpha-tested.
// Opaque pipeline, so it writes depth, sorts against itself and casts shadows onto the face and neck;
// hair_scan_fringe.gdshader (next_pass) adds the soft edges. Strand lighting (hair_scan.gdshaderinc): wrapped
// diffuse and backlight scatter on the hair volume's normal (never flipped on a card's back face), two broad
// Kajiya-Kay lobes along the mesh tangents in the hair's own colour, broken up per strand.
// Writes stencil 2 ("hair here"): glasses.gdshader's second pass draws the temple arms over hair that lies a
// few mm above them (a real arm presses the hair flat; the cards are grown a few mm out from the frames).
// Hair hanging in front of the face (a fringe's ends over the brows and lenses: UV2 from hair_scan_cards.shadow_cut,
// below shadow_cut_z over the brows) stays out of the shadow map: it lies a few mm to 2 cm off the skin, and the shadow
// bias hides its shadow everywhere except where the face falls far away behind it (the eye's inner corner beside
// the nose), where two lock tips' shadows show as an isolated purple-brown blob under the eye.
render_mode cull_disabled, depth_draw_opaque, diffuse_burley;
stencil_mode write, compare_always, 2;

#include "res://scripts/fx/hair_common.gdshaderinc"
#include "res://scripts/fx/hair_scan.gdshaderinc"

// the height over the brows (metres) below which hair in front of the face stays out of the shadow map (fading)
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
	if (ambient_warm > 0.0 || ambient_gain != 1.0) {
		vec3 k;
		ALBEDO = scan_warm_albedo(ALBEDO, hue, k);
		v_alb_k = k;
	}
	ALPHA = scan_coverage_alpha(t.a, UV, VERTEX) * scan_root_fade(COLOR.a, UV) * scan_edge_on(VERTEX, NORMAL, VIEW);
	ALPHA_SCISSOR_THRESHOLD = core_threshold;
	if (IN_SHADOW_PASS) {
		// hair in front of the face (UV2.x, 0 on meshes without UV2) below shadow_cut_z over the brows (UV2.y - 0.5)
		ALPHA *= 1.0 - UV2.x * (1.0 - smoothstep(shadow_cut_z.x, shadow_cut_z.y, UV2.y - 0.5));
	}
	// (lock_roll > 0 only, after the alpha and the highlight's weight) each lock lit as a rounded tube
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
