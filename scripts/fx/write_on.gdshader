shader_type canvas_item;
// Handwriting being written on (docs/DESIGN.md §5.4, docs/ART_DIRECTION.md): on a one-line Label, everything to the right of
// `reveal` (in the label's own canvas units) is not written yet, with a short soft edge where the ink is wet.
// Ink.write_on() tweens `reveal` across the label at the pen's speed.

uniform float reveal = 100000.0;
uniform float soft = 14.0;

varying float lx;

void vertex() {
	lx = VERTEX.x;
}

void fragment() {
	COLOR.a *= 1.0 - smoothstep(reveal - soft, reveal, lx);
}
