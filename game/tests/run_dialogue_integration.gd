extends SceneTree

const DIALOGUE_SCENE_PATH := "res://scenes/dialogue.tscn"
const MESSAGE_ENVIRONMENT_VARIABLE := "CYBER_TOWN_DIALOGUE_EVAL_MESSAGE"
const DEADLINE_MILLISECONDS := 18000

var _scene: Control
var _client: Node
var _status_label: Label
var _reply_label: Label
var _message_input: TextEdit
var _send_button: Button
var _trace_label: Label
var _observed_states: Array[StringName] = []
var _finished := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var message := OS.get_environment(MESSAGE_ENVIRONMENT_VARIABLE)
	if message.strip_edges().is_empty():
		_fail("evaluation message was not configured")
		return

	var packed_scene: PackedScene = load(DIALOGUE_SCENE_PATH)
	if packed_scene == null:
		_fail("dialogue scene could not be loaded")
		return

	_scene = packed_scene.instantiate()
	root.add_child(_scene)
	_client = _scene.get_node("DialogueClient")
	_status_label = _scene.get_node("CenterContainer/VBoxContainer/StatusLabel")
	_reply_label = _scene.get_node("CenterContainer/VBoxContainer/ReplyLabel")
	_message_input = _scene.get_node("CenterContainer/VBoxContainer/MessageInput")
	_send_button = _scene.get_node("CenterContainer/VBoxContainer/ButtonRow/SendButton")
	_trace_label = _scene.get_node("CenterContainer/VBoxContainer/TraceLabel")
	_client.state_changed.connect(_on_state_changed)

	_message_input.text = message
	_message_input.text_changed.emit()
	_send_button.pressed.emit()

	var deadline := Time.get_ticks_msec() + DEADLINE_MILLISECONDS
	while not _finished and Time.get_ticks_msec() < deadline:
		await process_frame

	if not _finished:
		_fail("dialogue exceeded its safety deadline")


func _on_state_changed(state: StringName) -> void:
	if _observed_states.is_empty() or _observed_states.back() != state:
		_observed_states.append(state)

	if state == &"success":
		call_deferred("_verify_success")
	elif state != &"loading":
		_fail("dialogue ended in a non-success state: %s" % state)


func _verify_success() -> void:
	await process_frame
	if _observed_states != [&"loading", &"success"]:
		_fail("dialogue state sequence was not loading then success")
		return
	if _status_label.text != "Reply received":
		_fail("dialogue success status was not rendered")
		return
	if not _reply_label.visible or _reply_label.text.is_empty():
		_fail("dialogue reply was not rendered")
		return
	if not _trace_label.visible or _client.latest_trace_id.is_empty():
		_fail("dialogue trace was not rendered")
		return
	if _client.is_request_in_flight() or _send_button.disabled:
		_fail("dialogue did not leave the loading state")
		return
	var identity_matches := (
		_reply_label.text.to_lower().contains("nia") or _reply_label.text.contains("妮娅")
	)
	if not identity_matches:
		_fail("dialogue reply did not preserve the approved NPC identity")
		return

	_finished = true
	print(
		(
			"GODOT_DIALOGUE_E2E=PASS states=loading,success reply_chars=%d "
			+ "trace_present=true identity_matches=true"
		)
		% _reply_label.text.length()
	)
	quit(0)


func _fail(reason: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("GODOT_DIALOGUE_E2E=FAIL reason=%s" % reason)
	quit(1)
