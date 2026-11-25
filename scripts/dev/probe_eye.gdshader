shader_type spatial;
// dev probe copy of scripts/fx/eye.gdshader with its specular exposed (glass_probe.gd)
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 tint : source_color = vec4(0.92, 0.9, 0.88, 1.0);
uniform vec2 iris_a = vec2(0.293, 0.709);
uniform vec2 iris_b = vec2(0.709, 0.297);
uniform float iris_r = 0.116;
uniform float edge_shade : hint_range(0.0, 1.0) = 0.5;
uniform float lid_shade : hint_range(0.0, 1.0) = 0.3;
uniform float rough = 0.35;
uniform float spec = 0.3;
uniform float iris_spec = 0.3;
uniform int dbg = 0;

varying float up;

void vertex() {
	up = NORMAL.y;
}

void fragment() {
	vec3 c = texture(albedo_tex, UV).rgb * tint.rgb;
	float r = min(distance(UV, iris_a), distance(UV, iris_b));
	float edge = smoothstep(iris_r * 1.1, iris_r * 2.2, r);
	float lid = smoothstep(0.0, 0.5, up);
	float iris = 1.0 - smoothstep(iris_r * 0.95, iris_r * 1.1, r);
	ALBEDO = c * (1.0 - edge_shade * edge) * (1.0 - lid_shade * lid);
	if (dbg == 1) { ALBEDO = vec3(iris, 0.0, 0.0); }
	ROUGHNESS = rough;
	SPECULAR = mix(spec, iris_spec, iris);
}
