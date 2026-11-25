shader_type canvas_item;
// Mano's notebook paper on any shape drawn with draw_polygon (the torn objective strip, sticky notes; docs/DESIGN.md
// §5.2, docs/ART_DIRECTION.md). The paper's colour is the vertex colour. Fibre and the Seyès ruling (violet lines every 8 mm,
// both ways, three blue interlines between them, the red margin) are measured in canvas units from the shape's
// own origin and anti-aliased over one screen pixel, so they stay sharp at any scale and on Retina.
// Per vertex, UV.x = ruling (0 or 1) and UV.y = fibre (0 or 1): a shadow passes its colour through, a torn fringe
// gets fibre only, the page gets both. `ruling` 1 is the 5 mm squares of Mano's algo pad (petits carreaux, the
// map sheet) instead of Seyès; PaperSheet (scripts/ui/paper_sheet.gd) sets these per page.

uniform float row = 40.0;          // violet line spacing (8 mm) in canvas units
uniform float first_line = 33.0;   // y of one violet line (the text sits on it)
uniform float margin_x = 24.0;     // the red margin; the vertical violet lines are counted from it
uniform float grain = 0.0;         // shifts the fibre so two pieces of paper differ
uniform int ruling = 0;            // 0 Seyès, 1 squares of `square` units (5 mm)
uniform float square = 25.0;       // the 5 mm square, in canvas units (5/8 of a Seyès row)
uniform bool margin = true;        // the red margin line
uniform vec4 violet : source_color = vec4(0.725, 0.686, 0.867, 1.0);
uniform vec4 blue : source_color = vec4(0.796, 0.847, 0.933, 1.0);
uniform vec4 grid : source_color = vec4(0.749, 0.804, 0.878, 1.0);
uniform vec4 margin_red : source_color = vec4(0.878, 0.376, 0.353, 1.0);

varying vec2 local;

void vertex() {
	local = VERTEX;
}

float hash(vec2 p) {
	return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453);
}

float vnoise(vec2 p) {
	vec2 i = floor(p);
	vec2 f = fract(p);
	f = f * f * (3.0 - 2.0 * f);
	return mix(mix(hash(i), hash(i + vec2(1.0, 0.0)), f.x), mix(hash(i + vec2(0.0, 1.0)), hash(i + vec2(1.0, 1.0)), f.x), f.y);
}

// coverage of lines `w` units wide every `period` units along v
float rule(float v, float period, float w) {
	float d = abs(fract(v / period + 0.5) - 0.5) * period;
	float fw = max(fwidth(v), 1e-4);
	return 1.0 - smoothstep(0.5 * w - 0.5 * fw, 0.5 * w + 0.5 * fw, d);
}

void fragment() {
	vec3 c = COLOR.rgb;
	vec2 p = local + vec2(grain * 37.0, grain * 11.0);
	float n = vnoise(p * 0.45) * 0.55 + vnoise(p * 0.08) * 0.45;   // fine fibre and a little cloudiness
	c *= mix(1.0, mix(0.958, 1.0, n), UV.y);
	if (UV.x > 0.5) {
		float ink = 0.72 + 0.28 * vnoise(p * 0.7);                  // the printing skips on the fibres
		float y = local.y - first_line;
		float x = local.x - margin_x;
		if (ruling == 1) {
			c = mix(c, grid.rgb, max(rule(y, square, 0.8), rule(x, square, 0.8)) * 0.75 * ink);
		} else {
			float main_y = rule(y, row, 1.0);
			float inter = rule(y, row * 0.25, 0.7) * (1.0 - main_y);
			c = mix(c, blue.rgb, inter * 0.8 * ink);
			c = mix(c, violet.rgb, max(main_y, rule(x, row, 0.9) * step(0.0, x)) * 0.85 * ink);
		}
		if (margin) {
			float fw = max(fwidth(local.x), 1e-4);
			c = mix(c, margin_red.rgb, (1.0 - smoothstep(0.6 - 0.5 * fw, 0.6 + 0.5 * fw, abs(x))) * 0.85 * ink);
		}
	}
	COLOR = vec4(c, COLOR.a);
}
