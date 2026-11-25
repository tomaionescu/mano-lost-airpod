shader_type sky;
// Time-of-day sky driven by WorldEnv.apply_time(): two HDRI panoramas, each turned so its own sun sits on the
// real sun's bearing, blended by `pano_t`; a sun disk at the true sun position; then a fade by `night_t` into a
// procedural twilight / city-night sky (afterglow toward the set sun, orange-grey light pollution low over the
// periphérique), with a handful of stars and the crescent moon drawn on top. The radiance pass (ambient light,
// reflections, SDFGI) gets its own gain, tint and fill, so the ambient can follow the preset without changing how
// the sky looks. Colours are linear (no source_color hint). No TIME: the sky stays in incremental radiance mode.

uniform sampler2D pano_a : filter_linear, repeat_enable, hint_default_black;
uniform sampler2D pano_b : filter_linear, repeat_enable, hint_default_black;
uniform float yaw_a = 0.0;
uniform float yaw_b = 0.0;
uniform float pano_t : hint_range(0.0, 1.0) = 0.0;
// luminance cap on the HDRIs: their own suns (the dusk one peaks at ~2600) sit 2-10 degrees off the real one, so
// they are flattened into their halo and the disk below draws the sun where it really is
uniform float pano_max = 6.0;
uniform float energy = 1.0;
uniform vec3 pano_tint = vec3(1.0);
uniform vec3 haze_a = vec3(0.1);
uniform vec3 haze_b = vec3(0.1);

uniform vec3 sun_dir = vec3(-0.95, 0.2, 0.24);   // toward the true sun, may be below the horizon
uniform vec3 sun_color = vec3(1.0, 0.74, 0.52);
uniform float sun_disk = 1.0;
uniform float sun_radius = 0.0052;               // radians (0.3 deg)

uniform float night_t : hint_range(0.0, 1.0) = 0.0;
uniform vec3 zenith = vec3(0.004, 0.006, 0.014);
uniform vec3 horizon = vec3(0.04, 0.03, 0.025);
uniform vec3 glow_color = vec3(0.5, 0.2, 0.08);  // afterglow above the set sun
uniform float glow = 0.0;
uniform vec3 city_color = vec3(0.1, 0.065, 0.035);
uniform float city = 1.0;
uniform vec3 ground = vec3(0.01, 0.01, 0.012);
uniform float stars = 0.0;
uniform vec3 moon_dir = vec3(0.0, -1.0, 0.0);
uniform float moon = 0.0;                        // brightness, 0 = not up
uniform float moon_lit = 0.24;                   // illuminated fraction
uniform float moon_radius = 0.0087;              // 0.5 deg, about twice the real moon so it reads at 1080p

uniform float ambient_gain = 1.0;
uniform vec3 ambient_tint = vec3(1.0);
uniform vec3 ambient_fill = vec3(0.0);

vec2 pano_uv(vec3 d, float yaw) {
	// turn the view direction back by the panorama's yaw (a rotation about +Y by -yaw)
	float c = cos(yaw);
	float s = sin(yaw);
	vec3 r = vec3(c * d.x - s * d.z, d.y, s * d.x + c * d.z);
	return vec2(fract(atan(r.x, -r.z) / TAU), acos(clamp(r.y, -1.0, 1.0)) / PI);
}

float hash13(vec3 p) {
	p = fract(p * 0.1031);
	p += dot(p, p.zyx + 31.32);
	return fract((p.x + p.y) * p.z);
}

vec3 capped(vec3 c) {
	float l = dot(c, vec3(0.2126, 0.7152, 0.0722));
	return c * min(1.0, pano_max / max(l, 1e-4));
}

