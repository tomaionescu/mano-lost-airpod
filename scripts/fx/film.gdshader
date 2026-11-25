shader_type canvas_item;
// A print developed from Ishita's disposable camera (the credits, V2-27, docs/DESIGN.md §3.8): lower contrast and lifted
// blacks, warm highlights over cooler shadows, a light leak bleeding in from one edge, a soft vignette and grain
// that changes 24 times a second. 2D only: one texture read per pixel, no screen texture.

uniform float seed = 0.0;
uniform float leak : hint_range(0.0, 1.0) = 0.5;
uniform vec2 leak_from = vec2(1.0, 0.0);   // the UV corner or edge the leak comes from
uniform float grain : hint_range(0.0, 0.2) = 0.055;
uniform float lift : hint_range(0.0, 0.3) = 0.07;

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(12.9898, 78.233)) + seed * 17.13) * 43758.5453);
}

void fragment() {
	vec4 c = texture(TEXTURE, UV);
	vec3 col = c.rgb;
	float l = dot(col, vec3(0.299, 0.587, 0.114));
	col = mix(vec3(l), col, 0.86);
	col = col * (1.0 - lift) + lift;
	col *= mix(vec3(0.94, 0.98, 1.06), vec3(1.08, 1.0, 0.86), smoothstep(0.15, 0.9, l));
	float d = distance(UV, leak_from);
	vec3 leak_col = mix(vec3(1.0, 0.32, 0.08), vec3(1.0, 0.72, 0.32), smoothstep(0.0, 0.6, d));
	col += leak_col * leak * smoothstep(0.8, 0.0, d) * 0.6;
	vec2 v = UV - 0.5;
	col *= 1.0 - dot(v, v) * 0.85;
	float t = floor(TIME * 24.0);
	col += (hash(floor(UV * vec2(640.0, 420.0)) + t) - 0.5) * grain;
	COLOR = vec4(clamp(col, 0.0, 1.0), c.a * COLOR.a);
}
