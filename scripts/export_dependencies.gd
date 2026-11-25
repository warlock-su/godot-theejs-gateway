extends SceneTree

# Runs during packaging so the browser receives only GLBs reachable from the chosen scenes.
func _initialize() -> void:
	var args := OS.get_cmdline_user_args()
	var roots := PackedStringArray()
	for i in range(1,args.size()):
		roots.append(args[i])
	if roots.is_empty() or roots[0].is_empty():
		var main := str(ProjectSettings.get_setting("application/run/main_scene",""))
		if roots.is_empty(): roots.append("")
		roots[0] = main if not main.is_empty() else "res://addons/three_gateway/demo.tscn"
	var queue: Array[String] = []
	for i in roots.size():
		roots[i] = _path(roots[i])
		queue.append(roots[i])
	for key in ProjectSettings.get_property_list():
		if str(key.name).begins_with("autoload/"):
			queue.append(_path(str(ProjectSettings.get_setting(key.name)).trim_prefix("*")))
	var seen := {}
	var models := PackedStringArray()
	while not queue.is_empty():
		var file: String = queue.pop_back()
		if seen.has(file):
			continue
		if not ResourceLoader.exists(file):
			push_error("Missing dependency: " + file)
			quit(1)
			return
		seen[file] = true
		if file.get_extension().to_lower() == "glb":
			models.append(file)
		for item in ResourceLoader.get_dependencies(file):
			var parts := item.split("::")
			var path := _path(parts[0])
			if not path.begins_with("res://") and parts.size()>1:
				path = parts[-1]
			if path.begins_with("res://"):
				queue.append(path)
	var out := FileAccess.open(args[0],FileAccess.WRITE)
	if out == null:
		quit(2)
		return
	out.store_string(JSON.stringify({"roots":roots,"models":models}))
	out.close()
	# This script runs only in the packager's disposable copy.
	ProjectSettings.set_setting("application/run/main_scene", "res://addons/three_gateway/runner.tscn")
	ProjectSettings.set_setting("rendering/renderer/rendering_method", "gl_compatibility")
	if ProjectSettings.save() != OK:
		quit(1)
		return
	quit()

func _path(id: String) -> String:
	if id.begins_with("uid://"):
		var uid := ResourceUID.text_to_id(id)
		if ResourceUID.has_id(uid): return ResourceUID.get_id_path(uid)
	return id
