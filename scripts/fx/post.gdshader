shader_type canvas_item;
// Lens finish over the 3D view (docs/DESIGN.md §4.6), driven by post_layer.gd: film halation, a sun flare (soft glow
// and three warm ghosts, no streaks), the vignette, film grain that changes 24 times a second, and a very light
// chromatic aberration at the edges (keep it at or under 0.0012). The mipmaps of the screen copy are blurred,
// which is what the halation and the flare's sun test read.
uniform sampler2D screen : hint_screen_texture, filter_linear_mipmap;
uniform sampler2D grain_tex : filter_linear, repeat_enable;
uniform float vignette = 0.22;
uniform float grain = 0.025;
uniform vec2 grain_offset = vec2(0.0);
uniform float aberration = 0.0012;
uniform float halation = 0.05;
uniform vec3 halation_tint : source_color = vec3(1.0, 0.45, 0.25);
// where the sun is on screen, and how much flare it makes (0: none; post_layer.gd fades it in and out)
uniform vec2 sun_uv = vec2(0.5);
uniform float flare = 0.0;
uniform vec3 flare_tint : source_color = vec3(1.0, 0.78, 0.55);
// how bright the frame must be at the sun for the sun to count as seen (trees and people hide it too)
uniform float sun_seen_luma = 0.9;

float luma(vec3 c) {
	return dot(c, vec3(0.2126, 0.7152, 0.0722));
}

void fragment() {
	vec2 uv = SCREEN_UV;
	vec2 c = uv - 0.5;
	float r2 = dot(c, c);
	vec2 off = c * r2 * aberration * 4.0;
	vec3 col;
	col.r = textureLod(screen, uv + off, 0.0).r;
	col.g = textureLod(screen, uv, 0.0).g;
	col.b = textureLod(screen, uv - off, 0.0).b;
	// halation: the red-orange glow film makes around bright edges, spilling mostly into the darker side
	vec3 soft = textureLod(screen, uv, 3.0).rgb * 0.4 + textureLod(screen, uv, 5.0).rgb * 0.6;
	float hi = smoothstep(0.55, 0.92, luma(soft));
	float spill = clamp((luma(soft) - luma(col)) * 2.5 + 0.2, 0.0, 1.0);
	col += soft * halation_tint * hi * spill * halation;
	if (flare > 0.001) {
		vec2 asp = vec2(SCREEN_PIXEL_SIZE.y / SCREEN_PIXEL_SIZE.x, 1.0);   // distances in screen heights
		float seen = smoothstep(sun_seen_luma - 0.1, sun_seen_luma, luma(textureLod(screen, sun_uv, 2.0).rgb));
		float f = flare * seen;
		vec2 d = (uv - sun_uv) * asp;
		vec3 fl = flare_tint * exp(-dot(d, d) * 22.0) * 0.28;
		// ghosts on the line from the sun through the centre of the frame: soft-edged discs, as the aperture makes them
		for (int i = 0; i < 3; i++) {
			float k = float(i) * 0.55 + 0.6;
			float rad = i == 1 ? 0.085 : (i == 0 ? 0.045 : 0.03);
			vec2 g = sun_uv + (vec2(0.5) - sun_uv) * k;
			float dg = length((uv - g) * asp);
			float disc = 1.0 - smoothstep(rad * 0.7, rad, dg);
			fl += flare_tint * mix(vec3(1.0), vec3(1.0, 0.86, 0.7), float(i) * 0.5) * disc * 0.06;
		}
		col += fl * f;
	}
	col *= 1.0 - vignette * smoothstep(0.08, 0.62, r2 * 1.6);
	// grain: a tiling Gaussian grain at about 1.4 px, moved to a new place 24 times a second
	float n = (texture(grain_tex, FRAGCOORD.xy / (256.0 * 1.4) + grain_offset).r - 0.5) * 1.8;
	col += n * grain * (1.0 - luma(col) * 0.6);
	COLOR = vec4(col, 1.0);
}
