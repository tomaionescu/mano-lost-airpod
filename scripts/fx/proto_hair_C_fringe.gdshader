shader_type spatial;
// PROTOTYPE C, pass 2 (next_pass of proto_hair_C.gdshader; not wired in yet): only the texels the alpha-tested
// pass dropped (strand tips, the ragged hairline, the sparse strands of the fuzz shells), alpha-blended over it
// with the depth test on and no depth write. Same maps and uniforms as pass 1.
render_mode blend_mix, cull_disabled, depth_draw_never, diffuse_burley;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic;
uniform sampler2D rough_tex : hint_default_white, filter_linear_mipmap_anisotropic;
uniform sampler2D mask_tex : hint_default_white, filter_linear_mipmap;
uniform sampler2D flow_tex : hint_default_white, filter_linear_mipmap;
uniform int layer : hint_range(0, 2) = 0;
uniform float alpha_threshold : hint_range(0.05, 0.95) = 0.5;
uniform float fringe_opacity : hint_range(0.0, 1.0) = 0.85;
uniform float normal_depth : hint_range(0.0, 2.0) = 0.45;
uniform float anisotropy : hint_range(0.0, 1.0) = 0.4;
uniform float rough_add : hint_range(-0.3, 0.3) = 0.12;
uniform float specular_amount : hint_range(0.0, 1.0) = 0.5;
uniform float backlight_amount : hint_range(0.0, 1.0) = 0.25;

void fragment() {
	vec4 m = texture(mask_tex, UV);
	float a = layer == 0 ? m.b : (layer == 1 ? m.r : m.g);
	vec3 alb = texture(albedo_tex, UV).rgb;
	ALBEDO = alb;
	ROUGHNESS = clamp(texture(rough_tex, UV).r + rough_add, 0.12, 1.0);
	SPECULAR = specular_amount * mix(0.35, 1.0, m.a);
	AO = m.a;
	AO_LIGHT_AFFECT = 0.35;
	NORMAL_MAP = texture(normal_tex, UV).rgb;
	NORMAL_MAP_DEPTH = normal_depth;
	vec2 f = texture(flow_tex, UV).rg * 2.0 - 1.0;
	ANISOTROPY = anisotropy;
	ANISOTROPY_FLOW = dot(f, f) > 1e-4 ? normalize(f) : vec2(1.0, 0.0);
	BACKLIGHT = alb * backlight_amount;
	ALPHA = a < alpha_threshold ? (a / alpha_threshold) * fringe_opacity : 0.0;
}
