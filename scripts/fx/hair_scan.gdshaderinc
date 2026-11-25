// Shared by hair_scan.gdshader and hair_scan_fringe.gdshader: the strand cards laid over a scan's hair shell
// (tools/blender/hair_scan_cards.py). Include after hair_common.gdshaderinc (it uses albedo_tex, tint, kajiya()).
//  - COLOR.rgb is each card's depth tone (inner layers ~0.3, outer ~1), multiplied in by scan_albedo(); the hair's
//    colour itself is in the per-person atlas (sRGB, BC7: BC1/BC3 turned near-black hair green and orange), never
//    in the 8-bit vertex colour
//  - COLOR.a fades a card in from its root (most cards start on top of other hair: a hard root edge in the middle
//    of the hair reads as a stack of chips). scan_root_fade() staggers it per strand (a column of the atlas): the
//    fade is linear across a row of vertices, so the alpha-tested core cut every card's root off along a straight
//    line across the card, the top edge of the pale rectangular chips.
//  - NORMAL is the hair volume's normal (the guide's smoothed normal, written as the cards' vertex normals). Godot
//    flips NORMAL on the back face of a double-sided surface: a card seen from behind (the underside of a fringe or
//    quiff, the inside of a curl, a card at the silhouette) then lit as if it faced into the head and came out as a
//    flat black shard; with the volume normal kept as is, a lock curling away showed its back as a dark slate
//    patch. scan_frontal() keeps the volume normal, and a card seen from behind also takes back_light of the light
//    on its other side (a thin lock lets light through), so every card lights as part of one mass of hair (the
//    shadow map still darkens what lies under other hair).
//  - the strand direction is the mesh's own tangent frame (MikkTSpace at import; each card is a strip with shared
//    vertices), smooth along a card. The UV gradient (strand_dir) is constant over each card triangle: a highlight
//    computed from it lit whole triangles at once (pale rectangles, "broken glass"), so it only orients the tangent.
//  - the highlight is the hair's own colour, brightened: the person's hair hue (the atlas' average) at spec_rel x
//    the strip's brightness + spec_abs, under the light's brightness with only spec_light_tint of the light's own
//    colour. A near-white highlight read as grey-white chalk on dark hair, and the blue fill light's colour turned
//    dark hair's edges navy. Two broad Kajiya-Kay lobes, the second tinted twice by the hair (TRT).
//  - highlights follow the strands: multiplied per texel by the strand's brightness against its neighbourhood and
//    its coverage, so a highlight is a soft band broken into streaks along the strands, never a smooth sheet; faded
//    where a card turns edge-on (the underlayer shows there) and toward the roots; kept to inner_spec on the inner
//    layers (layer-aware, from the depth tone)
//  - a card seen much more edge-on than the hair surface fades out (scan_edge_on): squeezed into a coarse mip it
//    was a flat pale rectangle
//  - SPECULAR = 0 in the shaders: Godot's own Schlick term reflected the (blue) ambient light at grazing angles, a
//    navy line along the hair's outline. All the hair's sheen is the strand lobes in light().

