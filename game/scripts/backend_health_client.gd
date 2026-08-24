extends Node

signal state_changed(state: StringName)

const BackendHealthState = preload("res://scripts/backend_health_state.gd")

@export var health_url := "http://127.0.0.1:8000/api/v1/health"
@export_range(0.1, 60.0, 0.1) var timeout_seconds := 3.0

@onready var _http_request: HTTPRequest = $HTTPRequest

var state: StringName = BackendHealthState.CONNECTING
var _request_in_flight := false
var _request_sender := Callable()
var _state_model := BackendHealthState.new()


func _ready() -> void:
	_http_request.timeout = timeout_seconds
	_http_request.max_redirects = 0
	_http_request.request_completed.connect(_on_request_completed)


func set_request_sender_for_testing(sender: Callable) -> void:
	_request_sender = sender


func begin_check(is_retry: bool) -> bool:
	if _request_in_flight:
		return false

	_set_state(BackendHealthState.RETRY if is_retry else BackendHealthState.CONNECTING)
	_request_in_flight = true

	var dispatch_error: int
	if _request_sender.is_valid():
		dispatch_error = int(_request_sender.call(health_url))
	elif is_instance_valid(_http_request):
		dispatch_error = _http_request.request(health_url)
	else:
		dispatch_error = ERR_UNCONFIGURED

	if dispatch_error != OK:
		_request_in_flight = false
		_set_state(BackendHealthState.UNAVAILABLE)
		return false

	return true


func is_request_in_flight() -> bool:
	return _request_in_flight


func handle_response(result: int, response_code: int, body: PackedByteArray) -> void:
	if not _request_in_flight:
		return

	_request_in_flight = false
	_set_state(_state_model.state_for_response(result, response_code, body))


func _on_request_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	handle_response(result, response_code, body)


func _set_state(next_state: StringName) -> void:
	state = next_state
	state_changed.emit(state)
