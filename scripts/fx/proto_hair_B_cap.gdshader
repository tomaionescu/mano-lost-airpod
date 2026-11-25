shader_type spatial;
// PROTOTYPE B (not wired into the game): the scalp cap, a copy of the head's hair-covered triangles 1 mm above
// the skin, with the head's UVs. It turns the scan's grey hairline band and the bald, hair-painted dome under
// the shell into dark roots fading into the skin, without touching the face texture.
//  - mask_tex.a: where the head's baked texture is hair, not skin (Lab distance from the forehead skin colour),
//    already multiplied at build time by the region weight (no brows, no beard, the nape cut for short hair)
//    and by the open part line (a 3 mm line of scalp left visible along a centre part)
//  - COLOR.r: the region weight again, per vertex (lets the build fade the cap without rebaking the mask)
// Drawn before the cards' blended fringe pass (render_priority below the fringe material's).
render_mode blend_mix, cull_back, depth_draw_never, diffuse_burley, specular_schlick_ggx;

uniform sampler2D mask_tex : hint_default_black, filter_linear_mipmap;
uniform vec4 root_color : source_color = vec4(0.03, 0.022, 0.018, 1.0);
uniform float lift : hint_range(0.5, 4.0) = 2.2;
uniform float edge_lo : hint_range(0.0, 1.0) = 0.4;
uniform float edge_hi : hint_range(0.0, 1.0) = 0.8;

void fragment() {
	float m = smoothstep(edge_lo, edge_hi, texture(mask_tex, UV).a);
	ALBEDO = root_color.rgb * lift;
	ALPHA = m * COLOR.r;
	ROUGHNESS = 0.9;
	SPECULAR = 0.12;
}
