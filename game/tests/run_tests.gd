extends SceneTree

const STATE_SCRIPT_PATH := "res://scripts/backend_health_state.gd"
const CLIENT_SCRIPT_PATH := "res://scripts/backend_health_client.gd"
const UI_SCRIPT_PATH := "res://scripts/backend_status_ui.gd"
const MAIN_SCENE_PATH := "res://scenes/backend_status.tscn"

const EXPECTED_HEALTH := {
	"status": "ok",
	"service": "cyber-town-backend",
	"api_version": "v1",
}

var _failures: Array[String] = []


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_test_required_resources_exist()
	if not _failures.is_empty():
		_finish()
		return

	var state_script: Script = load(STATE_SCRIPT_PATH)
	var client_script: Script = load(CLIENT_SCRIPT_PATH)

	_test_five_state_messages(state_script)
	_test_strict_response_mapping(state_script)
	_test_timeout_and_transport_mapping(state_script)
	_test_single_in_flight_and_retry_state(client_script)
	_test_main_scene_contract()
	_finish()


func _test_required_resources_exist() -> void:
	for path in [STATE_SCRIPT_PATH, CLIENT_SCRIPT_PATH, UI_SCRIPT_PATH, MAIN_SCENE_PATH]:
		_assert_true(ResourceLoader.exists(path), "required resource exists: %s" % path)


func _test_five_state_messages(state_script: Script) -> void:
	var state_model: RefCounted = state_script.new()
	var expected_messages := {
		&"connecting": ["Connecting to backend…", true, false],
		&"connected": ["Backend connected", false, false],
		&"timeout": ["Connection timed out", true, true],
		&"unavailable": ["Backend unavailable", true, true],
		&"retry": ["Retrying connection…", true, false],
	}

	for state: StringName in expected_messages:
		var expected: Array = expected_messages[state]
		_assert_equal(
			state_model.message_for(state),
			expected[0],
			"message for %s" % state,
		)
		_assert_equal(
			state_model.is_retry_visible(state),
			expected[1],
			"retry visibility for %s" % state,
		)
		_assert_equal(
			state_model.is_retry_enabled(state),
			expected[2],
			"retry enabled policy for %s" % state,
		)


func _test_strict_response_mapping(state_script: Script) -> void:
	var state_model: RefCounted = state_script.new()
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			JSON.stringify(EXPECTED_HEALTH).to_utf8_buffer(),
		),
		&"connected",
		"exact health response connects",
	)
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			503,
			JSON.stringify(EXPECTED_HEALTH).to_utf8_buffer(),
		),
		&"unavailable",
		"non-2xx response is unavailable",
	)
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			PackedByteArray(),
		),
		&"unavailable",
		"empty response is unavailable",
	)
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			"not-json".to_utf8_buffer(),
		),
		&"unavailable",
		"invalid JSON is unavailable",
	)

	var missing_field := EXPECTED_HEALTH.duplicate()
	missing_field.erase("api_version")
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			JSON.stringify(missing_field).to_utf8_buffer(),
		),
		&"unavailable",
		"missing field is unavailable",
	)

	var extra_field := EXPECTED_HEALTH.duplicate()
	extra_field["extra"] = "not-allowed"
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			JSON.stringify(extra_field).to_utf8_buffer(),
		),
		&"unavailable",
		"extra field is unavailable",
	)

	var wrong_value := EXPECTED_HEALTH.duplicate()
	wrong_value["status"] = "degraded"
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			JSON.stringify(wrong_value).to_utf8_buffer(),
		),
		&"unavailable",
		"wrong fixed value is unavailable",
	)
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			(
				'{"status":"not-ok","status":"ok",'
				+ '"service":"cyber-town-backend","api_version":"v1"}'
			).to_utf8_buffer(),
		),
		&"unavailable",
		"conflicting duplicate key is unavailable",
	)

	var invalid_field_values: Array[Variant] = [{"nested": "value"}, ["value"], null, 1, true]
	for invalid_value: Variant in invalid_field_values:
		var invalid_type := EXPECTED_HEALTH.duplicate()
		invalid_type["service"] = invalid_value
		_assert_equal(
			state_model.state_for_response(
				HTTPRequest.RESULT_SUCCESS,
				200,
				JSON.stringify(invalid_type).to_utf8_buffer(),
			),
			&"unavailable",
			"non-string health field is unavailable (type=%s)" % typeof(invalid_value),
		)