uniform float core_threshold : hint_range(0.05, 0.95) = 0.5;
uniform float edge_fade : hint_range(0.0, 1.0) = 0.3;
// how much the per-strand brightness breaks the highlight up: ~1 a soft sheen along the strands, 2+ glitter
uniform float glint_pow : hint_range(0.5, 4.0) = 1.5;
uniform float glint_gain : hint_range(0.0, 4.0) = 1.0;
uniform float glint_max : hint_range(1.0, 3.0) = 1.6;
// the neighbourhood a strand is compared with (and the highlight's colour is taken from): a coarse mip
uniform float glint_lod : hint_range(0.0, 8.0) = 4.0;
uniform float inner_spec : hint_range(0.0, 1.0) = 0.35;
// how much of the cards' depth tone (COLOR.rgb: inner layers ~0.3) darkens them (1: as built)
uniform float depth_tone : hint_range(0.0, 1.0) = 1.0;
// The atlas darkens every strand toward its root (root colour ~0.3 of the tip's brightness over the first half of
// the strip), which is right for cards rooted at the scalp. Most of these cards start on top of other hair, so
// each would carry a dark band across its root half and a pale tip half, and overlapping cards would make a
// patchwork of light and dark rectangles. ramp_flatten evens each card toward the strip's colour at ramp_ref (a
// coarse mip, so the strands' own shading stays; near 0.3 a card keeps about the average brightness of the
// unflattened ramp, which the hair colours in cast.py are matched against); scan_root_dark keeps a little root
// shade. Depth in the hair comes from the cards' depth tone, the underlayer and the scalp cap instead.
uniform float ramp_flatten : hint_range(0.0, 1.0) = 0.85;
uniform float ramp_ref : hint_range(0.0, 1.0) = 0.28;
uniform float scan_root_dark : hint_range(0.0, 1.0) = 0.12;
// a card turned much more edge-on to the camera than the hair surface it lies in fades out (alpha x): seen edge-on,
// its strands squeeze into a coarse mip, a flat pale rectangle with the card's straight edges. At the silhouette,
// where the surface itself is edge-on, cards stay.
uniform float edge_on_lo : hint_range(0.0, 1.0) = 0.15;
uniform float edge_on_hi : hint_range(0.0, 1.0) = 0.45;
uniform float scan_spec1_exp : hint_range(4.0, 800.0) = 40.0;
uniform float scan_spec1_strength : hint_range(0.0, 3.0) = 1.0;
uniform float scan_spec2_exp : hint_range(4.0, 400.0) = 12.0;
uniform float scan_spec2_strength : hint_range(0.0, 3.0) = 0.45;
// highlight colour = spec_rel x the hair's colour + spec_abs x its hue (luminance 1)
uniform float spec_rel : hint_range(0.0, 16.0) = 2.2;
uniform float spec_abs : hint_range(0.0, 0.3) = 0.01;
// 1: the hair's own hue; > 1 saturates it (warmer, toward copper)
uniform float spec_hue_pow : hint_range(1.0, 3.0) = 1.0;
// 0: the highlight takes only the light's brightness; 1: also its colour
uniform float spec_light_tint : hint_range(0.0, 1.0) = 0.3;
// the same for the diffuse light: brown hair in the shadow of the hair above, lit by the blue fill (the sky) alone,
// comes out navy (a navy rim along the outline, navy locks under a fringe)
uniform float diffuse_light_tint : hint_range(0.0, 1.0) = 0.8;
// a card seen from behind: how much of the light falling on its other side it shows (0: none, 1: as much)
uniform float back_light : hint_range(0.0, 1.0) = 0.6;
// how far apart along the root fade the strands of one card switch on (0: all at once, a straight edge)
uniform float fade_stagger : hint_range(0.0, 0.95) = 0.7;
// 1: strand direction from the mesh tangents (smooth along a card); 0: from the UV gradient (per triangle)
uniform float tangent_mix : hint_range(0.0, 1.0) = 1.0;
// Per person (CharacterMaterials.FINISH; 0, the default, changes nothing): the ambient light (sky, GI) sees the
// albedo pushed toward the hair's own hue by ambient_warm, the direct lights see it as it is (scan_warm_albedo()
// in fragment, undone for each light in light() by v_alb_k). Light warm-toned hair in the shade, lit by the blue
// sky alone, otherwise reads as a neutral mauve-grey.
uniform float ambient_warm : hint_range(0.0, 2.0) = 0.0;
varying vec3 v_alb_k;
uniform float spec_tone : hint_range(0.0, 1.0) = 0.0;
// (per person, with spec_tone > 0; (0.05, 0.22), the default, changes nothing) the depth tones over which a card's
// highlight comes back. Root cards built only a little darker (root_tone x0.25: tone ~0.2) would keep most of the
// highlight, and dark roots would glint in the hair's lighter colour next to the part.
uniform vec2 spec_tone_range = vec2(0.05, 0.22);
// (per person, with ambient_warm > 0; 1, the default, changes nothing) the albedo the direct lights see, its
// saturation scaled (luminance kept). Light hair that takes the lights' full colour (light tints at 1, so that
// part-white light does not turn it silver-lilac) comes out copper-gold in the golden sun; the ambient keeps the
// warm hue, so the shade stays warm.
uniform float direct_sat : hint_range(0.0, 1.0) = 1.0;
// (per person, with ambient_warm > 0; white, the default, changes nothing) the albedo the direct lights see x this
// (linear), against a golden-yellow cast in the golden sun. The same tint on the albedo itself would turn the
// shaded hair mauve, so only the direct lights see it.
uniform vec3 direct_tint = vec3(1.0);
// (per person; 1, the default, changes nothing) the albedo the ambient light (sky, GI) sees, x ambient_gain; the
// direct lights see it unchanged (k, as for ambient_warm). Near-black curls take the sun and the lamps only as thin
// glints between their own shadows and read as one blue-black mass indoors; an albedo tint alone lifts them under
// char_viewer's key light but barely in the game's.
uniform float ambient_gain : hint_range(0.0, 8.0) = 1.0;
// (per person, with ambient_warm > 0; white, the default, changes nothing) the albedo the ambient light sees x this
// (linear), the direct lights' unchanged (k): hair whose tint is desaturated for the golden sun reads mauve-grey
// from behind in the shade, and this keeps the shade warm.
uniform vec3 ambient_tint = vec3(1.0);
// (per person; 0, the default, changes nothing) lock-scale shading. The cards' shading normal is the hair volume's
// (smooth over 12 mm), so a key light lights a whole region of locks as one sheet and the locks show only through
// the atlas' strands: from 1.35 m wavy hair reads as a dark rounded mass of card patches. A lock's body is the
// atlas' coverage at a coarse mip (lock_lod; at 3 a strip is 32 texels across), its wave included. lock_roll bends
// the shading normal across the card by that coverage's slope (each lock a rounded tube: its side toward the light
// lit, the other in shade), lock_gap darkens the albedo where the coverage thins (a lock's flanks, the gaps between
// locks; lock_cover: coverage from the gap to the core), lock_crest keeps the strand highlight to the lock's core
// (scattered pale patches otherwise). lock_step: the slope's half step in UV.x.
uniform float lock_roll : hint_range(0.0, 4.0) = 0.0;
uniform float lock_gap : hint_range(0.0, 1.0) = 0.0;
uniform float lock_crest : hint_range(0.0, 1.0) = 0.0;
uniform float lock_lod : hint_range(0.0, 8.0) = 3.0;
uniform vec2 lock_cover = vec2(0.1, 0.6);
uniform float lock_step : hint_range(0.0005, 0.03) = 0.006;
// (per person; 1, the default, off) the strand highlight x glint_near on hair nearer the camera than
// glint_near_dist (metres, x to y: glint_near to none; scan_glint_near). Up close under a key light (0.6-0.75 m)
// the highlights of wavy hair show as crinkled pale foil patches and zig-zag ribbons; from the 1.35 m dialogue
// camera they read as lock highlights and stay.
uniform float glint_near : hint_range(0.0, 1.0) = 1.0;
uniform vec2 glint_near_dist = vec2(0.8, 1.1);
// (per person, with ambient_warm > 0; -1, the default, off) the direct_sat a strongly coloured light sees instead:
// by the light's own saturation (1 - min/max of LIGHT_COLOR, linear) from warm_light_range.x (direct_sat) to .y
// (direct_sat_warm). A direct albedo desaturated for the golden sun (linear saturation 0.77) goes grey beside an
// orange-lit face under last light's deeper sun (0.92).
uniform float direct_sat_warm : hint_range(-1.0, 1.0) = -1.0;
uniform vec2 warm_light_range = vec2(0.8, 0.9);

