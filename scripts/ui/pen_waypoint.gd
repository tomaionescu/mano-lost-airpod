class_name PenWaypoint
extends Control
## The optional waypoint (Settings > Objective marker, off by default: docs/DESIGN.md §5.5): a red
## pen target that boils over the next place to go, a drawn arrow on the screen edge when that place is off
## screen or behind, and no distance (a number in metres makes it a sat-nav). It fades out within 4 m.

const SIZE := 34.0              # the target, about 41 px at 1080p
const ARROW := 54.0             # the edge arrow's box (the arrow itself is about 40 px long at 1080p)
const EDGE := Vector2(60, 66)   # how far in from the screen edges the arrow sits
const NEAR := 4.0               # metres: gone at 2 m, whole from 4 m

var _pos := Vector2.ZERO
var _alpha := 0.0
var _off := false
var _dir := 0.0
var _seen := false


func _ready() -> void:
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)   # the whole HUD: it draws at screen positions
	modulate.a = 0.0
	visible = false


## `target` (Vector3 or null) is where to go, `from` (Vector3 or null) where Mano is.
func tick(dt: float, show: bool, camera: Camera3D, target, from) -> void:
	var want := 0.0
	if show and target != null and camera != null:
		var wp: Vector3 = target
		var vp := size
		var center := vp * 0.5
		var behind := camera.is_position_behind(wp)
		var sp := camera.unproject_position(wp)
		if behind:
			# behind the camera: the arrow goes on the side to turn to, at mid height (the bottom edge is Mano's)
			var local := camera.global_transform.affine_inverse() * wp
			sp = center + Vector2(signf(local.x) if absf(local.x) > 0.01 else 1.0, 0.25) * vp.length()
		var off := sp - center
		var lim := center - EDGE
		var k := maxf(absf(off.x) / lim.x, absf(off.y) / lim.y)
		_off = behind or k > 1.0
		if k > 1.0:
			sp = center + off / k
		_dir = off.angle()
		_pos = sp if not _seen else _pos.lerp(sp, 1.0 - exp(-dt * 14.0))
		_seen = true
		want = 1.0
		if from != null:
			var d := (from as Vector3).distance_to(wp)
			want = clampf((d - NEAR * 0.5) / (NEAR * 0.5), 0.0, 1.0)
	else:
		_seen = false
	_alpha = move_toward(_alpha, want * (0.9 if _off else 1.0), dt / 0.25)
	modulate.a = _alpha
	visible = _alpha > 0.002
	if visible:
		queue_redraw()


## Red pen over a pale halo and a soft ink shadow, so the mark reads over a bright sky and in the night alike.
func _draw() -> void:
	var id := "arrow" if _off else "target"
	var s := ARROW if _off else SIZE
	var w := 2.8 if _off else 2.2
	var r := Rect2(_pos - Vector2(s, s) * 0.5, Vector2(s, s))
	var f := Doodles.boil()
	Doodles.draw(self, id, r, Color(UITheme.INK_SHADOW, 0.35), w + 4.0, f, Color(0, 0, 0, 0), 1.0, _dir if _off else 0.0)
	Doodles.draw(self, id, r, Color(UITheme.FILM_WHITE, 0.85), w + 2.0, f, Color(0, 0, 0, 0), 1.0, _dir if _off else 0.0)
	Doodles.draw(self, id, r, UITheme.MARKER_RED, w, f, Color(0, 0, 0, 0), 1.0, _dir if _off else 0.0)
