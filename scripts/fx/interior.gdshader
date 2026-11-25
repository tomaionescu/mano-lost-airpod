// Interior mapping for windows of rooms the player never enters (docs/DESIGN.md V2-18): no cubemaps, no textures.
// Each window quad looks into its own box-shaped room, ray-traced per pixel: back wall, side walls with a cupboard
// or a board, floor, ceiling with a light fitting (offices: tiles and a grid of LED panels), one piece of furniture,
// blinds or curtains, frames for lean windows.
// The level writes the window into its UVs (campus_arch.window(interior=...)): UV.x = seed + u and, in Blender
// space, v = lit + v' (lit = 0..8, the chance out of 8 that the room is lit at night). The glTF export flips v,
// hence the -UV.y below. The window's size in metres comes from the screen-space derivatives of the position
// against the UVs, so any window size works with the same material.
// WorldEnv drives `emission_energy` with the time of day (0 at 17:42, 1.5 after sunset; LevelBinder lists the
// material with the lit windows).
shader_type spatial;
render_mode blend_mix, depth_draw_opaque, cull_back, diffuse_burley, specular_schlick_ggx;

uniform float emission_energy = 0.0;
uniform float room_depth = 5.0;           // metres behind the glass (jittered per room)
uniform float floor_below = 0.9;          // from the window's bottom edge down to the room floor
uniform float ceiling_above = 0.45;       // from the window's top edge up to the ceiling
uniform float side_margin = 0.8;          // the room runs on past each side of the window
uniform float kind = 0.0;                 // 0 office / classroom, 1 flat, 2 hotel room
uniform float lit_scale = 1.0;            // multiplies the per-window chance of a lit room
uniform float day_level = 0.22;           // brightness of a room by daylight (before sunset)
uniform float blinds_chance = 0.35;
uniform float curtains_chance = 0.0;
uniform float tv_chance = 0.0;            // unlit flats with a TV on
uniform float frame_width = 0.0;          // > 0: the shader draws the frame and a mullion (lean windows)
uniform vec3 frame_color : source_color = vec3(0.9, 0.9, 0.88);
uniform vec3 warm_light : source_color = vec3(1.0, 0.78, 0.52);
uniform vec3 cool_light : source_color = vec3(0.86, 0.93, 1.0);
uniform float cool_share = 0.3;
uniform vec3 wall_a : source_color = vec3(0.86, 0.84, 0.79);
uniform vec3 wall_b : source_color = vec3(0.78, 0.82, 0.86);
uniform vec3 floor_a : source_color = vec3(0.36, 0.38, 0.42);
uniform vec3 floor_b : source_color = vec3(0.52, 0.40, 0.29);
uniform vec3 furniture_color : source_color = vec3(0.30, 0.28, 0.26);
uniform vec3 blind_color : source_color = vec3(0.86, 0.84, 0.78);
uniform vec3 curtain_color : source_color = vec3(0.62, 0.28, 0.24);
uniform float glass_tint = 0.88;

varying vec3 v_wpos;

float h1(float p) {
	p = fract(p * 0.1031);
	p *= p + 33.33;
	p *= p + p;
	return fract(p);
}

float box_hit(vec3 ro, vec3 rd, vec3 bmin, vec3 bmax, out vec3 n) {
	vec3 t0 = (bmin - ro) / rd;
	vec3 t1 = (bmax - ro) / rd;
	vec3 tn3 = min(t0, t1);
	vec3 tf3 = max(t0, t1);
	float tn = max(max(tn3.x, tn3.y), tn3.z);
	float tf = min(min(tf3.x, tf3.y), tf3.z);
	n = vec3(0.0);
	if (tn > tf || tn <= 0.0) {
		return 1e9;
	}
	if (tn == tn3.x) {
		n = vec3(-sign(rd.x), 0.0, 0.0);
	} else if (tn == tn3.y) {
		n = vec3(0.0, -sign(rd.y), 0.0);
	} else {
		n = vec3(0.0, 0.0, -sign(rd.z));
	}
	return tn;
}

void vertex() {
	v_wpos = (MODEL_MATRIX * vec4(VERTEX, 1.0)).xyz;
}

