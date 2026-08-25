extends RefCounted

const STATE_SCRIPT_PATH := "res://scripts/dialogue/dialogue_state.gd"
const CLIENT_SCRIPT_PATH := "res://scripts/dialogue/dialogue_client.gd"
const UI_SCRIPT_PATH := "res://scripts/dialogue/dialogue_ui.gd"
const SCENE_PATH := "res://scenes/dialogue.tscn"

const REQUEST_ID := "11111111-1111-4111-8111-111111111111"
const CONVERSATION_ID := "22222222-2222-4222-8222-222222222222"
const TRACE_ID := "33333333-3333-4333-8333-333333333333"
const VALID_SUCCESS := {
	"request_id": REQUEST_ID,
	"trace_id": TRACE_ID,
	"npc_id": "neon_guide",
	"conversation_id": CONVERSATION_ID,
	"reply": "The east arcade stays quiet after midnight.",
	"status": "completed",
	"provider": "fake",
}

var _failures: Array[String] = []
var _root: Window


func run(root: Window) -> Array[String]:
	_root = root
	for path in [STATE_SCRIPT_PATH, CLIENT_SCRIPT_PATH, UI_SCRIPT_PATH, SCENE_PATH]:
		_assert_true(ResourceLoader.exists(path), "dialogue resource exists: %s" % path)
	if not _failures.is_empty():
		return _failures

	var state_script: Script = load(STATE_SCRIPT_PATH)
	var client_script: Script = load(CLIENT_SCRIPT_PATH)
	_test_frozen_state_messages(state_script)
	_test_strict_success_response(state_script)
	_test_invalid_success_responses(state_script)
	_test_strict_http_response_metadata(state_script, client_script)
	_test_public_error_mapping(state_script)
	_test_transport_failures(state_script)
	_test_input_validation(client_script)
	_test_single_inflight_and_manual_retry(client_script)
	_test_late_callback_cannot_override_new_generation(client_script)
	_test_editing_message_invalidates_retry_context(client_script)
	_test_scene_contract()
	if _failures.is_empty():
		print("Godot dialogue tests passed")
	return _failures


func _test_frozen_state_messages(state_script: Script) -> void:
	var model: RefCounted = state_script.new()
	var expected := {
		&"idle": "Send a message to Nia",
		&"loading": "Nia is thinking…",
		&"success": "Reply received",
		&"timeout": "Dialogue request timed out",
		&"unavailable": "Dialogue service unavailable",
		&"invalid_response": "Invalid dialogue response",
		&"unsafe": "That message could not be processed",
		&"validation": "Enter 1–1000 characters",
		&"retrying": "Retrying dialogue…",
	}
	for state: StringName in expected:
		_assert_equal(model.message_for(state), expected[state], "dialogue message: %s" % state)


func _test_strict_success_response(state_script: Script) -> void:
	var model: RefCounted = state_script.new()
	var outcome: Dictionary = _response(model, 200, VALID_SUCCESS)
	_assert_equal(outcome["state"], &"success", "exact v1 success response")
	_assert_equal(outcome["reply"], VALID_SUCCESS["reply"], "validated reply is retained")
	_assert_equal(outcome["trace_id"], TRACE_ID, "validated trace is retained")
	_assert_false(outcome["retryable"], "success cannot be retried")

	var degraded := VALID_SUCCESS.duplicate()
	degraded["status"] = "degraded"
	degraded["provider"] = "local-fallback"
	_assert_equal(_response(model, 200, degraded)["state"], &"success", "degraded success")


