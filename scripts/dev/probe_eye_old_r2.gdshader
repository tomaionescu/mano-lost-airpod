shader_type spatial;
// dev copy of scripts/fx/eye.gdshader without the per-person iris uniforms, for an A/B in glass_probe (sh:eye=)
// MakeHuman eyeball (sclera + iris; the wet look is the cornea shell on top, see character_materials.gd).
// Its texture is evenly white right out to the lids, so eyes read wide and staring. Real sclera falls off into
// the shadow of the lids and lashes: darker away from the iris, and darker under the upper lid.
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 tint : source_color = vec4(0.92, 0.9, 0.88, 1.0);
// MakeHuman's eye UV layout: both eyes on one texture, iris centres and radius in UV
uniform vec2 iris_a = vec2(0.293, 0.709);
uniform vec2 iris_b = vec2(0.709, 0.297);
uniform float iris_r = 0.116;
uniform float edge_shade : hint_range(0.0, 1.0) = 0.5;
uniform float lid_shade : hint_range(0.0, 1.0) = 0.3;
// the iris' own specular (pupil included). The iris lies under the cornea and has no sheen of its own: the eyeball's
// broad roughness-0.35 lobe laid the fill light (the sky, in the game) over a dark iris, so brown eyes read blue at
// three-quarters and a whitish smear sat beside the pupil. 0 leaves the cornea shell's sharp highlights alone on it.
// Per person (CharacterMaterials.FINISH); the default 0.3 is the sclera's, as before.
uniform float iris_specular : hint_range(0.0, 1.0) = 0.3;

varying float up;

void vertex() {
	up = NORMAL.y;   // model space: the top of the eyeball sits under the upper lid
}

void fragment() {
	vec3 c = texture(albedo_tex, UV).rgb * tint.rgb;
	float r = min(distance(UV, iris_a), distance(UV, iris_b));
	float edge = smoothstep(iris_r * 1.1, iris_r * 2.2, r);
	float lid = smoothstep(0.0, 0.5, up);
	ALBEDO = c * (1.0 - edge_shade * edge) * (1.0 - lid_shade * lid);
	ROUGHNESS = 0.35;
	float iris = 1.0 - smoothstep(iris_r * 0.95, iris_r * 1.1, r);
	SPECULAR = 0.3 + (iris_specular - 0.3) * iris;   // exactly 0.3 at the default
}