const vec3 HAIR_LUM = vec3(0.2126, 0.7152, 0.0722);

varying float v_spec;
varying vec3 v_spec_col;
varying vec3 v_hue;
varying float v_back;

float scan_hash(float x) {
	return fract(sin(x * 12.9898 + 78.233) * 43758.5453);
}

// The ends of the cards. coverage_alpha() boosts alpha in coarse mips so distant hair keeps its body; in a coarse
// mip a strip's clump is a smooth blob, and boosted, its tip's contour came out as a rounded opaque lobe: long hair's
// lower edge read as a row of drips from the gameplay camera behind (Anisha). Toward a card's tip the boost fades
// out (from tip_boost_lo to tip_boost_hi of its length), and the strands end at staggered lengths (tip_stagger, a
// value noise across the card, analytic so a coarse mip cannot round it off).
// Long cards (long hair's, tip_soft_len: 15-30 cm and longer) also keep their ends out of the alpha-tested core once
// a strand is finer than a texel (lod 0.5-2.5): there the core's cut through a smooth mip was a hard-edged black lobe
// at every card's end, a row of ink drips on the sweater with detached droplets below it (a narrow tip's last
// opaque blob); taken down by tip_soften, the ends draw in the blended pass (hair_scan_fringe), the same coverage
// with a soft edge. Short hair's cards (5-10 cm) keep their crisp ends.
// The boost itself only where the mip is dense (dense_lo..dense_hi): its purpose is a clump's core thinned by
// averaging with the gaps between its strands. Sparse texels boosted (a wispy strip, a card's thinning end) came
// out as solid flat shards: a sparse brow wisp seen obliquely as a black flake over Mano's eye, long hair's sparse
// ends as opaque black drops. The mip is the one the sampler reads (anisotropic: the footprint's minor axis, or its
// major one over the anisotropy, `aniso`, the project's 16x): from the major axis alone a card seen obliquely
// close up counted as distant and was boosted.
uniform float tip_boost_lo : hint_range(0.0, 1.0) = 0.55;
uniform float tip_boost_hi : hint_range(0.0, 1.0) = 0.85;
uniform float tip_stagger : hint_range(0.0, 0.5) = 0.22;
uniform float tip_soften : hint_range(0.0, 1.0) = 0.5;
uniform vec2 tip_soft_len = vec2(0.15, 0.3);
uniform float boost_dense_lo : hint_range(0.0, 1.0) = 0.35;
uniform float boost_dense_hi : hint_range(0.0, 1.0) = 0.65;
uniform float aniso : hint_range(1.0, 16.0) = 16.0;

