extends SceneTree

const MAIN_SCENE_PATH := "res://scenes/backend_status.tscn"

const EXPECTED_STATES := {
	"connected": [&"connecting", &"connected"],
	"unavailable": [&"connecting", &"unavailable"],
	"duplicate_rejected": [&"connecting", &"unavailable"],
	"non_string_rejected": [&"connecting", &"unavailable"],
	"redirect_rejected": [&"connecting", &"unavailable"],
	"stopped_service": [],
	"http_error_recovery": [&"connecting", &"unavailable", &"retry", &"connected"],
	"invalid_recovery": [&"connecting", &"unavailable", &"retry", &"connected"],
	"timeout_recovery": [&"connecting", &"timeout", &"retry", &"connected"],
}

const STATE_MESSAGES := {
	&"connecting": "Connecting to backend…",
	&"connected": "Backend connected",
	&"timeout": "Connection timed out",
	&"unavailable": "Backend unavailable",
	&"retry": "Retrying connection…",
}

var _scenario := ""
var _observed_states: Array[StringName] = []
var _scene: Control
var _client: Node
var _status_label: Label
var _retry_button: Button
var _retry_requested := false
var _finished := false


func _init() -> void:
	_scenario = _read_scenario(OS.get_cmdline_user_args())
	call_deferred("_run")


func _run() -> void:
	if not EXPECTED_STATES.has(_scenario):
		_fail("unknown or missing --scenario value: %s" % _scenario)
		return

	var packed_scene: PackedScene = load(MAIN_SCENE_PATH)
	if packed_scene == null:
		_fail("main scene could not be loaded")
		return

	_scene = packed_scene.instantiate()
	_client = _scene.get_node("BackendHealthClient")
	_status_label = _scene.get_node("CenterContainer/VBoxContainer/StatusLabel")
	_retry_button = _scene.get_node("CenterContainer/VBoxContainer/RetryButton")
	_client.state_changed.connect(_on_state_changed)
	root.add_child(_scene)

	var deadline := Time.get_ticks_msec() + 15000
	while not _finished and Time.get_ticks_msec() < deadline:
		await process_frame

	if not _finished:
		_fail(
			"scenario exceeded 15-second safety deadline (observed=%s)"
			% [_observed_states]
		)


func _on_state_changed(state: StringName) -> void:
	if _observed_states.is_empty() or _observed_states.back() != state:
		_observed_states.append(state)

	if state == &"timeout" or state == &"unavailable":
		if _scenario.ends_with("_recovery") and not _retry_requested:
			_retry_requested = true
			call_deferred("_request_retry_after_render", state)
			return

	if state == &"connected" or (
		state == &"unavailable"
		and _scenario in [
			"unavailable",
			"duplicate_rejected",
			"non_string_rejected",
			"redirect_rejected",
		]
	) or (
		_scenario == "stopped_service"
		and (state == &"timeout" or state == &"unavailable")
	):
		call_deferred("_verify_and_finish", state)


func _request_retry_after_render(failure_state: StringName) -> void:
	await process_frame
	if not _verify_ui(failure_state):
		return
	if not _retry_button.visible or _retry_button.disabled:
		_fail("Retry must be visible and enabled after %s" % failure_state)
		return
	_retry_button.pressed.emit()


func _verify_and_finish(final_state: StringName) -> void:
	await process_frame
	if not _verify_ui(final_state):
		return

	var expected: Array = EXPECTED_STATES[_scenario]
	var sequence_matches := _observed_states == expected
	if _scenario == "stopped_service":
		sequence_matches = (
			_observed_states.size() == 2
			and _observed_states[0] == &"connecting"
			and (
				_observed_states[1] == &"timeout"
				or _observed_states[1] == &"unavailable"
			)
		)
		expected = [&"connecting", &"timeout|unavailable"]
	if not sequence_matches:
		_fail(
			"state sequence mismatch (expected=%s, actual=%s)"
			% [expected, _observed_states]
		)
		return

	_finished = true
	print("Godot integration scenario passed: %s -> %s" % [_scenario, _observed_states])
	quit(0)


func _verify_ui(state: StringName) -> bool:
	var expected_message: String = STATE_MESSAGES[state]
	if _status_label.text != expected_message:
		_fail(
			"status text mismatch for %s (expected=%s, actual=%s)"
			% [state, expected_message, _status_label.text]
		)
		return false

	var should_offer_retry := state == &"timeout" or state == &"unavailable"
	if should_offer_retry:
		if not _retry_button.visible or _retry_button.disabled:
			_fail("Retry policy mismatch for %s" % state)
			return false
	elif state == &"connected" and _retry_button.visible:
		_fail("Retry must be hidden after connection succeeds")
		return false

	return true


func _read_scenario(arguments: PackedStringArray) -> String:
	for index in range(arguments.size() - 1):
		if arguments[index] == "--scenario":
			return arguments[index + 1]
	return ""


func _fail(message: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("Godot integration scenario failed (%s): %s" % [_scenario, message])
	quit(1)
