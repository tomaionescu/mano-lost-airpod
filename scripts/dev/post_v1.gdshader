shader_type canvas_item;
// The v1 lens finish (vignette 0.32, grain new every frame, edge aberration), kept for A/B: autotest lens=v1.
uniform sampler2D screen : hint_screen_texture, filter_linear;
uniform float vignette = 0.32;
uniform float grain = 0.028;
uniform float aberration = 0.0012;
uniform float time_seed = 0.0;

float hash(vec2 p) {
	p = fract(p * vec2(443.897, 441.423));
	p += dot(p, p.yx + 19.19);
	return fract((p.x + p.y) * p.x);
}

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 c = uv - 0.5;
	float r2 = dot(c, c);
	vec2 off = c * r2 * aberration * 4.0;
	vec3 col;
	col.r = texture(screen, uv + off).r;
	col.g = texture(screen, uv).g;
	col.b = texture(screen, uv - off).b;
	float v = 1.0 - vignette * smoothstep(0.08, 0.62, r2 * 1.6);
	col *= v;
	float n = hash(uv * vec2(1920.0, 1080.0) + time_seed) - 0.5;
	float lum = dot(col, vec3(0.299, 0.587, 0.114));
	col += n * grain * (1.0 - lum * 0.6);
	COLOR = vec4(col, 1.0);
}
