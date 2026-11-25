shader_type spatial;
// Glasses (kind "glasses": MakeHuman frames; Mano's also have lenses, the texels with alpha < 1 in the same
// texture). CharacterMaterials draws them at render_priority -2: before the scan hair's blended fringe pass and
// scalp cap, so wisps of a fringe in front of a lens or frame blend over it instead of being painted over.
//  - frames: opaque (alpha 1, written to depth by the depth prepass)
//  - lenses (alpha < 1): glass, premultiplied: their own reflection (F0 0.04) added in full, their tint film at
//    alpha squared. Mano's lenses are a 20 % grey film in the texture: drawn as such it lifted the dark fringe
//    behind it to the skin's tone, so the fringe looked cut along the lens outline; at 4 % they read as clear
//    glass. A tinted lens (the leopard glasses' gradient, alpha up to 1) keeps most of its tint.
// next_pass (glasses_over_hair.gdshader) draws the temple arms again over the hair that grows a few mm over them.
//  - the temple arms only (arm_mask's G, one texel per vertex by VERTEX_ID, CharacterMaterials): a pixel or two wide
//    from behind, their sharp highlight broke into a dotted line along them. Where the normal turns a lot within a
//    pixel they get rougher and, so the spread highlight does not light the whole arm, less specular (geometric
//    specular anti-aliasing). Not on the front frame: at full-body distance every rim is that thin, and black frames
//    rough and as specular lit up grey-blue under the fill light (Joaquin's)
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
// per person (CharacterMaterials.FINISH; the defaults leave the texture as it is): lens_tint scales a lens' tint film
// (its alpha before squaring), frame_flat evens the frame's texture toward frame_color. Together they turn a
// patterned sunglasses asset (a leopard print, dark-to-clear gradient lenses that read as a milky film over the
// eyes) into plain frames with clear lenses.
uniform float lens_tint : hint_range(0.0, 1.0) = 1.0;
uniform float frame_flat : hint_range(0.0, 1.0) = 0.0;
uniform vec4 frame_color : source_color = vec4(0.5, 0.5, 0.5, 1.0);
// per person (FINISH; frame_grad 0, the default, leaves the frame as above): a two-tone acetate frame, frame_top's
// colour at the top of the front fading to frame_bottom at frame_bottom_alpha (clear plastic) at its bottom, over
// grad_range of the front's height (grad_mask's R, one texel per vertex by VERTEX_ID: 0 at the front's top, 1 at its
// bottom, 0 on the arms; CharacterMaterials). Silvia's frames: dark olive-grey at the top, clear at the bottom
uniform float frame_grad : hint_range(0.0, 1.0) = 0.0;
uniform vec4 frame_top : source_color = vec4(0.294, 0.322, 0.282, 1.0);
uniform vec4 frame_bottom : source_color = vec4(0.85, 0.85, 0.82, 1.0);
uniform float frame_bottom_alpha : hint_range(0.0, 1.0) = 0.3;
uniform vec2 grad_range = vec2(0.25, 0.85);
uniform sampler2D grad_mask : filter_nearest, repeat_disable, hint_default_black;

varying float v_temple;
varying float v_grad;

void vertex() {
	ivec2 ms = textureSize(arm_mask, 0);
	v_temple = texelFetch(arm_mask, ivec2(VERTEX_ID % ms.x, VERTEX_ID / ms.x), 0).g;
	v_grad = 0.0;
	if (frame_grad > 0.0) {
		ivec2 gs = textureSize(grad_mask, 0);
		v_grad = texelFetch(grad_mask, ivec2(VERTEX_ID % gs.x, VERTEX_ID / gs.x), 0).r;
	}
}

void fragment() {
	vec4 t = texture(albedo_tex, UV) * tint;
	float lens = 1.0 - step(0.99, t.a);
	t.rgb = mix(t.rgb, frame_color.rgb, frame_flat * (1.0 - lens));
	float fa = 1.0;
	if (frame_grad > 0.0) {
		float g = smoothstep(grad_range.x, grad_range.y, v_grad);
		t.rgb = mix(t.rgb, mix(frame_top.rgb, frame_bottom.rgb, g), frame_grad * (1.0 - lens));
		fa = mix(1.0, frame_bottom_alpha, g * frame_grad);
	}
	float ta = t.a * lens_tint;
	float a = mix(fa, ta * ta, lens);
	ALBEDO = t.rgb * a;
	ALPHA = a;
	METALLIC = frame_metallic * (1.0 - lens);
	// geometric specular anti-aliasing on the temple arms (see the top); a close arm keeps its gloss
	vec3 dn = fwidth(NORMAL);
	float aa = v_temple * smoothstep(0.15, 0.8, sqrt(dot(dn, dn)));
	ROUGHNESS = mix(mix(frame_roughness, max(frame_roughness, arm_aa_roughness), aa), lens_roughness, lens);
	SPECULAR = mix(frame_specular * (1.0 - arm_aa_dim * aa), lens_specular, lens);
}