func _test_invalid_success_responses(state_script: Script) -> void:
	var model: RefCounted = state_script.new()
	var invalid_payloads: Array[Dictionary] = []

	var missing := VALID_SUCCESS.duplicate()
	missing.erase("reply")
	invalid_payloads.append(missing)
	var extra := VALID_SUCCESS.duplicate()
	extra["extra"] = "not-allowed"
	invalid_payloads.append(extra)

	for invalid_value: Variant in [{"nested": true}, ["value"], null, 123, true]:
		var wrong_type := VALID_SUCCESS.duplicate()
		wrong_type["reply"] = invalid_value
		invalid_payloads.append(wrong_type)

	for invalid_entry: Array in [
		["request_id", "44444444-4444-4444-8444-444444444444"],
		["conversation_id", "55555555-5555-4555-8555-555555555555"],
		["trace_id", "invalid-uuid"],
		["npc_id", "different_npc"],
		["reply", ""],
		["reply", "x".repeat(4001)],
		["status", "unexpected"],
		["provider", ""],
	]:
		var wrong_value := VALID_SUCCESS.duplicate()
		wrong_value[invalid_entry[0]] = invalid_entry[1]
		invalid_payloads.append(wrong_value)

	for payload: Dictionary in invalid_payloads:
		_assert_equal(
			_response(model, 200, payload)["state"],
			&"invalid_response",
			"invalid success payload fails closed: %s" % str(payload.keys()),
		)

	for invalid_body: PackedByteArray in [PackedByteArray(), "not-json".to_utf8_buffer()]:
		var outcome: Dictionary = model.result_for_response(
			HTTPRequest.RESULT_SUCCESS,
			200,
			invalid_body,
			REQUEST_ID,
			CONVERSATION_ID,
			"neon_guide",
		)
		_assert_equal(outcome["state"], &"invalid_response", "invalid response body")

	var duplicate_text := JSON.stringify(VALID_SUCCESS).trim_suffix("}")
	duplicate_text += ',"reply":"replacement"}'
	var duplicate: Dictionary = model.result_for_response(
		HTTPRequest.RESULT_SUCCESS,
		200,
		duplicate_text.to_utf8_buffer(),
		REQUEST_ID,
		CONVERSATION_ID,
		"neon_guide",
	)
	_assert_equal(duplicate["state"], &"invalid_response", "duplicate JSON field rejected")


func _test_public_error_mapping(state_script: Script) -> void:
	var model: RefCounted = state_script.new()
	for expected: Array in [
		[400, "unsafe_content", false, &"unsafe"],
		[404, "npc_not_found", false, &"unavailable"],
		[409, "conflict", false, &"unavailable"],
		[422, "validation_error", false, &"validation"],
		[500, "internal_error", false, &"unavailable"],
		[502, "provider_unavailable", true, &"invalid_response"],
		[503, "provider_unavailable", true, &"unavailable"],
		[504, "provider_timeout", true, &"timeout"],
	]:
		var payload := {
			"trace_id": TRACE_ID,
			"code": expected[1],
			"message": "Safe public message.",
			"retryable": expected[2],
		}
		var outcome: Dictionary = _response(model, expected[0], payload)
		_assert_equal(outcome["state"], expected[3], "HTTP %s public mapping" % expected[0])
		_assert_equal(outcome["retryable"], expected[2], "HTTP %s retry policy" % expected[0])

	var mismatched := {
		"trace_id": TRACE_ID,
		"code": "provider_timeout",
		"message": "Safe public message.",
		"retryable": true,
	}
	_assert_equal(
		_response(model, 503, mismatched)["state"],
		&"invalid_response",
		"status/code mismatch fails closed",
	)

	for invalid_value: Variant in [{"nested": true}, ["value"], null, 1, "true"]:
		var invalid_error := {
			"trace_id": TRACE_ID,
			"code": "provider_unavailable",
			"message": "Safe public message.",
			"retryable": invalid_value,
		}
		_assert_equal(
			_response(model, 503, invalid_error)["state"],
			&"invalid_response",
			"non-boolean error retryable is rejected",
		)


func _test_strict_http_response_metadata(state_script: Script, client_script: Script) -> void:
	var model: RefCounted = state_script.new()
	_assert_equal(
		_response(model, 201, VALID_SUCCESS)["state"],
		&"invalid_response",
		"HTTP 201 cannot satisfy the frozen dialogue success contract",
	)

	for headers: PackedStringArray in [
		PackedStringArray(["Content-Type: text/plain"]),
		PackedStringArray(),
		PackedStringArray(["Content-Type: application/json", "Content-Type: text/plain"]),
	]:
		var client: Node = client_script.new()
		client.set_request_sender_for_testing(
			func(_url: String, _headers: PackedStringArray, _method: int, _body: String) -> int:
				return OK
		)
		_assert_true(client.begin_send("Synthetic dialogue request"), "metadata request starts")
		var frozen: Dictionary = JSON.parse_string(client._frozen_payload_json)
		var payload := VALID_SUCCESS.duplicate()
		payload["request_id"] = frozen["request_id"]
		payload["conversation_id"] = frozen["conversation_id"]
		client._on_request_completed(
			HTTPRequest.RESULT_SUCCESS,
			200,
			headers,
			JSON.stringify(payload).to_utf8_buffer(),
			client.active_generation(),
		)
		_assert_equal(
			client.state,
			&"invalid_response",
			"non-JSON, missing or duplicate Content-Type is rejected",
		)
		client.free()


