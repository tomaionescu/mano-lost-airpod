shader_type spatial;
// PROTOTYPE B (not wired into the game; see tools/blender/proto_hair_B.py): strand cards laid over a scan's hair
// shell, pass 1 (alpha-tested core). The same strand lighting as the generated cards (hair_common.gdshaderinc,
// strand direction from the UV gradient, two shifted Kajiya-Kay lobes), plus what the shingled cards need:
//  - COLOR.a fades a card in from its root: most cards start on top of other hair, and a hard root edge in the
//    middle of the hair reads as a stack of chips
//  - COLOR.rgb is the card's depth tone (inner layers darker), already multiplied in by hair_albedo()
//  - the highlights are broken up by the texel's own strand brightness and coverage (strand cores bright, the
//    gaps between strands dark): a band of glints, never a smooth sheet across the card (highlights that ignore
//    the strands come out as "wet latex" blotches, as in hair_shell.gdshader)
//  - the highlights are faded where the card is nearly edge-on to the view (the underlayer is what shows
//    there), so a card seen side-on never flashes a thin white line
// NORMAL is the hair volume's normal (the guide surface's smoothed normal, written as the cards' vertex
// normals at build time), so the diffuse term lights the cards as one mass of hair, not as separate flakes.
render_mode cull_disabled, depth_draw_opaque, diffuse_burley;

#include "res://scripts/fx/hair_common.gdshaderinc"

uniform float core_threshold : hint_range(0.05, 0.95) = 0.5;
uniform float edge_fade : hint_range(0.0, 1.0) = 0.25;
// straight hair ~1.3 (a coherent sheen band, lightly broken), curls ~2.2 (scattered small glints)
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
	ALPHA = coverage_alpha(t.a, UV) * COLOR.a;
	ALPHA_SCISSOR_THRESHOLD = core_threshold;
	ROUGHNESS = 0.55;
	SPECULAR = 0.2;
}

void light() {
	vec3 spec = vec3(0.0);
	hair_light(v_strand, NORMAL, LIGHT, VIEW, ALBEDO, LIGHT_COLOR, ATTENUATION, DIFFUSE_LIGHT, spec);
	SPECULAR_LIGHT += spec * v_facing * v_glint;
}
