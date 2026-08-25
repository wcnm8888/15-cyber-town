extends Node

signal snapshot_changed(state: StringName)

const IDLE: StringName = &"idle"
const LOADING: StringName = &"loading"
const AVAILABLE: StringName = &"available"
const UNAVAILABLE: StringName = &"unavailable"
const RESPONSE_FIELDS := ["npc_id", "score", "stage", "rule_version", "event"]
const EVENT_FIELDS := ["category", "applied_delta", "reason_code", "score", "stage", "occurred_at"]
const STAGES := ["newcomer", "acquaintance", "friend", "trusted_ally"]
const CATEGORIES := ["supportive", "friendly", "neutral", "dismissive", "hostile"]
const REASON_CODES := [
	"rule_supportive",
	"rule_friendly",
	"rule_neutral",
	"rule_dismissive",
	"rule_hostile",
	"low_confidence",
	"candidate_invalid",
	"cooldown",
	"score_floor",
	"score_ceiling",
]

@export var relationship_url := "http://127.0.0.1:8000/api/v1/relationships"
@export_range(0.1, 60.0, 0.1) var timeout_seconds := 15.0

@onready var _http_request: HTTPRequest = $HTTPRequest

var state: StringName = IDLE
var score := 20
var stage := "acquaintance"
var latest_event: Dictionary = {}
var has_verified_snapshot := false
var last_failure := ""

var _generation := 0
var _request_in_flight := false
var _pending_request_id := ""


func _ready() -> void:
	_http_request.timeout = timeout_seconds


func refresh(request_id := "") -> bool:
	if _request_in_flight:
		_pending_request_id = request_id
		return false
	_generation += 1
	_request_in_flight = true
	_set_state(LOADING)
	var url := relationship_url + "/local_player/neon_guide"
	if not request_id.is_empty():
		url += "?request_id=" + request_id.uri_encode()
	var completion := _on_request_completed.bind(_generation)
	_http_request.request_completed.connect(completion, CONNECT_ONE_SHOT)
	var dispatch_error := _http_request.request(url, PackedStringArray(["Accept: application/json"]))
	if dispatch_error != OK:
		if _http_request.request_completed.is_connected(completion):
			_http_request.request_completed.disconnect(completion)
		_request_in_flight = false
		_set_state(UNAVAILABLE)
		return false
	return true


func _on_request_completed(
	result: int,
	response_code: int,
	headers: PackedStringArray,
	body: PackedByteArray,
	generation: int,
) -> void:
	if not _request_in_flight or generation != _generation:
		return
	_request_in_flight = false
	if result != HTTPRequest.RESULT_SUCCESS or response_code != 200 or not _has_json_content_type(headers):
		last_failure = "transport=%d http=%d headers=%s" % [result, response_code, headers]
		_set_state(UNAVAILABLE)
		_dispatch_pending_refresh()
		return
	var json := JSON.new()
	if json.parse(body.get_string_from_utf8()) != OK or typeof(json.data) != TYPE_DICTIONARY:
		last_failure = "relationship response was not a JSON object"
		_set_state(UNAVAILABLE)
		_dispatch_pending_refresh()
		return
	var payload: Dictionary = json.data
	if not _is_valid_snapshot(payload):
		last_failure = "relationship response did not match the approved contract"
		_set_state(UNAVAILABLE)
		_dispatch_pending_refresh()
		return
	score = int(payload["score"])
	stage = String(payload["stage"])
	latest_event = {} if payload["event"] == null else payload["event"].duplicate()
	has_verified_snapshot = true
	last_failure = ""
	_set_state(AVAILABLE)
	_dispatch_pending_refresh()


func _is_valid_snapshot(payload: Dictionary) -> bool:
	if payload.size() != RESPONSE_FIELDS.size():
		return false
	for field: String in RESPONSE_FIELDS:
		if not payload.has(field):
			return false
	if (
		typeof(payload["npc_id"]) != TYPE_STRING
		or String(payload["npc_id"]) != "neon_guide"
		or not _is_integer_in_range(payload["score"], 0, 100)
		or typeof(payload["stage"]) != TYPE_STRING
		or not String(payload["stage"]) in STAGES
		or typeof(payload["rule_version"]) != TYPE_STRING
		or String(payload["rule_version"]) != "f-006-v1"
	):
		return false
	if payload["event"] == null:
		return true
	if typeof(payload["event"]) != TYPE_DICTIONARY:
		return false
	var event: Dictionary = payload["event"]
	if event.size() != EVENT_FIELDS.size():
		return false
	for field: String in EVENT_FIELDS:
		if not event.has(field):
			return false
	if (
		(event["category"] != null and (
			typeof(event["category"]) != TYPE_STRING or not String(event["category"]) in CATEGORIES
		))
		or not _is_integer_in_range(event["applied_delta"], -2, 2)
		or typeof(event["reason_code"]) != TYPE_STRING
		or not String(event["reason_code"]) in REASON_CODES
		or not _is_integer_in_range(event["score"], 0, 100)
		or int(event["score"]) != int(payload["score"])
		or typeof(event["stage"]) != TYPE_STRING
		or String(event["stage"]) != String(payload["stage"])
		or not _is_integer_in_range(event["occurred_at"], 1, 9000000000)
	):
		return false
	return true


func _has_json_content_type(headers: PackedStringArray) -> bool:
	var count := 0
	for header: String in headers:
		var separator := header.find(":")
		if separator < 0 or header.substr(0, separator).strip_edges().to_lower() != "content-type":
			continue
		count += 1
		if header.substr(separator + 1).get_slice(";", 0).strip_edges().to_lower() != "application/json":
			return false
	return count == 1


func _is_integer_in_range(value: Variant, minimum: int, maximum: int) -> bool:
	if typeof(value) != TYPE_INT and typeof(value) != TYPE_FLOAT:
		return false
	var numeric := float(value)
	return numeric == floor(numeric) and numeric >= minimum and numeric <= maximum


func _set_state(next_state: StringName) -> void:
	state = next_state
	snapshot_changed.emit(state)


func _dispatch_pending_refresh() -> void:
	if _pending_request_id.is_empty():
		return
	var request_id := _pending_request_id
	_pending_request_id = ""
	call_deferred("refresh", request_id)