// the card's length (metres per unit of UV.y), from the screen derivatives of the position and the UVs
float scan_card_length(vec3 p, vec2 uv) {
	vec2 dux = dFdx(uv);
	vec2 duy = dFdy(uv);
	float det = dux.x * duy.y - dux.y * duy.x;
	if (abs(det) < 1e-14) {
		return 0.0;
	}
	return length((dFdy(p) * dux.x - dFdx(p) * duy.x) / det);
}

float scan_coverage_alpha(float a, vec2 uv, vec3 p) {
	vec2 ts = vec2(textureSize(albedo_tex, 0));
	vec2 dx = dFdx(uv * ts);
	vec2 dy = dFdy(uv * ts);
	float lx = dot(dx, dx);
	float ly = dot(dy, dy);
	float lod = log2(max(max(sqrt(min(lx, ly)), sqrt(max(lx, ly)) / aniso), 1e-4));
	float tipw = smoothstep(tip_boost_lo, tip_boost_hi, uv.y);
	float boost = mip_alpha_boost * (1.0 - tipw) * smoothstep(boost_dense_lo, boost_dense_hi, a);
	float x = uv.x * ts.x / 9.0;
	float i = floor(x);
	float f = fract(x);
	float r = mix(scan_hash(i + 31.0), scan_hash(i + 32.0), f * f * (3.0 - 2.0 * f));
	float end = 1.0 - r * tip_stagger;
	float soft = 1.0 - tip_soften * tipw * smoothstep(0.5, 2.5, lod) *
			smoothstep(tip_soft_len.x, tip_soft_len.y, scan_card_length(p, uv));
	return clamp(a * (1.0 + max(lod, 0.0) * boost), 0.0, 1.0) * soft * (1.0 - smoothstep(end - 0.12, end, uv.y));
}

float scan_root_fade(float fade, vec2 uv) {
	// a value noise across the card (the strands run along v), a few strands per step: per-strand random values
	// gave a fine dither of holes once the strands were thinner than a pixel
	float x = uv.x * float(textureSize(albedo_tex, 0).x) / 6.0;
	float i = floor(x);
	float f = fract(x);
	float r = mix(scan_hash(i), scan_hash(i + 1.0), f * f * (3.0 - 2.0 * f));
	float lo = r * fade_stagger;
	return smoothstep(lo, lo + (1.0 - fade_stagger) + 1e-3, fade);
}

vec3 scan_frontal(vec3 n, bool front_facing) {
	return front_facing ? n : -n;
}

vec3 scan_strand(vec3 p, vec3 n, vec2 uv, vec3 binormal) {
	vec3 d = strand_dir(p, n, uv);
	float l2 = dot(binormal, binormal);
	if (l2 < 1e-10) {
		return d;
	}
	vec3 b = binormal * inversesqrt(l2);
	// the tangent frame's handedness is per mesh, the UV gradient's is root -> tip: orient by it
	b *= dot(b, d) < 0.0 ? -1.0 : 1.0;
	return normalize(mix(d, b, tangent_mix));
}