func _test_timeout_and_transport_mapping(state_script: Script) -> void:
	var state_model: RefCounted = state_script.new()
	_assert_equal(
		state_model.state_for_response(HTTPRequest.RESULT_TIMEOUT, 0, PackedByteArray()),
		&"timeout",
		"timeout result maps to timeout",
	)
	_assert_equal(
		state_model.state_for_response(
			HTTPRequest.RESULT_CONNECTION_ERROR,
			0,
			PackedByteArray(),
		),
		&"unavailable",
		"transport failure maps to unavailable",
	)


func _test_single_in_flight_and_retry_state(client_script: Script) -> void:
	var client: Node = client_script.new()
	var dispatches := {"count": 0}
	client.set_request_sender_for_testing(func(_url: String) -> int:
		dispatches["count"] += 1
		return OK
	)

	_assert_true(client.begin_check(false), "initial request starts")
	_assert_equal(client.state, &"connecting", "initial request uses connecting state")
	_assert_true(client.is_request_in_flight(), "request is marked in flight")
	_assert_false(client.begin_check(true), "second in-flight request is rejected")
	_assert_equal(dispatches["count"], 1, "only one request is dispatched")

	client.handle_response(HTTPRequest.RESULT_TIMEOUT, 0, PackedByteArray())
	_assert_equal(client.state, &"timeout", "synthetic timeout completes request")
	_assert_false(client.is_request_in_flight(), "timeout clears in-flight state")

	_assert_true(client.begin_check(true), "manual retry starts after failure")
	_assert_equal(client.state, &"retry", "manual retry uses retry state")
	client.handle_response(
		HTTPRequest.RESULT_SUCCESS,
		200,
		JSON.stringify(EXPECTED_HEALTH).to_utf8_buffer(),
	)
	_assert_equal(client.state, &"connected", "successful retry connects")
	client.free()


func _test_main_scene_contract() -> void:
	_assert_equal(
		ProjectSettings.get_setting("application/run/main_scene"),
		MAIN_SCENE_PATH,
		"project uses the diagnostic scene as main scene",
	)
	var packed_scene: PackedScene = load(MAIN_SCENE_PATH)
	_assert_true(packed_scene != null, "main scene loads")
	if packed_scene == null:
		return

	var scene: Node = packed_scene.instantiate()
	_assert_true(scene is Control, "main scene root is Control")
	_assert_true(scene.has_node("CenterContainer/VBoxContainer/TitleLabel"), "title exists")
	_assert_true(scene.has_node("CenterContainer/VBoxContainer/StatusLabel"), "status exists")
	_assert_true(scene.has_node("CenterContainer/VBoxContainer/RetryButton"), "retry exists")
	_assert_true(scene.has_node("BackendHealthClient/HTTPRequest"), "HTTPRequest exists")

	var title: Label = scene.get_node("CenterContainer/VBoxContainer/TitleLabel")
	var status: Label = scene.get_node("CenterContainer/VBoxContainer/StatusLabel")
	var retry: Button = scene.get_node("CenterContainer/VBoxContainer/RetryButton")
	var client: Node = scene.get_node("BackendHealthClient")
	_assert_equal(title.text, "Cyber Town Backend", "title text is frozen")
	_assert_equal(status.text, "Connecting to backend…", "initial status text is frozen")
	_assert_equal(retry.text, "Retry", "retry button text is frozen")
	_assert_true(retry.disabled, "retry starts disabled")
	_assert_equal(client.health_url, "http://127.0.0.1:8000/api/v1/health", "health URL")
	_assert_equal(client.timeout_seconds, 3.0, "request timeout")
	scene.free()


func _assert_true(value: bool, label: String) -> void:
	if not value:
		_failures.append(label)


func _assert_false(value: bool, label: String) -> void:
	_assert_true(not value, label)


func _assert_equal(actual: Variant, expected: Variant, label: String) -> void:
	if actual != expected:
		_failures.append("%s (expected=%s, actual=%s)" % [label, expected, actual])


func _finish() -> void:
	if _failures.is_empty():
		print("Godot connectivity tests passed")
		quit(0)
		return

	for failure in _failures:
		printerr("FAIL: %s" % failure)
	printerr("Godot connectivity tests failed: %d" % _failures.size())
	quit(1)
