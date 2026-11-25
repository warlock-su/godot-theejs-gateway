extends Node

const DEMO := "res://addons/three_gateway/demo.tscn"

func _ready() -> void:
	var target := str(ProjectSettings.get_setting("application/run/main_scene", ""))
	for argument in OS.get_cmdline_user_args():
		if argument.begins_with("--gateway-scene="):
			target = argument.trim_prefix("--gateway-scene=")
	if target.is_empty():
		target = DEMO
	var tree := get_tree()
	if target == scene_file_path or not ResourceLoader.exists(target):
		push_error("Choose a game scene for Three Gateway: " + target)
		tree.quit(1)
		return
	for action in ["left", "right", "forward", "back", "jump"]:
		var name_from_settings := StringName(ProjectSettings.get_setting("three_gateway/actions/" + action, "gateway_" + action))
		if not InputMap.has_action(name_from_settings):
			InputMap.add_action(name_from_settings)
	# A persistent listener attaches the bridge after the actual game becomes current_scene.
	var listener := preload("res://addons/three_gateway/listener.gd").new()
	tree.root.add_child.call_deferred(listener)
	tree.change_scene_to_file.call_deferred(target)
