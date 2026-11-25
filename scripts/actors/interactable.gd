class_name Interactable
extends RefCounted
## Something Mano can talk to or use: an NPC or a hotspot in the level.

var id := ""
var label := ""
var kind := "spot"          # "npc" | "spot"
var range := 1.8
var pos := Vector3.ZERO
var npc: Node = null        # NPC node when kind == "npc"
var condition: Callable     # optional () -> bool


func is_available() -> bool:
	if npc != null and (not is_instance_valid(npc) or not npc.visible):
		return false
	return condition.is_null() or condition.call()


func position_for(_from: Vector3) -> Vector3:
	return npc.global_position if npc else pos


func look_point() -> Vector3:
	if npc and npc.rig:
		return npc.rig.head_position()
	return pos + Vector3.UP * 0.9


func prompt_point() -> Vector3:
	if npc and npc.rig:
		return npc.rig.head_position() + Vector3.UP * 0.32
	return pos + Vector3.UP * 1.2
