extends CharacterBody3D

func _ready() -> void:
	# Physical keys let the same demo run in the native editor.
	var keys := {"left": KEY_A, "right": KEY_D, "forward": KEY_W, "back": KEY_S, "jump": KEY_SPACE}
	for suffix in keys:
		var action := StringName("gateway_" + suffix)
		if not InputMap.has_action(action):
			InputMap.add_action(action)
		if InputMap.action_get_events(action).is_empty():
			var event := InputEventKey.new()
			event.physical_keycode = keys[suffix]
			InputMap.action_add_event(action, event)

func _physics_process(delta: float) -> void:
	var move := Input.get_vector("gateway_left", "gateway_right", "gateway_forward", "gateway_back")
	velocity.x = 3.0 * move.x
	velocity.z = 3.0 * move.y
	if is_on_floor() and Input.is_action_just_pressed("gateway_jump"):
		velocity.y = 4.5
	else:
		velocity.y -= 12.0 * delta
	move_and_slide()
