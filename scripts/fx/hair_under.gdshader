shader_type spatial;
// The underlayer of scanned hair (kind "hairunder", tools/blender/hair_scan_cards.py): the scan's hair shell after
// Taubin smoothing, 1.5 mm inside the surface the strand cards follow. Only seen through the gaps between cards,
// so it must read as depth inside the hair, not as a surface: its colour is baked at build time (the person's
// dark root colour, a little of the scan's light and dark kept so it is not a flat sheet); fully matte, no rim
// (a rim and a sheen make it read as a plastic helmet); a soft wrap so its shadowed side
// does not go pitch black against the lit cards above it. Casts shadows (an opaque volume under the cards).
// Writes stencil 2 ("hair here") like the cards' core: glasses_over_hair.gdshader draws the temple arms over it.
// Single-sided: the build keeps only the triangles facing their cards (hair_scan_cards.generate), so a view from
// inside the hair (between a long front lock and the back hair) ends on the backs of the cards, strands, not on a
// smooth black sheet. Its shadow stays double-sided (CharacterMaterials).
render_mode cull_back, depth_draw_opaque, diffuse_burley, specular_disabled;
stencil_mode write, compare_always, 2;

uniform sampler2D albedo_tex : source_color, filter_linear_mipmap_anisotropic;
uniform float gain : hint_range(0.0, 3.0) = 1.0;
uniform float wrap : hint_range(0.0, 1.0) = 0.3;
// per person (CharacterMaterials.FINISH; 0: off), as the cards' (hair_scan.gdshaderinc): the ambient light sees
// the albedo pushed toward its own hue, the direct lights see it as it is
uniform float ambient_warm : hint_range(0.0, 2.0) = 0.0;
// (per person; 1: off) the albedo the ambient light sees x ambient_gain, as the cards'
uniform float ambient_gain : hint_range(0.0, 8.0) = 1.0;
varying vec3 v_alb_k;

void fragment() {
	ALBEDO = texture(albedo_tex, UV).rgb * gain;
	if (ambient_warm > 0.0 || ambient_gain != 1.0) {
		vec3 hue = ALBEDO / max(dot(ALBEDO, vec3(0.2126, 0.7152, 0.0722)), 1e-4);
		vec3 w = ALBEDO * mix(vec3(1.0), clamp(hue, vec3(0.2), vec3(3.0)), ambient_warm) * ambient_gain;
		v_alb_k = ALBEDO / max(w, vec3(1e-5));
		ALBEDO = w;
	}
	ROUGHNESS = 1.0;
	SPECULAR = 0.0;
}

void light() {
	float ndl = dot(NORMAL, LIGHT);
	vec3 d = LIGHT_COLOR * ATTENUATION * clamp((ndl + wrap) / (1.0 + wrap), 0.0, 1.0) / PI;
	if (ambient_warm > 0.0 || ambient_gain != 1.0) {
		d *= v_alb_k;
	}
	DIFFUSE_LIGHT += d;
}
