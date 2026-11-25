extends Node

var watched: Node
var bridge: Node
var rebuilding := false

func _ready() -> void:
	get_tree().scene_changed.connect(_attach)
	get_tree().node_added.connect(_topology_changed)
	get_tree().node_removed.connect(_topology_changed)

func _attach() -> void:
	var tree := get_tree()
	if not ClassDB.class_exists(&"ThreeGatewayBridge"):
		push_error("ThreeGatewayBridge is missing. Run the gateway installer for this platform.")
		tree.quit(1)
		return
	watched = tree.current_scene
	if watched == null: return
	bridge = ClassDB.instantiate(&"ThreeGatewayBridge") as Node
	bridge.name = "ThreeGatewayBridge"
	watched.add_child(bridge)

func _topology_changed(node: Node) -> void:
	if rebuilding or not is_instance_valid(bridge) or not is_instance_valid(watched):
		return
	if not (node is MeshInstance3D or node is Light3D or node is WorldEnvironment or node is Skeleton3D or node.scene_file_path.ends_with(".glb")):
		return
	if watched != get_tree().current_scene or not watched.is_ancestor_of(node):
		return
	bridge.set_process(false)
	rebuilding = true
	_refresh.call_deferred(watched.get_instance_id())

func _refresh(scene_id: int) -> void:
	rebuilding = false
	if not is_instance_valid(watched) or watched.get_instance_id() != scene_id or get_tree().current_scene != watched:
		return
	if is_instance_valid(bridge): bridge.free()
	_attach()
