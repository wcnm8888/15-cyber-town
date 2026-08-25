extends SceneTree

const DIALOGUE_SCENE_PATH := "res://scenes/dialogue.tscn"
const DEADLINE_MILLISECONDS := 18000
const SYNTHETIC_MESSAGE := "Synthetic offline dialogue request."
const FAILURE_STATES := {
	"unavailable_recovery": &"unavailable",
	"timeout_recovery": &"timeout",
	"invalid_recovery": &"invalid_response",
	"wrong_content_type": &"invalid_response",
	"missing_content_type": &"invalid_response",
	"duplicate_content_type": &"invalid_response",
	"unexpected_status": &"invalid_response",
}

var _scenario := ""
var _scene: Control
var _client: Node
var _status_label: Label
var _reply_label: Label
var _message_input: TextEdit
var _send_button: Button
var _retry_button: Button
var _observed_states: Array[StringName] = []
var _original_payload := ""
var _retried := false
var _finished := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var arguments := OS.get_cmdline_user_args()
	var option_index := arguments.find("--scenario")
	if option_index < 0 or option_index + 1 >= arguments.size():
		_fail("offline dialogue scenario was not configured")
		return
	_scenario = arguments[option_index + 1]
	if _scenario != "success" and not FAILURE_STATES.has(_scenario):
		_fail("offline dialogue scenario is not approved")
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
	_retry_button = _scene.get_node("CenterContainer/VBoxContainer/ButtonRow/RetryButton")
	_client.state_changed.connect(_on_state_changed)

	_message_input.text = SYNTHETIC_MESSAGE
	_message_input.text_changed.emit()
	_send_button.pressed.emit()
	_original_payload = _client._frozen_payload_json
	var deadline := Time.get_ticks_msec() + DEADLINE_MILLISECONDS
	while not _finished and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _finished:
		_fail("offline dialogue exceeded its safety deadline")


func _on_state_changed(state: StringName) -> void:
	if _observed_states.is_empty() or _observed_states.back() != state:
		_observed_states.append(state)
	if state == &"loading" or state == &"retrying":
		return
	if state == &"success":
		call_deferred("_verify_success")
		return
	if not FAILURE_STATES.has(_scenario) or state != FAILURE_STATES[_scenario]:
		_fail("offline dialogue entered an unexpected state: %s" % state)
		return
	call_deferred("_handle_expected_failure")


func _handle_expected_failure() -> void:
	await process_frame
	if not _retry_button.visible or _retry_button.disabled or not _client.can_retry():
		_fail("recoverable dialogue failure did not enable manual Retry")
		return
	if _reply_label.visible or not _client.latest_reply.is_empty():
		_fail("invalid dialogue response leaked untrusted reply into the UI")
		return
	if not _scenario.ends_with("_recovery"):
		_finish()
		return
	if _retried:
		_fail("offline dialogue attempted more than one manual Retry")
		return
	_retried = true
	_retry_button.pressed.emit()
	if _client._frozen_payload_json != _original_payload:
		_fail("manual Retry changed the frozen logical request")


func _verify_success() -> void:
	await process_frame
	var expected: Array[StringName]
	if _scenario == "success":
		expected = [&"loading", &"success"]
	else:
		expected = [&"loading", FAILURE_STATES[_scenario], &"retrying", &"success"]
	if _observed_states != expected:
		_fail("offline dialogue state transition contract did not match")
		return
	if _status_label.text != "Reply received" or not _reply_label.visible:
		_fail("offline dialogue success was not rendered")
		return
	if _retry_button.visible or _send_button.disabled or _client.is_request_in_flight():
		_fail("offline dialogue did not release its in-flight controls")
		return
	if _client.latest_trace_id.is_empty():
		_fail("offline dialogue did not expose its safe trace identifier")
		return
	_finish()


func _finish() -> void:
	if _finished:
		return
	_finished = true
	print("GODOT_FAKE_DIALOGUE=PASS scenario=%s" % _scenario)
	quit(0)


func _fail(reason: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("GODOT_FAKE_DIALOGUE=FAIL scenario=%s reason=%s" % [_scenario, reason])
	quit(1)
