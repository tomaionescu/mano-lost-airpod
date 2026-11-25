shader_type spatial;
// dev probe copy of scripts/fx/glasses.gdshader (glass_probe.gd): dbg 1 = view-space normal as colour (unlit),
// dbg 2 = N.V (red) and grazing (green), dbg 3 = arm mask G
render_mode blend_premul_alpha, depth_prepass_alpha, cull_disabled, diffuse_burley;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 tint : source_color = vec4(1.0);
uniform float frame_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float frame_roughness : hint_range(0.0, 1.0) = 0.22;
uniform float frame_specular : hint_range(0.0, 1.0) = 0.8;
uniform float lens_roughness : hint_range(0.0, 1.0) = 0.06;
uniform float lens_specular : hint_range(0.0, 1.0) = 0.5;
uniform sampler2D arm_mask : filter_nearest, repeat_disable, hint_default_black;
uniform float arm_aa_roughness : hint_range(0.0, 1.0) = 0.45;
uniform float arm_aa_dim : hint_range(0.0, 1.0) = 0.6;
uniform int dbg = 0;
uniform float frame_ao = 1.0;

varying float v_temple;

void vertex() {
	ivec2 ms = textureSize(arm_mask, 0);
	v_temple = texelFetch(arm_mask, ivec2(VERTEX_ID % ms.x, VERTEX_ID / ms.x), 0).g;
}

void fragment() {
	vec4 t = texture(albedo_tex, UV) * tint;
	float lens = 1.0 - step(0.99, t.a);
	float a = mix(1.0, t.a * t.a, lens);
	ALBEDO = t.rgb * a;
	ALPHA = a;
	METALLIC = frame_metallic * (1.0 - lens);
	vec3 dn = fwidth(NORMAL);
	float aa = v_temple * smoothstep(0.15, 0.8, sqrt(dot(dn, dn)));
	ROUGHNESS = mix(mix(frame_roughness, max(frame_roughness, arm_aa_roughness), aa), lens_roughness, lens);
	SPECULAR = mix(frame_specular * (1.0 - arm_aa_dim * aa), lens_specular, lens);
	AO = mix(frame_ao, 1.0, lens);
	if (dbg == 1) {
		vec3 n = FRONT_FACING ? NORMAL : -NORMAL;
		ALBEDO = vec3(0.0); METALLIC = 0.0; SPECULAR = 0.0; ROUGHNESS = 1.0;
		EMISSION = (n * 0.5 + 0.5) * (1.0 - lens);
		ALPHA = mix(1.0, 0.0, lens);
	} else if (dbg == 2) {
		vec3 n = FRONT_FACING ? NORMAL : -NORMAL;
		float nv = clamp(dot(n, VIEW), 0.0, 1.0);
		ALBEDO = vec3(0.0); METALLIC = 0.0; SPECULAR = 0.0; ROUGHNESS = 1.0;
		EMISSION = vec3(nv, 1.0 - smoothstep(0.0, 0.3, nv), 0.0) * (1.0 - lens);
		ALPHA = mix(1.0, 0.0, lens);
	}
}
