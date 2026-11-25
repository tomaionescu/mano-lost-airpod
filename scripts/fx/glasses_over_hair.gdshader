shader_type spatial;
// next_pass of glasses.gdshader: the temple arms drawn again, only over hair and only where the hair lies less than
// hair_pull above them. A real arm presses the hair at the temple flat; the scan hair's cards are grown a few mm
// off the frames, so the arm would vanish into the sideburn and reappear behind the ear.
//  - only over hair: stencil 2, written by the hair core (hair_scan.gdshader) and its underlayer
//    (hair_under.gdshader); the skin of a character with glasses writes 0 (CharacterMaterials), so an ear in front
//    of the hair never shows the arm behind it
//  - pulled toward the camera by hair_pull along the view ray: the same pixels at a nearer depth, so it passes the
//    depth test against hair up to that far above the arm, and still fails against the head and far-side hair
//  - only the arms: arm_mask (one texel per vertex, by VERTEX_ID) marks the vertices 35 mm or more behind the front
//    of the frame in the rest pose (CharacterMaterials), so the front frame and lenses never draw over a fringe that
//    hangs in front of them. Not a test on the posed VERTEX: the idle pose moves the head several cm forward.
render_mode depth_draw_never, cull_back, diffuse_burley;
stencil_mode read, compare_equal, 2;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 tint : source_color = vec4(1.0);
uniform float frame_metallic : hint_range(0.0, 1.0) = 0.0;
uniform float frame_roughness : hint_range(0.0, 1.0) = 0.22;
uniform float frame_specular : hint_range(0.0, 1.0) = 0.8;
uniform float hair_pull : hint_range(0.0, 0.05) = 0.011;
uniform sampler2D arm_mask : filter_nearest, repeat_disable, hint_default_black;
uniform float arm_aa_roughness : hint_range(0.0, 1.0) = 0.45;
uniform float arm_aa_dim : hint_range(0.0, 1.0) = 0.6;
// as glasses.gdshader's (FINISH; 0: the texture as it is)
uniform float frame_flat : hint_range(0.0, 1.0) = 0.0;
uniform vec4 frame_color : source_color = vec4(0.5, 0.5, 0.5, 1.0);
// per person (FINISH; 1, the default: as above): 0 leaves the arms behind the hair, for long hair that hangs over
// them from the temple back (drawn over it, the arm would run across the hair to its end)
uniform float arm_over_hair : hint_range(0.0, 1.0) = 1.0;
// the frame's colour at the top of a two-tone front (glasses.gdshader's frame_grad: the arms are its top colour)
uniform float frame_grad : hint_range(0.0, 1.0) = 0.0;
uniform vec4 frame_top : source_color = vec4(0.294, 0.322, 0.282, 1.0);

varying float v_arm;

void vertex() {
	ivec2 ms = textureSize(arm_mask, 0);
	v_arm = texelFetch(arm_mask, ivec2(VERTEX_ID % ms.x, VERTEX_ID / ms.x), 0).r;
	vec3 p = (MODELVIEW_MATRIX * vec4(VERTEX, 1.0)).xyz;
	float d = length(p);
	p *= max(d - hair_pull, 0.02) / max(d, 1e-4);
	POSITION = PROJECTION_MATRIX * vec4(p, 1.0);
}

void fragment() {
	vec4 t = texture(albedo_tex, UV) * tint;
	if (v_arm < 0.5 || t.a < 0.9 || arm_over_hair < 0.5) {
		discard;
	}
	ALBEDO = mix(mix(t.rgb, frame_color.rgb, frame_flat), frame_top.rgb, frame_grad);
	METALLIC = frame_metallic;
	// the same anti-aliasing as the arms in glasses.gdshader (the same pixels, a nearer depth)
	vec3 dn = fwidth(NORMAL);
	float aa = smoothstep(0.15, 0.8, sqrt(dot(dn, dn)));
	ROUGHNESS = mix(frame_roughness, max(frame_roughness, arm_aa_roughness), aa);
	SPECULAR = frame_specular * (1.0 - arm_aa_dim * aa);
}