func _test_transport_failures(state_script: Script) -> void:
	var model: RefCounted = state_script.new()
	var timed_out: Dictionary = model.result_for_response(
		HTTPRequest.RESULT_TIMEOUT,
		0,
		PackedByteArray(),
		REQUEST_ID,
		CONVERSATION_ID,
		"neon_guide",
	)
	_assert_equal(timed_out["state"], &"timeout", "transport timeout is visible")
	_assert_true(timed_out["retryable"], "transport timeout permits manual retry")
	var unavailable: Dictionary = model.result_for_response(
		HTTPRequest.RESULT_CONNECTION_ERROR,
		0,
		PackedByteArray(),
		REQUEST_ID,
		CONVERSATION_ID,
		"neon_guide",
	)
	_assert_equal(unavailable["state"], &"unavailable", "connection error is unavailable")


func _test_input_validation(client_script: Script) -> void:
	var client: Node = client_script.new()
	var dispatches := {"count": 0}
	client.set_request_sender_for_testing(func(
		_url: String,
		_headers: PackedStringArray,
		_method: int,
		_body: String,
	) -> int:
		dispatches["count"] += 1
		return OK
	)
	for invalid_message: String in ["", "   ", "x".repeat(1001)]:
		_assert_false(client.begin_send(invalid_message), "invalid message rejected")
		_assert_equal(client.state, &"validation", "invalid message renders validation")
	_assert_equal(dispatches["count"], 0, "invalid input never dispatches")
	client.free()


func _test_single_inflight_and_manual_retry(client_script: Script) -> void:
	var client: Node = client_script.new()
	var bodies: Array[String] = []
	client.set_request_sender_for_testing(func(
		url: String,
		headers: PackedStringArray,
		method: int,
		body: String,
	) -> int:
		_assert_equal(url, "http://127.0.0.1:8000/api/v1/dialogue", "dialogue URL")
		_assert_equal(method, HTTPClient.METHOD_POST, "dialogue uses HTTP POST")
		_assert_true(headers.has("Content-Type: application/json"), "JSON content type")
		bodies.append(body)
		return OK
	)

	_assert_true(client.begin_send("  hello Nia  "), "first message dispatches")
	_assert_equal(client.state, &"loading", "first dispatch enters loading")
	_assert_true(client.is_request_in_flight(), "request marked in flight")
	_assert_false(client.begin_send("another"), "second in-flight Send rejected")
	_assert_false(client.retry(), "in-flight Retry rejected")
	_assert_equal(bodies.size(), 1, "only one request is dispatched")

	var original_payload: Dictionary = JSON.parse_string(bodies[0])
	_assert_equal(original_payload["message"], "hello Nia", "message is trimmed")
	_assert_equal(original_payload["player_id"], "local_player", "player scope")
	_assert_equal(original_payload["npc_id"], "neon_guide", "fixed NPC")
	_assert_equal(original_payload.size(), 5, "request has exactly five v1 fields")
	_assert_true(_is_uuid(String(original_payload["request_id"])), "new request UUID")
	_assert_true(_is_uuid(String(original_payload["conversation_id"])), "conversation UUID")

	var first_generation: int = client.active_generation()
	client.handle_response(first_generation, HTTPRequest.RESULT_TIMEOUT, 0, PackedByteArray())
	_assert_equal(client.state, &"timeout", "timeout completes the request")
	_assert_true(client.can_retry(), "timeout enables manual Retry")
	_assert_true(client.retry(), "manual Retry dispatches")
	_assert_equal(client.state, &"retrying", "manual Retry uses frozen state")
	_assert_equal(bodies.size(), 2, "retry dispatches exactly once")
	_assert_equal(bodies[1], bodies[0], "Retry reuses byte-identical frozen payload")

	var successful := VALID_SUCCESS.duplicate()
	successful["request_id"] = original_payload["request_id"]
	successful["conversation_id"] = original_payload["conversation_id"]
	client.handle_response(
		client.active_generation(),
		HTTPRequest.RESULT_SUCCESS,
		200,
		JSON.stringify(successful).to_utf8_buffer(),
	)
	_assert_equal(client.state, &"success", "successful Retry renders success")
	_assert_equal(client.latest_reply, successful["reply"], "successful reply retained")
	_assert_equal(client.latest_trace_id, TRACE_ID, "safe diagnostic trace retained")
	_assert_false(client.can_retry(), "success clears Retry")
	client.free()


