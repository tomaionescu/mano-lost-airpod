class_name DieCut
extends RefCounted
## A die-cut sticker round any picture with transparency (docs/DESIGN.md §5.5, docs/ART_DIRECTION.md; the title
## logo is one): the picture's silhouette grown into white
## vinyl, with a soft shadow under it. The vinyl is baked once on the CPU, at a quarter of the picture's
## resolution (a chamfer distance transform; drawn back up with linear filtering it stays smooth), so drawing a
## sticker costs three quads a frame.

var art: Texture2D
var vinyl: Texture2D
var pad := 0          # transparent margin round the art, in its pixels (room for the border)
var art_px := Vector2.ZERO   # the picture's own size in pixels, without the margin


## `src` with a vinyl border `border_px` of its pixels wide.
static func bake(src: Image, border_px: float, quality := 4) -> DieCut:
	var d := DieCut.new()
	var pic := src.duplicate() as Image
	pic.convert(Image.FORMAT_RGBA8)
	d.pad = int(ceil(border_px + 10.0))
	d.art_px = Vector2(pic.get_width(), pic.get_height())
	var img := Image.create(pic.get_width() + d.pad * 2, pic.get_height() + d.pad * 2, false, Image.FORMAT_RGBA8)
	img.fill(Color(0, 0, 0, 0))
	img.blit_rect(pic, Rect2i(Vector2i.ZERO, pic.get_size()), Vector2i(d.pad, d.pad))
	var w := maxi(img.get_width() / quality, 1)
	var h := maxi(img.get_height() / quality, 1)
	var small := img.duplicate() as Image
	small.resize(w, h, Image.INTERPOLATE_BILINEAR)
	const FAR := 1e6
	var dist := PackedFloat32Array()
	dist.resize(w * h)
	for y in h:
		for x in w:
			dist[y * w + x] = 0.0 if small.get_pixel(x, y).a > 0.3 else FAR
	# two passes of a 3x3 chamfer: distance (in small pixels) to the nearest inked pixel
	for y in h:
		for x in w:
			var i := y * w + x
			var v := dist[i]
			if x > 0:
				v = minf(v, dist[i - 1] + 1.0)
			if y > 0:
				v = minf(v, dist[i - w] + 1.0)
				if x > 0:
					v = minf(v, dist[i - w - 1] + 1.414)
				if x < w - 1:
					v = minf(v, dist[i - w + 1] + 1.414)
			dist[i] = v
	for y in range(h - 1, -1, -1):
		for x in range(w - 1, -1, -1):
			var i := y * w + x
			var v := dist[i]
			if x < w - 1:
				v = minf(v, dist[i + 1] + 1.0)
			if y < h - 1:
				v = minf(v, dist[i + w] + 1.0)
				if x < w - 1:
					v = minf(v, dist[i + w + 1] + 1.414)
				if x > 0:
					v = minf(v, dist[i + w - 1] + 1.414)
			dist[i] = v
	var r := border_px / quality
	var mask := Image.create(w, h, false, Image.FORMAT_LA8)
	for y in h:
		for x in w:
			mask.set_pixel(x, y, Color(1, 1, 1, clampf(r - dist[y * w + x] + 0.5, 0.0, 1.0)))
	d.vinyl = ImageTexture.create_from_image(mask)
	d.art = ImageTexture.create_from_image(img)
	return d


## Draws the sticker with the picture itself filling `rect` (the vinyl spills past it), its shadow `shadow`
## units down and right.
func draw(ci: CanvasItem, rect: Rect2, shadow := Vector2(3, 5), shadow_alpha := 0.3, vinyl_color := Color(1, 1, 0.99)) -> void:
	if art == null or art_px.x <= 0.0:
		return
	var k := rect.size.x / art_px.x
	var full := Rect2(rect.position - Vector2(pad, pad) * k, (art_px + Vector2(pad, pad) * 2.0) * k)
	ci.draw_texture_rect(vinyl, Rect2(full.position + shadow, full.size), false, Color(UITheme.INK_SHADOW, shadow_alpha))
	ci.draw_texture_rect(vinyl, full, false, vinyl_color)
	ci.draw_texture_rect(art, full, false)
