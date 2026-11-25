// Shared by hair.gdshader (alpha-tested core) and hair_fringe.gdshader (soft blended edges).
// Strand shading after Kajiya-Kay / Scheuermann: two highlights shifted along the strand, wrapped diffuse,
// light scattering through backlit hair, darker roots. The strand direction comes from the UV gradient
// (UV.y runs root -> tip on every card), so no mesh tangents are needed and nothing flips across the head.

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic, repeat_disable;
uniform vec4 tint : source_color = vec4(1.0);
uniform float root_dark : hint_range(0.0, 1.0) = 0.5;
uniform float root_len : hint_range(0.01, 0.6) = 0.24;
uniform vec3 spec1_color : source_color = vec3(1.0, 0.96, 0.9);
uniform float spec1_strength : hint_range(0.0, 3.0) = 0.2;
uniform float spec1_exp : hint_range(4.0, 800.0) = 380.0;
uniform float spec1_shift : hint_range(-0.6, 0.6) = -0.07;
uniform float spec2_strength : hint_range(0.0, 3.0) = 0.32;
uniform float spec2_exp : hint_range(4.0, 400.0) = 70.0;
uniform float spec2_shift : hint_range(-0.6, 0.6) = 0.12;
uniform float wrap : hint_range(0.0, 1.0) = 0.35;
uniform float scatter_strength : hint_range(0.0, 3.0) = 0.5;
uniform float mip_alpha_boost : hint_range(0.0, 1.0) = 0.24;

varying vec3 v_strand;

vec3 strand_dir(vec3 p, vec3 n, vec2 uv) {
	vec3 dp1 = dFdx(p);
	vec3 dp2 = dFdy(p);
	vec2 duv1 = dFdx(uv);
	vec2 duv2 = dFdy(uv);
	vec3 dp2perp = cross(dp2, n);
	vec3 dp1perp = cross(n, dp1);
	vec3 b = dp2perp * duv1.y + dp1perp * duv2.y;
	float l2 = dot(b, b);
	return l2 > 1e-24 ? b * inversesqrt(l2) : vec3(0.0, -1.0, 0.0);
}

// alpha keeps its coverage as mip levels average strands away (distant hair would otherwise thin out)
float coverage_alpha(float a, vec2 uv) {
	vec2 ts = vec2(textureSize(albedo_tex, 0));
	vec2 dx = dFdx(uv * ts);
	vec2 dy = dFdy(uv * ts);
	float lod = 0.5 * log2(max(max(dot(dx, dx), dot(dy, dy)), 1e-8));
	return clamp(a * (1.0 + max(lod, 0.0) * mip_alpha_boost), 0.0, 1.0);
}

vec3 hair_albedo(vec3 tex, vec4 vcol, vec2 uv) {
	float root = mix(1.0 - root_dark, 1.0, smoothstep(0.0, root_len, uv.y));
	return tex * tint.rgb * vcol.rgb * root;
}

float kajiya(vec3 t, vec3 h, float e) {
	float th = dot(t, h);
	float s = sqrt(max(0.0, 1.0 - th * th));
	return smoothstep(-1.0, 0.0, th) * pow(s, e);
}

void hair_light(vec3 strand, vec3 n, vec3 l, vec3 v, vec3 albedo, vec3 light_color, float attenuation,
		inout vec3 diffuse_light, inout vec3 specular_light) {
	vec3 t = normalize(strand);
	float ndl = dot(n, l);
	float diff = clamp((ndl + wrap) / (1.0 + wrap), 0.0, 1.0);
	float back = pow(clamp(dot(-l, v), 0.0, 1.0), 4.0) * scatter_strength;
	vec3 lc = light_color * attenuation / PI;
	diffuse_light += lc * (diff + back);
	vec3 h = normalize(l + v);
	float s1 = kajiya(normalize(t + n * spec1_shift), h, spec1_exp);
	float s2 = kajiya(normalize(t + n * spec2_shift), h, spec2_exp);
	float vis = smoothstep(-0.25, 0.35, ndl);
	specular_light += lc * vis * (spec1_color * s1 * spec1_strength + albedo * s2 * spec2_strength * 2.0);
}
