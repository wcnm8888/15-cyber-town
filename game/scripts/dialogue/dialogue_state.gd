extends RefCounted

const IDLE: StringName = &"idle"
const LOADING: StringName = &"loading"
const SUCCESS: StringName = &"success"
const TIMEOUT: StringName = &"timeout"
const UNAVAILABLE: StringName = &"unavailable"
const INVALID_RESPONSE: StringName = &"invalid_response"
const UNSAFE: StringName = &"unsafe"
const VALIDATION: StringName = &"validation"
const RETRYING: StringName = &"retrying"

const STATE_MESSAGES := {
	IDLE: "Send a message to Nia",
	LOADING: "Nia is thinking…",
	SUCCESS: "Reply received",
	TIMEOUT: "Dialogue request timed out",
	UNAVAILABLE: "Dialogue service unavailable",
	INVALID_RESPONSE: "Invalid dialogue response",
	UNSAFE: "That message could not be processed",
	VALIDATION: "Enter 1–1000 characters",
	RETRYING: "Retrying dialogue…",
}

const SUCCESS_FIELDS := [
	"request_id",
	"trace_id",
	"npc_id",
	"conversation_id",
	"reply",
	"status",
	"provider",
]
const ERROR_FIELDS := ["trace_id", "code", "message", "retryable"]
const ERROR_MAPPINGS := {
	400: ["unsafe_content", false, UNSAFE],
	404: ["npc_not_found", false, UNAVAILABLE],
	409: ["conflict", false, UNAVAILABLE],
	422: ["validation_error", false, VALIDATION],
	500: ["internal_error", false, UNAVAILABLE],
	502: ["provider_unavailable", true, INVALID_RESPONSE],
	503: ["provider_unavailable", true, UNAVAILABLE],
	504: ["provider_timeout", true, TIMEOUT],
}

var _uuid_pattern := RegEx.new()


func _init() -> void:
	_uuid_pattern.compile(
		"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
		+ "[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
	)


func message_for(state: StringName) -> String:
	return STATE_MESSAGES.get(state, STATE_MESSAGES[INVALID_RESPONSE])


func result_for_response(
	result: int,
	response_code: int,
	body: PackedByteArray,
	expected_request_id: String,
	expected_conversation_id: String,
	expected_npc_id: String,
	headers: PackedStringArray = PackedStringArray(["Content-Type: application/json"]),
) -> Dictionary:
	if result == HTTPRequest.RESULT_TIMEOUT:
		return _result(TIMEOUT, true)
	if result != HTTPRequest.RESULT_SUCCESS:
		return _result(UNAVAILABLE, true)
	if body.is_empty() or not _has_json_content_type(headers):
		return _invalid()

	var response_text := body.get_string_from_utf8()
	var json := JSON.new()
	if json.parse(response_text) != OK or typeof(json.data) != TYPE_DICTIONARY:
		return _invalid()
	var payload: Dictionary = json.data

	if response_code == 200:
		return _validate_success(
			payload,
			response_text,
			expected_request_id,
			expected_conversation_id,
			expected_npc_id,
		)
	return _validate_error(payload, response_text, response_code)


func _has_json_content_type(headers: PackedStringArray) -> bool:
	var content_type_count := 0
	for header: String in headers:
		var separator := header.find(":")
		if separator < 0:
			continue
		var name := header.substr(0, separator).strip_edges().to_lower()
		if name != "content-type":
			continue
		content_type_count += 1
		var value := header.substr(separator + 1).get_slice(";", 0).strip_edges().to_lower()
		if value != "application/json":
			return false
	return content_type_count == 1


func _validate_success(
	payload: Dictionary,
	response_text: String,
	expected_request_id: String,
	expected_conversation_id: String,
	expected_npc_id: String,
) -> Dictionary:
	if not _has_exact_fields(payload, response_text, SUCCESS_FIELDS):
		return _invalid()
	for key: String in SUCCESS_FIELDS:
		if typeof(payload[key]) != TYPE_STRING:
			return _invalid()

	if (
		String(payload["request_id"]) != expected_request_id
		or String(payload["conversation_id"]) != expected_conversation_id
		or String(payload["npc_id"]) != expected_npc_id
		or not _is_canonical_uuid(String(payload["request_id"]))
		or not _is_canonical_uuid(String(payload["conversation_id"]))
		or not _is_canonical_uuid(String(payload["trace_id"]))
	):
		return _invalid()

	var reply := String(payload["reply"])
	var provider := String(payload["provider"])
	if (
		reply.is_empty()
		or reply.length() > 4000
		or reply != reply.strip_edges()
		or provider.is_empty()
		or provider.length() > 64
		or provider != provider.strip_edges()
		or not String(payload["status"]) in ["completed", "degraded"]
	):
		return _invalid()

	return {
		"state": SUCCESS,
		"reply": reply,
		"trace_id": String(payload["trace_id"]),
		"status": String(payload["status"]),
		"retryable": false,
	}


func _validate_error(
	payload: Dictionary,
	response_text: String,
	response_code: int,
) -> Dictionary:
	if (
		not ERROR_MAPPINGS.has(response_code)
		or not _has_exact_fields(payload, response_text, ERROR_FIELDS)
		or typeof(payload["trace_id"]) != TYPE_STRING
		or typeof(payload["code"]) != TYPE_STRING
		or typeof(payload["message"]) != TYPE_STRING
		or typeof(payload["retryable"]) != TYPE_BOOL
	):
		return _invalid()

	var mapping: Array = ERROR_MAPPINGS[response_code]
	var message := String(payload["message"])
	if (
		not _is_canonical_uuid(String(payload["trace_id"]))
		or String(payload["code"]) != String(mapping[0])
		or bool(payload["retryable"]) != bool(mapping[1])
		or message.is_empty()
		or message.length() > 500
		or message != message.strip_edges()
	):
		return _invalid()

	return {
		"state": mapping[2],
		"reply": "",
		"trace_id": String(payload["trace_id"]),
		"status": "",
		"retryable": bool(mapping[1]),
	}


func _has_exact_fields(payload: Dictionary, response_text: String, expected: Array) -> bool:
	if (
		payload.size() != expected.size()
		or _top_level_object_member_count(response_text) != expected.size()
	):
		return false
	for key: String in expected:
		if not payload.has(key):
			return false
	return true


func _is_canonical_uuid(value: String) -> bool:
	return _uuid_pattern.search(value) != null


func _top_level_object_member_count(text: String) -> int:
	var object_depth := 0
	var in_string := false
	var escaped := false
	var member_count := 0
	for index in range(text.length()):
		var character := text[index]
		if in_string:
			if escaped:
				escaped = false
			elif character == "\\":
				escaped = true
			elif character == '"':
				in_string = false
			continue
		if character == '"':
			in_string = true
		elif character == "{":
			object_depth += 1
		elif character == "}":
			object_depth -= 1
		elif character == ":" and object_depth == 1:
			member_count += 1
	return member_count


func _invalid() -> Dictionary:
	return _result(INVALID_RESPONSE, true)


func _result(state: StringName, retryable: bool) -> Dictionary:
	return {
		"state": state,
		"reply": "",
		"trace_id": "",
		"status": "",
		"retryable": retryable,
	}