// (lock_*: off by default) the lock's coverage at a coarse mip, and its profile from the gap (0) to the core (1)
float scan_lock_cov(vec2 uv) {
	return textureLod(albedo_tex, uv, lock_lod).a;
}

float scan_lock_profile(vec2 uv) {
	return smoothstep(lock_cover.x, lock_cover.y, scan_lock_cov(uv));
}

// (lock_roll > 0 only) the shading normal bent across the card (its +UV.x direction: the tangent, oriented by the
// UV gradient) by the slope of the lock's coverage per strip width (8 strips across the atlas)
vec3 scan_lock_normal(vec3 n, vec2 uv, vec3 p, vec3 tangent) {
	if (lock_roll <= 0.0) {
		return n;
	}
	float g = (scan_lock_cov(uv + vec2(lock_step, 0.0)) - scan_lock_cov(uv - vec2(lock_step, 0.0))) /
			(16.0 * lock_step);
	vec3 dp2perp = cross(dFdy(p), n);
	vec3 dp1perp = cross(n, dFdx(p));
	vec3 est = dp2perp * dFdx(uv).x + dp1perp * dFdy(uv).x;
	vec3 w = tangent - n * dot(tangent, n);
	float l2 = dot(w, w);
	if (l2 < 1e-10) {
		return n;
	}
	w *= inversesqrt(l2) * (dot(w, est) < 0.0 ? -1.0 : 1.0);
	return normalize(n - w * (lock_roll * clamp(g, -3.0, 3.0)));
}

// the highlight's colours: the hue of the person's hair (the atlas' last mip, its average: per texel, the block
// compression's colour error on near-black hair turned highlights green and orange) at the brightness of the hair
// in this strip (a coarse mip at ramp_ref, as the albedo is evened: the strands' colour, not their shade)
void scan_spec_colors(vec2 uv, out vec3 spec_col, out vec3 hue_out) {
	vec3 avg = textureLod(albedo_tex, vec2(0.5), 14.0).rgb * tint.rgb;
	float la = max(dot(avg, HAIR_LUM), 1e-5);
	vec3 hue = pow(clamp(avg / la, vec3(0.0), vec3(4.0)), vec3(spec_hue_pow));
	hue /= max(dot(hue, HAIR_LUM), 1e-5);
	float l = dot(textureLod(albedo_tex, vec2(uv.x, ramp_ref), glint_lod).rgb * tint.rgb, HAIR_LUM);
	hue_out = hue;
	spec_col = hue * (l * spec_rel + spec_abs);
}

// (glint_near < 1 only) the highlight's factor by the camera's distance (vertex: VERTEX, view space)
float scan_glint_near(vec3 vertex) {
	if (glint_near >= 1.0) {
		return 1.0;
	}
	return mix(glint_near, 1.0, smoothstep(glint_near_dist.x, glint_near_dist.y, length(vertex)));
}

float scan_glint(vec4 t, vec2 uv, vec4 col, vec3 n, vec3 view) {
	float lum = dot(t.rgb, HAIR_LUM);
	float around = dot(textureLod(albedo_tex, uv, glint_lod).rgb, HAIR_LUM);
	float rel = clamp(lum / max(around, 1e-4), 0.0, glint_max);
	// a little less shine toward a card's root (a strong ramp here lit only each card's tip half: pale chips)
	float ramp = mix(0.6, 1.0, smoothstep(0.0, 0.5, uv.y));
	float facing = smoothstep(0.0, edge_fade, abs(dot(n, view)));
	float tone = (col.r + col.g + col.b) / 3.0;
	float layer = mix(inner_spec, 1.0, smoothstep(0.3, 0.9, tone));
	// (spec_tone, per person, 0 by default) cards darkened far below any depth tone (hair_scan_cards.root_tone: dark
	// roots under lighter hair, tone ~0.03) lose their highlight, which takes its colour from the atlas, not from the
	// tone: lit by the sun, dark roots would otherwise glint in the lighter colour
	layer *= mix(1.0, smoothstep(spec_tone_range.x, spec_tone_range.y, tone), spec_tone);
	if (lock_crest > 0.0) {
		// (lock_crest, per person) the highlight kept to the lock's core
		layer *= mix(1.0, scan_lock_profile(uv), lock_crest);
	}
	return glint_gain * pow(rel * ramp, glint_pow) * pow(t.a, 1.5) * facing * layer;
}

