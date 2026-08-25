extends Node

signal state_changed(state: StringName)

const DialogueState = preload("res://scripts/dialogue/dialogue_state.gd")

@export var dialogue_url := "http://127.0.0.1:8000/api/v1/dialogue"
@export_range(0.1, 60.0, 0.1) var timeout_seconds := 15.0

@onready var _http_request: HTTPRequest = $HTTPRequest

var state: StringName = DialogueState.IDLE
var latest_reply := ""
var latest_trace_id := ""

var _state_model := DialogueState.new()
var _conversation_id := ""
var _frozen_payload_json := ""
var _frozen_message := ""
var _generation := 0
var _request_in_flight := false
var _retry_allowed := false
var _request_sender := Callable()


func _init() -> void:
	_conversation_id = _generate_uuid()


func _ready() -> void:
	_http_request.timeout = timeout_seconds
	_http_request.max_redirects = 0


func set_request_sender_for_testing(sender: Callable) -> void:
	_request_sender = sender


func begin_send(message: String) -> bool:
	if _request_in_flight:
		return false
	var normalized := message.strip_edges()
	if normalized.is_empty() or normalized.length() > 1000:
		_clear_retry_context()
		_set_state(DialogueState.VALIDATION)
		return false

	var payload := {
		"request_id": _generate_uuid(),
		"player_id": "local_player",
		"npc_id": "neon_guide",
		"conversation_id": _conversation_id,
		"message": normalized,
	}
	_frozen_payload_json = JSON.stringify(payload)
	_frozen_message = normalized
	return _dispatch(false)


func retry() -> bool:
	if _request_in_flight or not can_retry():
		return false
	return _dispatch(true)


func notify_input_changed(message: String) -> void:
	if _request_in_flight or _frozen_payload_json.is_empty():
		return
	if message.strip_edges() != _frozen_message:
		_clear_retry_context()
		_set_state(DialogueState.IDLE)


func is_request_in_flight() -> bool:
	return _request_in_flight


func can_retry() -> bool:
	return _retry_allowed and not _frozen_payload_json.is_empty() and not _request_in_flight


func active_generation() -> int:
	return _generation


func handle_response(
	generation: int,
	result: int,
	response_code: int,
	body: PackedByteArray,
	headers: PackedStringArray = PackedStringArray(["Content-Type: application/json"]),
) -> void:
	if not _request_in_flight or generation != _generation:
		return
	_request_in_flight = false

	var frozen_payload: Dictionary = JSON.parse_string(_frozen_payload_json)
	var outcome: Dictionary = _state_model.result_for_response(
		result,
		response_code,
		body,
		String(frozen_payload["request_id"]),
		String(frozen_payload["conversation_id"]),
		String(frozen_payload["npc_id"]),
		headers,
	)
	latest_reply = String(outcome["reply"])
	latest_trace_id = String(outcome["trace_id"])
	_retry_allowed = bool(outcome["retryable"])
	_set_state(outcome["state"])


func _dispatch(is_retry: bool) -> bool:
	_generation += 1
	_request_in_flight = true
	_retry_allowed = false
	latest_reply = ""
	latest_trace_id = ""
	_set_state(DialogueState.RETRYING if is_retry else DialogueState.LOADING)

	var headers := PackedStringArray(["Content-Type: application/json"])
	var dispatch_error: int
	if _request_sender.is_valid():
		dispatch_error = int(
			_request_sender.call(
				dialogue_url,
				headers,
				HTTPClient.METHOD_POST,
				_frozen_payload_json,
			)
		)
	elif is_instance_valid(_http_request):
		var completion := _on_request_completed.bind(_generation)
		_http_request.request_completed.connect(completion, CONNECT_ONE_SHOT)
		dispatch_error = _http_request.request(
			dialogue_url,
			headers,
			HTTPClient.METHOD_POST,
			_frozen_payload_json,
		)
		if dispatch_error != OK and _http_request.request_completed.is_connected(completion):
			_http_request.request_completed.disconnect(completion)
	else:
		dispatch_error = ERR_UNCONFIGURED

	if dispatch_error != OK:
		_request_in_flight = false
		_retry_allowed = true
		_set_state(DialogueState.UNAVAILABLE)
		return false
	return true


func _on_request_completed(
	result: int,
	response_code: int,
	headers: PackedStringArray,
	body: PackedByteArray,
	generation: int,
) -> void:
	handle_response(generation, result, response_code, body, headers)


func _clear_retry_context() -> void:
	_retry_allowed = false
	_frozen_payload_json = ""
	_frozen_message = ""


func _set_state(next_state: StringName) -> void:
	state = next_state
	state_changed.emit(state)


func _generate_uuid() -> String:
	var bytes := Crypto.new().generate_random_bytes(16)
	bytes[6] = (bytes[6] & 0x0f) | 0x40
	bytes[8] = (bytes[8] & 0x3f) | 0x80
	var encoded := ""
	for index in range(bytes.size()):
		if index in [4, 6, 8, 10]:
			encoded += "-"
		encoded += "%02x" % bytes[index]
	return encoded