func _test_late_callback_cannot_override_new_generation(client_script: Script) -> void:
	var client: Node = client_script.new()
	var bodies: Array[String] = []
	client.set_request_sender_for_testing(func(
		_url: String,
		_headers: PackedStringArray,
		_method: int,
		body: String,
	) -> int:
		bodies.append(body)
		return OK
	)
	client.begin_send("first")
	var old_generation: int = client.active_generation()
	client.handle_response(old_generation, HTTPRequest.RESULT_TIMEOUT, 0, PackedByteArray())
	client.begin_send("second")
	var new_generation: int = client.active_generation()
	_assert_true(new_generation > old_generation, "new send advances request generation")
	client._on_request_completed(
		HTTPRequest.RESULT_SUCCESS,
		200,
		PackedStringArray(),
		JSON.stringify(VALID_SUCCESS).to_utf8_buffer(),
		old_generation,
	)
	_assert_equal(client.state, &"loading", "late old callback cannot override loading")
	_assert_true(client.is_request_in_flight(), "late callback cannot clear new request")
	var first_payload: Dictionary = JSON.parse_string(bodies[0])
	var second_payload: Dictionary = JSON.parse_string(bodies[1])
	_assert_true(
		first_payload["request_id"] != second_payload["request_id"],
		"new Send creates a new logical request id",
	)
	client.free()


func _test_editing_message_invalidates_retry_context(client_script: Script) -> void:
	var client: Node = client_script.new()
	client.set_request_sender_for_testing(func(
		_url: String,
		_headers: PackedStringArray,
		_method: int,
		_body: String,
	) -> int:
		return OK
	)
	client.begin_send("original")
	client.handle_response(
		client.active_generation(),
		HTTPRequest.RESULT_TIMEOUT,
		0,
		PackedByteArray(),
	)
	_assert_true(client.can_retry(), "failed original request permits Retry")
	client.notify_input_changed("edited")
	_assert_false(client.can_retry(), "editing input invalidates frozen Retry context")
	_assert_false(client.retry(), "edited message cannot reuse old logical request")
	client.free()


func _test_scene_contract() -> void:
	_assert_equal(
		ProjectSettings.get_setting("application/run/main_scene"),
		"res://scenes/backend_status.tscn",
		"F-002 health diagnostic remains the default main scene",
	)
	var packed_scene: PackedScene = load(SCENE_PATH)
	_assert_true(packed_scene != null, "dialogue scene loads")
	if packed_scene == null:
		return
	var scene: Node = packed_scene.instantiate()
	_assert_true(scene is Control, "dialogue scene root is Control")
	for path in [
		"CenterContainer/VBoxContainer/TitleLabel",
		"CenterContainer/VBoxContainer/StatusLabel",
		"CenterContainer/VBoxContainer/ReplyLabel",
		"CenterContainer/VBoxContainer/MessageInput",
		"CenterContainer/VBoxContainer/CharacterCountLabel",
		"CenterContainer/VBoxContainer/ButtonRow/SendButton",
		"CenterContainer/VBoxContainer/ButtonRow/RetryButton",
		"CenterContainer/VBoxContainer/TraceLabel",
		"DialogueClient/HTTPRequest",
	]:
		_assert_true(scene.has_node(path), "dialogue scene node exists: %s" % path)
	if not _failures.is_empty():
		scene.free()
		return
	var title: Label = scene.get_node("CenterContainer/VBoxContainer/TitleLabel")
	var status: Label = scene.get_node("CenterContainer/VBoxContainer/StatusLabel")
	var input: TextEdit = scene.get_node("CenterContainer/VBoxContainer/MessageInput")
	var send: Button = scene.get_node("CenterContainer/VBoxContainer/ButtonRow/SendButton")
	var retry: Button = scene.get_node("CenterContainer/VBoxContainer/ButtonRow/RetryButton")
	var client: Node = scene.get_node("DialogueClient")
	_assert_equal(title.text, "Nia", "fixed NPC display name")
	_assert_equal(status.text, "Send a message to Nia", "frozen idle message")
	_assert_equal(input.placeholder_text, "Type your message…", "frozen input placeholder")
	_assert_equal(send.text, "Send", "send button text")
	_assert_equal(retry.text, "Retry", "retry button text")
	_assert_equal(client.dialogue_url, "http://127.0.0.1:8000/api/v1/dialogue", "local URL")
	_assert_equal(client.timeout_seconds, 15.0, "Godot dialogue timeout is 15 seconds")
	_test_rendered_scene_interaction(scene, client)
	scene.free()