vec3 night_sky(vec3 d) {
	float up = max(d.y, 0.0);
	vec3 col = mix(horizon, zenith, pow(up, 0.5));
	vec2 dh = normalize(d.xz + vec2(1e-5));
	vec2 sh = normalize(sun_dir.xz + vec2(1e-5));
	float toward = 0.5 + 0.5 * dot(dh, sh);
	col += glow_color * glow * pow(toward, 5.0) * exp(-up * 7.0);
	// light pollution all round, strongest toward Paris and the periphérique (-Z points to bearing 346)
	col += city_color * city * exp(-up * 6.0) * (0.55 + 0.45 * max(-dh.y, 0.0));
	return mix(ground, col, smoothstep(-0.03, 0.0, d.y));
}

// stars and the moon go over whatever sky is there, so the moon also shows in the blue hour
vec3 sky_objects(vec3 d) {
	vec3 col = vec3(0.0);
	if (stars > 0.0 && d.y > 0.04) {
		vec3 p = d * 240.0;
		vec3 cell = floor(p);
		float h = hash13(cell);
		if (h > 0.9994) {
			vec3 c = cell + 0.5 + (vec3(hash13(cell + 7.1), hash13(cell + 3.7), hash13(cell + 1.3)) - 0.5) * 0.5;
			float b = (h - 0.9994) / 0.0006;
			col += vec3(0.85, 0.92, 1.0) * stars * (0.05 + b * b * 0.5) * smoothstep(0.42, 0.05, length(p - c)) * smoothstep(0.04, 0.35, d.y);
		}
	}
	if (moon > 0.0) {
		float cd = dot(d, moon_dir);
		if (cd > cos(moon_radius * 12.0)) {
			// moon disk frame: x toward the sun, so the crescent's lit side faces the set sun
			vec3 ex = sun_dir - moon_dir * dot(sun_dir, moon_dir);
			ex = length(ex) > 1e-4 ? normalize(ex) : vec3(1.0, 0.0, 0.0);
			vec3 ey = cross(moon_dir, ex);
			vec2 q = vec2(dot(d, ex), dot(d, ey)) / moon_radius;
			float r = length(q);
			float disk = 1.0 - smoothstep(0.86, 1.0, r);
			float term = (1.0 - 2.0 * moon_lit) * sqrt(max(1.0 - q.y * q.y, 0.0));
			float lit = smoothstep(term - 0.12, term + 0.12, q.x);
			vec3 mc = vec3(1.0, 0.95, 0.86) * moon;
			col += mc * (lit + 0.012) * disk;
			col += mc * 0.012 * exp(-max(r - 1.0, 0.0) * 0.9) * step(1.0, r);
		}
	}
	return col * smoothstep(-0.01, 0.01, d.y);
}

void sky() {
	vec3 d = EYEDIR;
	vec3 col = vec3(0.0);
	if (night_t < 1.0) {
		vec3 a = capped(texture(pano_a, pano_uv(d, yaw_a)).rgb);
		vec3 b = capped(texture(pano_b, pano_uv(d, yaw_b)).rgb);
		if (d.y < 0.0) {
			// the HDRIs' own ground (a parking lot, a lagoon) must not show from a roof: below the horizon both
			// fade into a haze of their horizon's hue at their ground's brightness (WorldEnv._haze_of)
			float k = smoothstep(0.0, -0.05, d.y);
			a = mix(a, haze_a, k);
			b = mix(b, haze_b, k);
		}
		col = mix(a, b, pano_t) * energy * pano_tint;
		if (!AT_CUBEMAP_PASS && sun_disk > 0.0) {
			// the directional light already gives the sun's specular and ambient share: the disk is background only
			float ang = acos(clamp(dot(d, sun_dir), -1.0, 1.0));
			vec3 s = sun_color * sun_disk * (40.0 * smoothstep(sun_radius, sun_radius * 0.75, ang) + 0.8 * exp(-ang * 40.0) + 0.12 * exp(-ang * 7.0));
			col += s * smoothstep(-0.004, 0.003, d.y);
		}
	}
	if (night_t > 0.0) {
		col = mix(col, night_sky(d), night_t);
	}
	col += sky_objects(d);
	if (AT_CUBEMAP_PASS) {
		col = col * ambient_tint * ambient_gain + ambient_fill;
	}
	COLOR = col;
}
