shader_type spatial;
// A dust mote (docs/DESIGN.md §4.8): a tiny additive speck that only shows where direct light reaches it, so the dust
// draws the sunbeams in Amphi 4 and the lobby and disappears in the shade. Lit by the sun with its shadows (the
// light() ATTENUATION), scattered forward (brightest when looking toward the light); lamps barely count.
render_mode blend_add, depth_draw_never, cull_disabled, ambient_light_disabled, specular_disabled;

uniform float strength = 0.045;

void vertex() {
	// camera-facing, keeping the particle's scale
	MODELVIEW_MATRIX = VIEW_MATRIX * mat4(INV_VIEW_MATRIX[0], INV_VIEW_MATRIX[1], INV_VIEW_MATRIX[2], MODEL_MATRIX[3]);
	MODELVIEW_MATRIX = MODELVIEW_MATRIX * mat4(vec4(length(MODEL_MATRIX[0].xyz), 0.0, 0.0, 0.0),
		vec4(0.0, length(MODEL_MATRIX[1].xyz), 0.0, 0.0), vec4(0.0, 0.0, length(MODEL_MATRIX[2].xyz), 0.0), vec4(0.0, 0.0, 0.0, 1.0));
	MODELVIEW_NORMAL_MATRIX = mat3(MODELVIEW_MATRIX);
}

void fragment() {
	float r = length(UV - 0.5) * 2.0;
	ALBEDO = vec3(1.0, 0.97, 0.92);
	// COLOR.a: the particle's fade in and out over its life
	ALPHA = (1.0 - smoothstep(0.2, 1.0, r)) * COLOR.a;
}

void light() {
	float fwd = max(dot(-LIGHT, VIEW), 0.0);
	float phase = 0.3 + 2.7 * fwd * fwd * fwd * fwd;
	float k = LIGHT_IS_DIRECTIONAL ? 1.0 : 0.12;
	DIFFUSE_LIGHT += LIGHT_COLOR * ATTENUATION * phase * k * strength;
}