void fragment() {
	// window space: x right, y up (metres from the bottom-left corner), z into the room
	vec2 uvw = vec2(UV.x, -UV.y);
	vec2 st = fract(uvw);
	float seed = floor(uvw.x);
	float lit_chance = clamp((floor(uvw.y) + 1.0) / 8.0 * lit_scale, 0.0, 1.0);
	vec3 dpx = dFdx(v_wpos);
	vec3 dpy = dFdy(v_wpos);
	vec2 dux = dFdx(uvw);
	vec2 duy = dFdy(uvw);
	float det = dux.x * duy.y - dux.y * duy.x;
	det = abs(det) < 1e-14 ? 1e-14 : det;
	vec3 tw = (dpx * duy.y - dpy * dux.y) / det;
	vec3 bw = (dpy * dux.x - dpx * duy.x) / det;
	float W = clamp(length(tw), 0.2, 12.0);
	float H = clamp(length(bw), 0.2, 12.0);
	vec3 ex = tw / max(length(tw), 1e-4);
	vec3 ey = bw / max(length(bw), 1e-4);
	vec3 ez = normalize(cross(ey, ex));
	vec3 V = normalize(v_wpos - CAMERA_POSITION_WORLD);
	vec3 rd = vec3(dot(V, ex), dot(V, ey), max(dot(V, ez), 0.02));
	rd.x = abs(rd.x) < 1e-4 ? 1e-4 : rd.x;
	rd.y = abs(rd.y) < 1e-4 ? 1e-4 : rd.y;
	vec3 ro = vec3(st.x * W, st.y * H, 0.0);

	float r1 = h1(seed * 1.37 + 0.11);
	float r2 = h1(seed * 2.11 + 0.37);
	float r3 = h1(seed * 3.07 + 0.59);
	float r4 = h1(seed * 4.33 + 0.71);
	float r5 = h1(seed * 5.71 + 0.23);
	float r6 = h1(seed * 6.97 + 0.83);
	float D = room_depth * (0.8 + 0.4 * r1);
	float mL = side_margin * (0.3 + 1.4 * r2);
	float mR = side_margin * (0.3 + 1.4 * r3);
	vec3 bmin = vec3(-mL, -floor_below, 0.0);
	vec3 bmax = vec3(W + mR, H + ceiling_above, D);

	// the room box seen from inside: the nearest far plane
	vec3 ta = (bmin - ro) / rd;
	vec3 tb = (bmax - ro) / rd;
	vec3 tf = max(ta, tb);
	float t = min(min(tf.x, tf.y), tf.z);
	vec3 p = ro + rd * t;
	vec3 wall = mix(wall_a, wall_b, step(0.5, r4)) * (0.88 + 0.24 * r5);
	vec3 base;
	vec3 n;
	if (t == tf.z) {
		n = vec3(0.0, 0.0, -1.0);
		base = wall;
		// a picture, a poster or a whiteboard on the back wall, a door on one side
		vec2 c = vec2(mix(bmin.x + 0.9, bmax.x - 0.9, r6), -floor_below + 1.55);
		vec2 hs = kind < 0.5 ? vec2(0.9, 0.5) : vec2(0.35 + 0.3 * r1, 0.28 + 0.15 * r2);
		if (abs(p.x - c.x) < hs.x && abs(p.y - c.y) < hs.y) {
			base = kind < 0.5 ? vec3(0.92, 0.93, 0.94) : mix(vec3(0.25, 0.42, 0.56), vec3(0.74, 0.46, 0.22), r3);
		}
		float dx = r6 > 0.5 ? bmin.x + 0.25 : bmax.x - 1.15;
		if (p.x > dx && p.x < dx + 0.9 && p.y < -floor_below + 2.05) {
			base = kind > 1.5 ? vec3(0.35, 0.25, 0.18) : wall * 0.72;
		}
	} else if (t == tf.x) {
		n = vec3(-sign(rd.x), 0.0, 0.0);
		base = wall * 0.9;
		float fy = p.y + floor_below;            // height above the room's floor
		if (kind < 0.5) {
			// offices: a tall cupboard (grey steel or wood) or a cork board on the side walls; seen at a slant from
			// the street, the side wall is most of what shows
			if (abs(p.z - D * (0.3 + 0.35 * r2)) < 0.55 && fy < 1.95) {
				base = r5 > 0.5 ? vec3(0.58, 0.58, 0.56) : vec3(0.42, 0.32, 0.22);
			} else if (abs(p.z - D * 0.78) < 0.45 && fy > 1.05 && fy < 1.75) {
				base = vec3(0.62, 0.46, 0.3);
			}
		} else if (kind < 1.5 && fy < 1.9 && p.z > D * 0.25 && p.z < D * 0.25 + 1.2) {
			base = mix(vec3(0.44, 0.31, 0.2), vec3(0.85, 0.85, 0.82), step(0.5, r5));   // wardrobe or shelf
		}
	} else if (rd.y < 0.0) {
		n = vec3(0.0, 1.0, 0.0);
		base = mix(floor_a, floor_b, step(0.55, r6));
		base *= 0.9 + 0.1 * h1(floor(p.x / 0.6) * 7.0 + floor(p.z / 0.6) * 13.0 + seed);
	} else {
		n = vec3(0.0, -1.0, 0.0);
		base = vec3(0.9, 0.9, 0.88);
		if (kind < 0.5) {
			// a suspended ceiling of 60 cm tiles, what you mostly see of an office from the street
			vec2 g = abs(fract(p.xz / 0.6) - 0.5);
			base *= 0.9 + 0.1 * step(max(g.x, g.y), 0.46);
		}
	}
	if (abs(n.y) < 0.5 && p.y + floor_below < 0.09) {
		base *= 0.55;   // skirting
	}

	// one piece of furniture: a row of desks (offices), a sofa (flats), a bed (hotel rooms)
	vec3 fmin;
	vec3 fmax;
	if (kind < 0.5) {
		fmin = vec3(bmin.x + 0.3, -floor_below, D * 0.42);
		fmax = vec3(bmax.x - 0.3, -floor_below + 0.75, D * 0.42 + 0.8);
	} else if (kind < 1.5) {
		fmin = vec3(mix(bmin.x, bmax.x, 0.18 + 0.2 * r2), -floor_below, D - 0.95);
		fmax = vec3(fmin.x + 1.9, -floor_below + 0.85, D);
	} else {
		fmin = vec3(mix(bmin.x, bmax.x, 0.2), -floor_below, D - 2.1);
		fmax = vec3(mix(bmin.x, bmax.x, 0.8), -floor_below + 0.58, D);
	}
	vec3 fn;
	float tfur = box_hit(ro, rd, fmin, fmax, fn);
	if (tfur < t) {
		t = tfur;
		p = ro + rd * t;
		n = fn;
		base = kind > 1.5 ? vec3(0.92, 0.91, 0.88) : furniture_color * (0.8 + 0.4 * r4);
		if (kind < 0.5 && fn.y > 0.5) {
			base = vec3(0.86, 0.85, 0.82);   // desk top
		}
	}
	// a screen on the office desks
	vec3 smin = vec3(mix(bmin.x, bmax.x, 0.3 + 0.3 * r3), -floor_below + 0.75, D * 0.42 + 0.35);
	vec3 smax = smin + vec3(0.55, 0.38, 0.04);
	vec3 sn;
	float tscr = kind < 0.5 ? box_hit(ro, rd, smin, smax, sn) : 1e9;

	// light: the fitting in the middle of the ceiling; daylight from the window
	float on = step(h1(seed * 9.91 + 0.5), lit_chance);
	vec3 lcol = mix(warm_light, cool_light, step(1.0 - cool_share, h1(seed * 7.13 + 0.3)));
	vec3 lamp = vec3((bmin.x + bmax.x) * 0.5, bmax.y - 0.05, D * 0.5);
	vec3 L = lamp - p;
	float dl = length(L);
	float ndl = max(dot(n, L / max(dl, 1e-3)), 0.0);
	float fall = 1.0 / (1.0 + 0.18 * dl * dl);
	// rooms are not all lit alike (dimmer lamps, older tubes), and a lit room keeps some shade: a flat even glow
	// read as a white card up close
	float dim = 0.7 + 0.5 * h1(seed * 3.71 + 0.13);
	vec3 night = base * lcol * (0.12 + 1.6 * ndl * fall) * on * dim;
	if (n.y < -0.5) {
		if (kind < 0.5) {
			// offices: 60 cm LED panels on a 1.8 m grid round the middle of the room
			vec2 q = abs(fract((p.xz - lamp.xz) / 1.8 + 0.5) - 0.5) * 1.8;
			if (q.x < 0.3 && q.y < 0.3) {
				night = lcol * 2.4 * on;
			}
		} else if (abs(p.x - lamp.x) < 0.18 && abs(p.z - lamp.z) < 0.18) {
			night = lcol * 3.0 * on;   // the light fitting itself
		}
	}
	float day_fall = clamp(1.15 - 0.6 * p.z / D, 0.35, 1.2) * (0.75 + 0.25 * max(-n.y, 0.0) + 0.15 * max(n.y, 0.0));
	vec3 day = base * day_level * day_fall * vec3(0.92, 0.96, 1.04);
	float nightness = clamp(emission_energy / 1.5, 0.0, 1.0);
	vec3 rad = day * (1.0 - nightness) + night * emission_energy;
	if (tscr < t) {
		rad = mix(vec3(0.02), vec3(0.25, 0.42, 0.75), on) * (0.4 + emission_energy);
	}
	// unlit flats: now and then a television
	if (on < 0.5 && h1(seed * 11.3 + 0.9) < tv_chance) {
		float flick = 0.6 + 0.4 * sin(TIME * 7.0 + seed) * sin(TIME * 2.3 + seed * 1.7);
		rad += base * vec3(0.25, 0.35, 0.7) * 0.35 * flick * emission_energy;
	}

	// blinds and curtains just behind the glass; a ray that leaves the pane's rectangle there would be inside the
	// window reveal, so it is clamped back onto the pane (an edge pixel seen at a grazing angle hits its own blind)
	vec3 q = ro + rd * (0.07 / rd.z);
	q.xy = clamp(q.xy, vec2(0.0), vec2(W, H));
	// never lowered all the way: a strip of the room stays in view under the blind
	float blind = h1(seed * 13.7 + 0.2) < blinds_chance ? 0.15 + 0.68 * h1(seed * 17.1 + 0.4) : 0.0;
	vec3 lit_inside = mix(vec3(day_level * 1.2) * (1.0 - nightness), lcol * 0.75 * emission_energy * on * dim + vec3(0.004), nightness);
	if (blind > 0.0 && q.y > H * (1.0 - blind)) {
		// slats 7 cm apart, faded out where they get smaller than a pixel (no moire); lit from behind, a blind
		// glows most in the middle, under the ceiling light
		float sf = q.y / 0.07;
		float slat = 0.84 + 0.16 * sin(sf * 6.2832) * clamp(1.5 - 2.0 * fwidth(sf), 0.0, 1.0);
		float glow = 0.78 + 0.22 * (1.0 - abs(q.x / W - 0.5) * 2.0);
		rad = blind_color * slat * glow * lit_inside;
	}
	float cw = h1(seed * 19.3 + 0.6) < curtains_chance ? W * (0.12 + 0.3 * h1(seed * 23.9)) : 0.0;
	if (cw > 0.0 && (q.x < cw || q.x > W - cw)) {
		float fold = 0.8 + 0.2 * sin(q.x * 38.0);
		// flats each hang their own: mostly cream sheers and greys, now and then a colour
		vec3 cc = curtain_color;
		if (kind > 0.5 && kind < 1.5) {
			float rc = h1(seed * 29.3 + 0.7);
			cc = rc < 0.35 ? vec3(0.86, 0.83, 0.76) : rc < 0.55 ? vec3(0.56, 0.57, 0.58) : rc < 0.68 ? vec3(0.32, 0.40, 0.56)
				: rc < 0.8 ? vec3(0.68, 0.55, 0.36) : rc < 0.9 ? vec3(0.42, 0.50, 0.38) : curtain_color;
		}
		rad = cc * fold * lit_inside * 1.1;
	}
	rad *= glass_tint;

	ALBEDO = vec3(0.025, 0.028, 0.032);
	ROUGHNESS = 0.06;
	METALLIC = 0.0;
	SPECULAR = 0.5;
	EMISSION = rad;
	if (frame_width > 0.0) {
		vec2 m = st * vec2(W, H);
		float fw = frame_width;
		bool fr = m.x < fw || m.x > W - fw || m.y < fw || m.y > H - fw || abs(m.x - W * 0.5) < fw * 0.45;
		if (W > 1.9) {
			fr = fr || abs(m.x - W * 0.25) < fw * 0.4 || abs(m.x - W * 0.75) < fw * 0.4;
		}
		if (fr) {
			ALBEDO = frame_color;
			ROUGHNESS = 0.5;
			EMISSION = vec3(0.0);
		}
	}
}