float scan_edge_on(vec3 p, vec3 n, vec3 view) {
	vec3 fn = cross(dFdx(p), dFdy(p));
	float l2 = dot(fn, fn);
	if (l2 < 1e-20) {
		return 1.0;
	}
	float card = abs(dot(fn * inversesqrt(l2), view));
	float surf = max(abs(dot(n, view)), 0.05);
	return smoothstep(edge_on_lo, edge_on_hi, card / surf);
}

// (ambient_warm > 0 only) the albedo the ambient light sees; k (fragment() keeps it in v_alb_k) turns each light's
// diffuse back to `alb`
vec3 scan_warm_albedo(vec3 alb, vec3 hue, out vec3 k) {
	vec3 w = alb * mix(vec3(1.0), clamp(hue, vec3(0.2), vec3(3.0)), ambient_warm) * ambient_gain * ambient_tint;
	k = mix(vec3(dot(alb, HAIR_LUM)), alb, direct_sat) * direct_tint / max(w, vec3(1e-5));
	return w;
}

// (in light(), direct_sat_warm >= 0 only; else k as it is) k for this light: w is the ambient's albedo (ALBEDO in
// light()), the direct albedo taken back out of it and desaturated by direct_sat_warm as the light's colour saturates
vec3 scan_direct_k(vec3 k, vec3 w, vec3 hue, vec3 light_color) {
	if (direct_sat_warm < 0.0) {
		return k;
	}
	float mx = max(light_color.r, max(light_color.g, light_color.b));
	float s = 1.0 - min(light_color.r, min(light_color.g, light_color.b)) / max(mx, 1e-5);
	float f = smoothstep(warm_light_range.x, warm_light_range.y, s);
	vec3 alb = w / max(mix(vec3(1.0), clamp(hue, vec3(0.2), vec3(3.0)), ambient_warm) * ambient_gain * ambient_tint,
			vec3(1e-5));
	vec3 k2 = mix(vec3(dot(alb, HAIR_LUM)), alb, direct_sat_warm) * direct_tint / max(w, vec3(1e-5));
	return mix(k, k2, f);
}

vec3 scan_albedo(vec3 tex, vec4 col, vec2 uv) {
	vec3 here = textureLod(albedo_tex, uv, 5.0).rgb;
	vec3 ref = textureLod(albedo_tex, vec2(uv.x, ramp_ref), 5.0).rgb;
	vec3 k = clamp(ref / max(here, vec3(1e-4)), vec3(0.25), vec3(4.0));
	float root = mix(1.0 - scan_root_dark, 1.0, smoothstep(0.0, root_len, uv.y));
	if (lock_gap > 0.0) {
		// (lock_gap, per person) darker where the lock's coverage thins: its flanks and the gaps between locks
		root *= mix(1.0, scan_lock_profile(uv), lock_gap);
	}
	return tex * mix(vec3(1.0), k, ramp_flatten) * tint.rgb * mix(vec3(1.0), col.rgb, depth_tone) * root;
}

void scan_hair_light(vec3 strand, vec3 n, vec3 l, vec3 v, vec3 spec_col, vec3 hue, vec3 light_color,
		float attenuation, float back_face, inout vec3 diffuse_light, inout vec3 specular_light) {
	vec3 t = normalize(strand);
	float ndl = dot(n, l);
	float diff = clamp((ndl + wrap) / (1.0 + wrap), 0.0, 1.0);
	diff = max(diff, back_face * back_light * clamp((wrap - ndl) / (1.0 + wrap), 0.0, 1.0));
	vec3 lc = light_color * attenuation / PI;
	float lum = dot(lc, HAIR_LUM);
	vec3 lcs = mix(vec3(lum), lc, spec_light_tint);
	vec3 lcd = mix(vec3(lum), lc, diffuse_light_tint);
	// light through backlit hair takes the hair's colour (x ALBEDO in Godot's sum), not the light's
	float back = pow(clamp(dot(-l, v), 0.0, 1.0), 4.0) * scatter_strength;
	diffuse_light += lcd * diff + lcs * hue * back;
	vec3 h = normalize(l + v);
	float s1 = kajiya(normalize(t + n * spec1_shift), h, scan_spec1_exp);
	float s2 = kajiya(normalize(t + n * spec2_shift), h, scan_spec2_exp);
	float vis = smoothstep(-0.25, 0.35, ndl);
	specular_light += lcs * vis * spec_col * (s1 * scan_spec1_strength + hue * s2 * scan_spec2_strength);
}
