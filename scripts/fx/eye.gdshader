shader_type spatial;
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
// Per person (CharacterMaterials.FINISH); the default 0.3 is the sclera's.
uniform float iris_specular : hint_range(0.0, 1.0) = 0.3;
// The iris recoloured in the engine, per person (CharacterMaterials.FINISH). The build gives the iris the cast's
// eye_color (build_human.recolor_iris), which can render off under a warm key: grey-green irises come out amber
// and near-black ones light copper. 0 (the default) keeps the built iris exactly.
//  - iris_color: the iris' albedo at its mean brightness (sRGB, like tint). Each texel keeps the texture's light
//    and dark (fibres, the dark limbal ring, the black pupil) as its luminance over the texture's own mean over a
//    ring round the pupil (a coarse mip), so only the hue and the overall brightness change.
//  - iris_inner_color out to iris_inner_r of the iris' radius: a collar of another colour round the pupil
//    (brown in a grey-green iris, say); its edge follows the fibres. iris_inner_r 0: none.
uniform float iris_recolor : hint_range(0.0, 1.0) = 0.0;
uniform vec4 iris_color : source_color = vec4(0.25, 0.2, 0.15, 1.0);
uniform vec4 iris_inner_color : source_color = vec4(0.25, 0.2, 0.15, 1.0);
uniform float iris_inner_r : hint_range(0.0, 1.0) = 0.0;

varying float up;

void vertex() {
	up = NORMAL.y;   // model space: the top of the eyeball sits under the upper lid
}

void fragment() {
	vec3 c = texture(albedo_tex, UV).rgb * tint.rgb;
	float r = min(distance(UV, iris_a), distance(UV, iris_b));
	if (iris_recolor > 0.0) {
		vec2 ctr = distance(UV, iris_a) < distance(UV, iris_b) ? iris_a : iris_b;
		vec3 lw = vec3(0.2126, 0.7152, 0.0722);
		float lod = log2(float(textureSize(albedo_tex, 0).x) / 64.0);   // texels ~1/64 of the texture: no fibres
		float ref = 0.0;
		for (int i = 0; i < 8; i++) {
			float a = float(i) * 0.7853982;
			ref += dot(textureLod(albedo_tex, ctr + iris_r * 0.6 * vec2(cos(a), sin(a)), lod).rgb, lw);
		}
		float k = dot(texture(albedo_tex, UV).rgb, lw) / max(ref / 8.0, 1e-4);
		float rn = r / iris_r;
		float inner = 0.0;
		if (iris_inner_r > 0.0) {
			inner = 1.0 - smoothstep(iris_inner_r - 0.1, iris_inner_r + 0.1, rn + 0.08 * (k - 1.0));
		}
		vec3 ic = mix(iris_color.rgb, iris_inner_color.rgb, inner) * min(k, 2.0);
		// full to 0.9 of the radius, none from its edge out (the texture's iris ends at 0.97)
		c = mix(c, ic, iris_recolor * (1.0 - smoothstep(0.9, 1.0, rn)));
	}
	float edge = smoothstep(iris_r * 1.1, iris_r * 2.2, r);
	float lid = smoothstep(0.0, 0.5, up);
	ALBEDO = c * (1.0 - edge_shade * edge) * (1.0 - lid_shade * lid);
	ROUGHNESS = 0.35;
	float iris = 1.0 - smoothstep(iris_r * 0.95, iris_r * 1.1, r);
	SPECULAR = 0.3 + (iris_specular - 0.3) * iris;   // exactly 0.3 at the default
}
