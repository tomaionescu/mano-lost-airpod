shader_type spatial;
// Leaf cards and grass that move in the breeze (docs/DESIGN.md §4.8: 2-4 cm at 0.6-1.2 Hz, phase from the world position).
// LevelBinder swaps it in for the imported foliage materials at load time and copies their textures, so the
// shading matches the StandardMaterial3D it replaces (alpha scissor, two-sided, vertex colour). The sway runs
// in the shadow pass too, so the dappled shadows move with the leaves.
render_mode blend_mix, depth_draw_opaque, cull_disabled, diffuse_burley, specular_schlick_ggx;

uniform vec4 albedo : source_color = vec4(1.0);
uniform sampler2D albedo_tex : source_color, filter_linear_mipmap, repeat_enable;
uniform bool vertex_color = true;   // the imported material's vertex_color_use_as_albedo
uniform bool use_normal_map = false;
uniform sampler2D normal_tex : hint_normal, filter_linear_mipmap, repeat_enable;
uniform float normal_scale = 1.0;
// ARM: ambient occlusion (r), roughness (g), metallic (b), as the Poly Haven / ambientCG maps pack them
uniform bool use_arm_map = false;
uniform sampler2D arm_tex : hint_default_white, filter_linear_mipmap, repeat_enable;
uniform float roughness = 0.7;
uniform float metallic = 0.0;
uniform float specular = 0.5;
uniform float alpha_scissor = 0.5;
uniform vec3 uv1_scale = vec3(1.0);
uniform vec3 uv1_offset = vec3(0.0);
// sway: metres of travel, cycles per second, horizontal wind direction (world x, z)
uniform float sway_amp = 0.03;
uniform float sway_hz = 0.9;
uniform vec2 wind_dir = vec2(0.85, -0.52);   // a south-westerly breeze, blowing toward the north-east
// 0: a leaf card in a crown moves whole, more the higher it sits above sway_base (object space: the foot of a
// plant prop, or the bottom of a level mesh full of bushes); 1: a grass card bends from its root (UV.y = 1 at the
// root, 0 at the tips)
uniform int anchor = 0;
uniform float sway_base = 0.0;

void vertex() {
	vec2 uv0 = UV;
	UV = UV * uv1_scale.xy + uv1_offset.xy;
	vec3 wp = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float w = anchor == 1 ? clamp(1.0 - uv0.y, 0.0, 1.0) : smoothstep(0.2, 2.5, VERTEX.y - sway_base);
	// neighbouring clusters move together, a crown sways as a wave, and a slow gust swells it now and then
	float ph = dot(wp, vec3(0.37, 0.21, 0.29));
	float t = TIME * sway_hz * 6.2831853;
	float gust = 0.65 + 0.35 * sin(TIME * 0.21 + wp.x * 0.045 + wp.z * 0.03);
	float along = sin(t + ph) * 0.75 + sin(t * 1.73 + ph * 1.9) * 0.25;
	float flutter = sin(t * 2.9 + ph * 4.1);
	vec3 wdir = vec3(wind_dir.x, 0.0, wind_dir.y);
	vec3 d = (wdir * along + vec3(-wind_dir.y, 0.5, wind_dir.x) * flutter * 0.3) * sway_amp * gust * w;
	VERTEX += inverse(mat3(MODEL_MATRIX)) * d;
}

void fragment() {
	vec4 a = texture(albedo_tex, UV) * albedo * (vertex_color ? COLOR : vec4(1.0));
	ALBEDO = a.rgb;
	ALPHA = a.a;
	ALPHA_SCISSOR_THRESHOLD = alpha_scissor;
	float rough = roughness;
	float metal = metallic;
	if (use_arm_map) {
		vec3 arm = texture(arm_tex, UV).rgb;
		AO = arm.r;
		AO_LIGHT_AFFECT = 0.0;
		rough = arm.g * roughness;
		metal = arm.b * metallic;
	}
	ROUGHNESS = rough;
	METALLIC = metal;
	SPECULAR = specular;
	if (use_normal_map) {
		NORMAL_MAP = texture(normal_tex, UV).rgb;
		NORMAL_MAP_DEPTH = normal_scale;
	}
}
