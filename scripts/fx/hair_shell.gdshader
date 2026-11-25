shader_type spatial;
// A scan's sculpted hair (tools/blender/scan_wrap.py): one solid shell with the scan's hair colour baked into
// smart-UV islands, so the UVs say nothing about which way the hair runs. Lit as plain fabric it read as one dark
// crumpled mass. Here every point gets a strand direction of its own: away from the crown and down, over the
// shell's surface, turned by a slow 3D noise for curls and waves. Kajiya-Kay highlights along it (as on the hair
// cards, hair_common.gdshaderinc) give the broken sheen of real hair; fine strand grooves come from the same noise.
render_mode cull_disabled, depth_draw_opaque, diffuse_burley;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap_anisotropic;
uniform bool has_normal = false;
uniform vec4 tint : source_color = vec4(1.0);
uniform vec3 crown = vec3(0.0, 1.75, -0.02);       // model space; set from the shell's bounds
uniform float curl : hint_range(0.0, 3.2) = 1.1;    // how far strands wander from the flow (radians)
uniform float curl_scale = 45.0;                    // waves per metre
uniform float groove : hint_range(0.0, 1.0) = 0.35; // strand grooves in the normal
uniform float groove_scale = 900.0;
uniform vec3 spec1_color : source_color = vec3(1.0, 0.95, 0.88);
uniform float spec1_strength : hint_range(0.0, 3.0) = 0.25;
uniform float spec1_exp : hint_range(4.0, 800.0) = 160.0;
uniform float spec1_shift : hint_range(-0.6, 0.6) = -0.08;
uniform float spec2_strength : hint_range(0.0, 3.0) = 0.4;
uniform float spec2_exp : hint_range(4.0, 400.0) = 40.0;
uniform float spec2_shift : hint_range(-0.6, 0.6) = 0.12;
uniform float wrap : hint_range(0.0, 1.0) = 0.4;
uniform float scatter_strength : hint_range(0.0, 3.0) = 0.35;

varying vec3 v_pos;
varying vec3 v_nrm;
varying vec3 v_strand;

vec3 hash3(vec3 p) {
	p = vec3(dot(p, vec3(127.1, 311.7, 74.7)), dot(p, vec3(269.5, 183.3, 246.1)), dot(p, vec3(113.5, 271.9, 124.6)));
	return fract(sin(p) * 43758.5453123) * 2.0 - 1.0;
}

float noise3(vec3 p) {
	vec3 i = floor(p);
	vec3 f = fract(p);
	vec3 u = f * f * (3.0 - 2.0 * f);
	return mix(mix(mix(dot(hash3(i), f), dot(hash3(i + vec3(1, 0, 0)), f - vec3(1, 0, 0)), u.x),
			mix(dot(hash3(i + vec3(0, 1, 0)), f - vec3(0, 1, 0)), dot(hash3(i + vec3(1, 1, 0)), f - vec3(1, 1, 0)), u.x), u.y),
		mix(mix(dot(hash3(i + vec3(0, 0, 1)), f - vec3(0, 0, 1)), dot(hash3(i + vec3(1, 0, 1)), f - vec3(1, 0, 1)), u.x),
			mix(dot(hash3(i + vec3(0, 1, 1)), f - vec3(0, 1, 1)), dot(hash3(i + vec3(1, 1, 1)), f - vec3(1, 1, 1)), u.x), u.y), u.z);
}

void vertex() {
	v_pos = VERTEX;
	v_nrm = NORMAL;
}

void fragment() {
	vec3 n = normalize(v_nrm);
	// the flow: out from the crown and down, laid onto the surface
	vec3 flow = normalize(v_pos - crown) + vec3(0.0, -0.7, 0.0);
	vec3 t = flow - n * dot(flow, n);
	if (dot(t, t) < 1e-8) {
		t = cross(n, vec3(1.0, 0.0, 0.0));
	}
	t = normalize(t);
	// curls: turn the strand about the normal by a slowly varying angle
	float a = noise3(v_pos * curl_scale) * 2.0 * curl;
	vec3 b = cross(n, t);
	t = normalize(t * cos(a) + b * sin(a));
	b = cross(n, t);
	// grooves across the strands: a ridged noise stretched along them
	float along = dot(v_pos, t);
	float across = dot(v_pos, b);
	// faded out once a groove is under a couple of pixels wide (procedural detail has no mipmaps: it would shimmer)
	float aa = clamp(1.5 - fwidth(across * groove_scale) * 1.5, 0.0, 1.0);
	float g = noise3(vec3(across * groove_scale, along * groove_scale * 0.08, 0.0)) * aa;
	vec4 tex = texture(albedo_tex, UV);
	ALBEDO = tex.rgb * tint.rgb * (1.0 - 0.18 * groove * (g * 0.5 + 0.5));
	ROUGHNESS = 0.6;
	SPECULAR = 0.2;
	mat3 to_view = mat3(VIEW_MATRIX) * mat3(MODEL_MATRIX);
	vec3 bend = (b * g * groove * 0.35);
	if (has_normal) {
		NORMAL_MAP = texture(normal_tex, UV).rgb;
		NORMAL_MAP_DEPTH = 0.6;
	}
	NORMAL = normalize(NORMAL + to_view * bend);
	v_strand = normalize(to_view * t);
}

float kajiya(vec3 t, vec3 h, float e) {
	float th = dot(t, h);
	float s = sqrt(max(0.0, 1.0 - th * th));
	return smoothstep(-1.0, 0.0, th) * pow(s, e);
}

void light() {
	vec3 t = normalize(v_strand);
	float ndl = dot(NORMAL, LIGHT);
	float diff = clamp((ndl + wrap) / (1.0 + wrap), 0.0, 1.0);
	float back = pow(clamp(dot(-LIGHT, VIEW), 0.0, 1.0), 4.0) * scatter_strength;
	vec3 lc = LIGHT_COLOR * ATTENUATION / PI;
	DIFFUSE_LIGHT += lc * (diff + back);
	vec3 h = normalize(LIGHT + VIEW);
	float s1 = kajiya(normalize(t + NORMAL * spec1_shift), h, spec1_exp);
	float s2 = kajiya(normalize(t + NORMAL * spec2_shift), h, spec2_exp);
	float vis = smoothstep(-0.25, 0.35, ndl);
	SPECULAR_LIGHT += lc * vis * (spec1_color * s1 * spec1_strength + ALBEDO * s2 * spec2_strength * 2.0);
}