func _test_rendered_scene_interaction(scene: Node, client: Node) -> void:
	var bodies: Array[String] = []
	client.set_request_sender_for_testing(func(
		_url: String,
		_headers: PackedStringArray,
		_method: int,
		body: String,
	) -> int:
		bodies.append(body)
		return OK
	)
	_root.add_child(scene)

	var status: Label = scene.get_node("CenterContainer/VBoxContainer/StatusLabel")
	var reply: Label = scene.get_node("CenterContainer/VBoxContainer/ReplyLabel")
	var input: TextEdit = scene.get_node("CenterContainer/VBoxContainer/MessageInput")
	var count: Label = scene.get_node("CenterContainer/VBoxContainer/CharacterCountLabel")
	var send: Button = scene.get_node("CenterContainer/VBoxContainer/ButtonRow/SendButton")
	var retry: Button = scene.get_node("CenterContainer/VBoxContainer/ButtonRow/RetryButton")
	var trace: Label = scene.get_node("CenterContainer/VBoxContainer/TraceLabel")
	var request_node: HTTPRequest = scene.get_node("DialogueClient/HTTPRequest")
	_assert_equal(request_node.timeout, 15.0, "HTTPRequest uses the locked timeout")
	_assert_equal(request_node.max_redirects, 0, "HTTPRequest does not follow redirects")

	input.text = "hello Nia"
	input.text_changed.emit()
	_assert_equal(count.text, "9 / 1000", "character counter follows the visible input")
	send.pressed.emit()
	_assert_equal(status.text, "Nia is thinking…", "UI renders loading state")
	_assert_true(send.disabled, "Send disabled while a request is in flight")
	_assert_false(input.editable, "input is frozen while a request is in flight")
	_assert_false(retry.visible, "Retry hidden while a request is in flight")

	client.handle_response(
		client.active_generation(),
		HTTPRequest.RESULT_TIMEOUT,
		0,
		PackedByteArray(),
	)
	_assert_equal(status.text, "Dialogue request timed out", "UI renders timeout")
	_assert_true(retry.visible, "Retry visible after timeout")
	_assert_false(retry.disabled, "Retry enabled after timeout")
	_assert_false(send.disabled, "Send re-enabled after timeout")

	retry.pressed.emit()
	_assert_equal(status.text, "Retrying dialogue…", "UI renders manual Retry")
	_assert_equal(bodies[1], bodies[0], "UI Retry preserves the exact frozen payload")
	var sent_payload: Dictionary = JSON.parse_string(bodies[1])
	var successful := VALID_SUCCESS.duplicate()
	successful["request_id"] = sent_payload["request_id"]
	successful["conversation_id"] = sent_payload["conversation_id"]
	client.handle_response(
		client.active_generation(),
		HTTPRequest.RESULT_SUCCESS,
		200,
		JSON.stringify(successful).to_utf8_buffer(),
	)
	_assert_equal(status.text, "Reply received", "UI renders successful completion")
	_assert_equal(reply.text, successful["reply"], "UI shows only the validated reply")
	_assert_true(reply.visible, "reply becomes visible on success")
	_assert_equal(trace.text, "Trace: %s" % TRACE_ID, "UI shows the safe trace identifier")
	_assert_false(retry.visible, "Retry hidden after successful completion")


func _response(model: RefCounted, response_code: int, payload: Dictionary) -> Dictionary:
	return model.result_for_response(
		HTTPRequest.RESULT_SUCCESS,
		response_code,
		JSON.stringify(payload).to_utf8_buffer(),
		REQUEST_ID,
		CONVERSATION_ID,
		"neon_guide",
	)


func _is_uuid(value: String) -> bool:
	var regex := RegEx.new()
	regex.compile("^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
	return regex.search(value) != null


func _assert_true(value: bool, label: String) -> void:
	if not value:
		_failures.append(label)


func _assert_false(value: bool, label: String) -> void:
	_assert_true(not value, label)


func _assert_equal(actual: Variant, expected: Variant, label: String) -> void:
	if actual != expected:
		_failures.append("%s (expected=%s, actual=%s)" % [label, expected, actual])
