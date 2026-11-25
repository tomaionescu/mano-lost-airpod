shader_type spatial;
// PROTOTYPE C (not wired in; nothing uses this file yet). The scan's hair as one shell that reads as hair.
// Everything that makes it hair is baked offline (tools/blender/proto_hair_C.py + proto_hair_C_tex.py) from the
// scan and a per-person style, so this shader only samples the maps and hands over to Godot's own lighting:
// no hand-written specular, unlike hair_shell.gdshader, whose Kajiya-Kay lobes along a noise flow
// come out as white latex blotches. The highlight is Godot's anisotropic GGX, stretched across the baked strand
// flow (a fibre's band), and the custom normals of the mesh are already smoothed so the band follows the head.
//   albedo_tex  person's colour: darker roots and inner layers, per-strand value, clump AO (sRGB)
//   normal_tex  strand grooves along the flow (tangent space, OpenGL)
//   rough_tex   R: roughness (rougher in the cavities)
//   mask_tex    R, G: the strands of fuzz shells 1 and 2; B: the core's alpha (staggered tips, ragged hairline);
//               A: ambient occlusion
//   flow_tex    RG: the direction ACROSS the strands in tangent space (sign-free)
// Pass 1 (this file) is alpha-tested and opaque: it writes depth, sorts against itself and casts shadows.
// Pass 2 (proto_hair_C_fringe.gdshader, next_pass) blends the texels this pass dropped, for soft tips without
// the grain of dithering (the project runs without TAA or MSAA).
// layer: 0 = the core shell, 1 and 2 = the fuzz shells floating 1-4 mm above it (their own mesh surfaces).
render_mode cull_disabled, depth_draw_opaque, diffuse_burley;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic;
uniform sampler2D rough_tex : hint_default_white, filter_linear_mipmap_anisotropic;
uniform sampler2D mask_tex : hint_default_white, filter_linear_mipmap;
uniform sampler2D flow_tex : hint_default_white, filter_linear_mipmap;
uniform int layer : hint_range(0, 2) = 0;
uniform float alpha_threshold : hint_range(0.05, 0.95) = 0.5;
uniform float normal_depth : hint_range(0.0, 2.0) = 0.45;
uniform float anisotropy : hint_range(0.0, 1.0) = 0.4;
uniform float rough_add : hint_range(-0.3, 0.3) = 0.12;
uniform float specular_amount : hint_range(0.0, 1.0) = 0.5;
uniform float backlight_amount : hint_range(0.0, 1.0) = 0.25;

float layer_alpha(vec4 m) {
	return layer == 0 ? m.b : (layer == 1 ? m.r : m.g);
}

void fragment() {
	vec4 m = texture(mask_tex, UV);
	vec3 alb = texture(albedo_tex, UV).rgb;
	ALBEDO = alb;
	ROUGHNESS = clamp(texture(rough_tex, UV).r + rough_add, 0.12, 1.0);
	// specular occlusion: deep inside the clumps no highlight survives
	SPECULAR = specular_amount * mix(0.35, 1.0, m.a);
	AO = m.a;
	AO_LIGHT_AFFECT = 0.35;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	NORMAL_MAP_DEPTH = normal_depth;
	vec2 f = texture(flow_tex, UV).rg * 2.0 - 1.0;
	ANISOTROPY = anisotropy;
	ANISOTROPY_FLOW = dot(f, f) > 1e-4 ? normalize(f) : vec2(1.0, 0.0);
	// thin tips let some light through when the hair is backlit (TT); dark hair absorbs most of it
	BACKLIGHT = alb * backlight_amount;
	ALPHA = layer_alpha(m);
	ALPHA_SCISSOR_THRESHOLD = alpha_threshold;
}
