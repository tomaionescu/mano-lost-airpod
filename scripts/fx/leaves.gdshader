shader_type particles;
render_mode disable_velocity, disable_force;
// October leaves (docs/DESIGN.md §4.8): each one lets go of a random tree crown, flutters down at 0.4-1.2 m/s in the
// breeze (a pendulum swing, or a tumble for about a third of them), lies on the ground a few seconds and shrinks
// away. FallingLeaves (falling_leaves.gd) fills the crowns and bakes the ground heights under them.
// CUSTOM: x the leaf's seed, y its age (s), z its atlas cell (leaf_card.gdshader), w the age it landed at (0: falling).

// at most 32 crowns (FallingLeaves.MAX_CROWNS)
uniform int crown_count = 0;
uniform vec4 crowns[32];      // xyz crown centre, w crown radius (m)
uniform vec4 crown_info[32];  // x ground height at the trunk, y kind (0 plane tree, 1 birch)
uniform vec2 wind = vec2(0.26, -0.16);   // drift (m/s) along world x and z: a south-westerly breeze
uniform sampler2D ground : filter_nearest, hint_default_black;   // ground heights (m) baked by raycasts; below -50: not baked
uniform vec4 ground_rect = vec4(1e9, 1e9, 1.0, 1.0);   // x, z of the map's corner; 1 / its size along x, z
uniform float rest_time = 3.0;   // seconds a leaf lies on the ground before it shrinks away

float rnd(inout uint s) {
	s = s * 747796405u + 2891336453u;
	uint w = ((s >> ((s >> 28u) + 4u)) ^ s) * 277803737u;
	return float((w >> 22u) ^ w) / 4294967295.0;
}

mat3 axis_rot(vec3 a, float t) {
	float c = cos(t);
	float s = sin(t);
	float k = 1.0 - c;
	return mat3(vec3(c + a.x * a.x * k, a.y * a.x * k + a.z * s, a.z * a.x * k - a.y * s),
		vec3(a.x * a.y * k - a.z * s, c + a.y * a.y * k, a.z * a.y * k + a.x * s),
		vec3(a.x * a.z * k + a.y * s, a.y * a.z * k - a.x * s, c + a.z * a.z * k));
}

float ground_at(vec3 p, float fallback) {
	vec2 uv = (p.xz - ground_rect.xy) * ground_rect.zw;
	if (uv.x < 0.0 || uv.y < 0.0 || uv.x > 1.0 || uv.y > 1.0) {
		return fallback;
	}
	float h = textureLod(ground, uv, 0.0).r;
	return h < -50.0 ? fallback : h;
}

void start() {
	uint s = RANDOM_SEED + NUMBER * 7919u;
	float seed = rnd(s);
	uint p = uint(seed * 16777215.0);
	int k = min(int(rnd(p) * float(crown_count)), max(crown_count - 1, 0));
	vec4 cr = crowns[k];
	// a point in the crown, more of them toward its outside
	vec3 d = normalize(vec3(rnd(p), rnd(p), rnd(p)) * 2.0 - 1.0 + vec3(0.0001));
	vec3 pos = cr.xyz + d * pow(rnd(p), 0.33) * vec3(cr.w, cr.w * 0.75, cr.w);
	float birch = crown_info[k].y;
	float cell = birch > 0.5 ? 2.0 : (rnd(p) < 0.5 ? 0.0 : (rnd(p) < 0.5 ? 1.0 : 3.0));
	CUSTOM = vec4(seed, 0.0, cell, 0.0);
	TRANSFORM = mat4(vec4(0.0), vec4(0.0), vec4(0.0), vec4(pos, 1.0));
	VELOCITY = vec3(0.0);
	ACTIVE = crown_count > 0;
}

void process() {
	// the same draws as start(), then this leaf's own fall
	uint p = uint(CUSTOM.x * 16777215.0);
	int k = min(int(rnd(p) * float(crown_count)), max(crown_count - 1, 0));
	rnd(p);
	rnd(p);
	rnd(p);
	rnd(p);
	float birch = crown_info[k].y;
	float fall = mix(0.4, 1.2, rnd(p));
	float swing_a = mix(0.15, 0.35, rnd(p));
	float swing_w = mix(2.5, 4.0, rnd(p));
	float ph = rnd(p) * 6.2831853;
	float yaw = rnd(p) * 6.2831853;
	vec2 swing_dir = vec2(cos(yaw), sin(yaw));
	float drift = mix(0.6, 1.4, rnd(p));
	bool tumbler = rnd(p) < 0.33;
	vec3 axis = normalize(vec3(rnd(p), rnd(p), rnd(p)) * 2.0 - 1.0 + vec3(0.0001));
	float spin = mix(3.0, 7.0, rnd(p)) * (rnd(p) < 0.5 ? -1.0 : 1.0);
	float size = birch > 0.5 ? mix(0.05, 0.075, rnd(p)) : mix(0.14, 0.22, rnd(p));   // a plane leaf is a hand wide

	float age = CUSTOM.y + DELTA;
	CUSTOM.y = age;
	vec3 pos = TRANSFORM[3].xyz;
	float landed = CUSTOM.w;
	float c = cos(swing_w * age + ph);
	if (landed <= 0.0) {
		vec3 v = vec3(wind.x * drift, -fall * (0.4 + 1.2 * c * c), wind.y * drift);
		v.xz += swing_dir * swing_a * swing_w * c;
		pos += v * DELTA;
		float g = ground_at(pos, crown_info[k].x) + 0.012;
		if (pos.y <= g) {
			pos.y = g;
			CUSTOM.w = age;
			landed = age;
		}
	}
	// lying flat on the ground: the quad's +Z face turned up, at the leaf's own yaw
	mat3 lying = mat3(vec3(cos(yaw), 0.0, sin(yaw)), vec3(sin(yaw), 0.0, -cos(yaw)), vec3(0.0, 1.0, 0.0));
	mat3 r;
	float t = landed > 0.0 ? landed : age;
	if (tumbler) {
		r = axis_rot(axis, spin * t) * lying;
	} else {
		// rocks with the swing about the horizontal axis across it, and turns slowly
		vec3 across = vec3(-swing_dir.y, 0.0, swing_dir.x);
		r = axis_rot(vec3(0.0, 1.0, 0.0), 0.4 * t) * axis_rot(across, 0.6 * sin(swing_w * t + ph)) * lying;
	}
	if (landed > 0.0) {
		float k2 = clamp((age - landed) / 0.3, 0.0, 1.0);
		r = mat3(normalize(mix(r[0], lying[0], k2)), normalize(mix(r[1], lying[1], k2)), normalize(mix(r[2], lying[2], k2)));
	}
	float shrink = landed > 0.0 ? 1.0 - smoothstep(rest_time, rest_time + 0.6, age - landed) : 1.0;
	// grows in over the first quarter second so no leaf pops into the crown
	float grow = smoothstep(0.0, 0.25, age);
	r *= size * shrink * grow;
	TRANSFORM = mat4(vec4(r[0], 0.0), vec4(r[1], 0.0), vec4(r[2], 0.0), vec4(pos, 1.0));
	if (landed > 0.0 && age - landed > rest_time + 0.6) {
		ACTIVE = false;
	}
}
