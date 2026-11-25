shader_type spatial;
// dev probe copy of scripts/fx/eye.gdshader with the in-engine iris recolour under test (glass_probe.gd sh:eye=)
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 tint : source_color = vec4(0.92, 0.9, 0.88, 1.0);
uniform vec2 iris_a = vec2(0.293, 0.709);
uniform vec2 iris_b = vec2(0.709, 0.297);
uniform float iris_r = 0.116;
uniform float edge_shade : hint_range(0.0, 1.0) = 0.5;
uniform float lid_shade : hint_range(0.0, 1.0) = 0.3;
uniform float iris_specular : hint_range(0.0, 1.0) = 0.3;
uniform float iris_recolor : hint_range(0.0, 1.0) = 0.0;
uniform vec4 iris_color : source_color = vec4(0.25, 0.2, 0.15, 1.0);
uniform vec4 iris_inner_color : source_color = vec4(0.25, 0.2, 0.15, 1.0);
uniform float iris_inner_r : hint_range(0.0, 1.0) = 0.0;
uniform int dbg = 0;

varying float up;

void vertex() {
	up = NORMAL.y;
}

void fragment() {
	vec3 t = texture(albedo_tex, UV).rgb;
	vec3 c = t * tint.rgb;
	float r = min(distance(UV, iris_a), distance(UV, iris_b));
	if (iris_recolor > 0.0) {
		vec2 ctr = distance(UV, iris_a) < distance(UV, iris_b) ? iris_a : iris_b;
		vec3 lw = vec3(0.2126, 0.7152, 0.0722);
		float lod = log2(float(textureSize(albedo_tex, 0).x) / 64.0);
		float ref = 0.0;
		for (int i = 0; i < 8; i++) {
			float a = float(i) * 0.7853982;
			ref += dot(textureLod(albedo_tex, ctr + iris_r * 0.6 * vec2(cos(a), sin(a)), lod).rgb, lw);
		}
		float k = dot(t, lw) / max(ref / 8.0, 1e-4);
		float rn = r / iris_r;
		float inner = 0.0;
		if (iris_inner_r > 0.0) {
			inner = 1.0 - smoothstep(iris_inner_r - 0.1, iris_inner_r + 0.1, rn + 0.08 * (k - 1.0));
		}
		vec3 ic = mix(iris_color.rgb, iris_inner_color.rgb, inner) * min(k, 2.0);
		c = mix(c, ic, iris_recolor * (1.0 - smoothstep(0.9, 1.0, rn)));
	}
	float edge = smoothstep(iris_r * 1.1, iris_r * 2.2, r);
	float lid = smoothstep(0.0, 0.5, up);
	ALBEDO = c * (1.0 - edge_shade * edge) * (1.0 - lid_shade * lid);
	if (dbg == 1) { ALBEDO = vec3(1.0 - smoothstep(iris_r * 0.95, iris_r * 1.1, r), 0.0, 0.0); }
	ROUGHNESS = 0.35;
	float iris = 1.0 - smoothstep(iris_r * 0.95, iris_r * 1.1, r);
	SPECULAR = 0.3 + (iris_specular - 0.3) * iris;
}
