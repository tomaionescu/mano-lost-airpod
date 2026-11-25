shader_type spatial;
// PROTOTYPE B (not wired into the game): the hair's underlayer, i.e. the scan's hair shell after Taubin
// smoothing, 1.5 mm inside the surface the strand cards of proto_hair_B.gdshader follow. Only seen through the
// gaps between cards, so it must read as depth inside the hair, not as a surface: the hair's root colour (a
// uniform, so Mano and Anisha read black whatever brown the scan baked), with a little of the bake's light and
// dark kept so it is not a flat sheet; fully matte, no rim (a rim and a sheen would make it
// look like plastic), a soft wrap so its shadowed side does not go pitch black against the lit cards above.
render_mode cull_back, depth_draw_opaque, diffuse_burley, specular_disabled;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform vec4 root_color : source_color = vec4(0.03, 0.022, 0.018, 1.0);
uniform float bake_lo = 0.0;
uniform float bake_hi = 0.08;
uniform float wrap : hint_range(0.0, 1.0) = 0.3;

void fragment() {
	float lum = dot(texture(albedo_tex, UV).rgb, vec3(0.2126, 0.7152, 0.0722));
	ALBEDO = root_color.rgb * mix(0.7, 1.3, smoothstep(bake_lo, bake_hi, lum));
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}

void light() {
	float ndl = dot(NORMAL, LIGHT);
	DIFFUSE_LIGHT += LIGHT_COLOR * ATTENUATION * clamp((ndl + wrap) / (1.0 + wrap), 0.0, 1.0) / PI;
}
