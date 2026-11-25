shader_type spatial;
// One falling leaf (leaves.gdshader moves it): a two-sided cut-out from the 2x2 atlas assets/textures/fx/leaves_fall.png,
// the cell chosen by the particle (INSTANCE_CUSTOM.z). Thin enough to glow when the low sun is behind it.
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_lambert_wrap, specular_schlick_ggx;

uniform sampler2D atlas : source_color, filter_linear_mipmap, repeat_disable;
uniform float translucency = 0.8;

varying vec2 cell;

void vertex() {
	float c = floor(INSTANCE_CUSTOM.z + 0.5);
	cell = vec2(mod(c, 2.0), floor(c / 2.0)) * 0.5;
}

void fragment() {
	vec4 a = texture(atlas, cell + UV * 0.5);
	ALBEDO = a.rgb;
	ALPHA = a.a;
	ALPHA_SCISSOR_THRESHOLD = 0.5;
	ROUGHNESS = 0.75;
	SPECULAR = 0.35;
	BACKLIGHT = a.rgb * translucency;
}
