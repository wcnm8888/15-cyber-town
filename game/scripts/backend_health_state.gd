extends RefCounted

const CONNECTING: StringName = &"connecting"
const CONNECTED: StringName = &"connected"
const TIMEOUT: StringName = &"timeout"
const UNAVAILABLE: StringName = &"unavailable"
const RETRY: StringName = &"retry"

const EXPECTED_HEALTH := {
	"status": "ok",
	"service": "cyber-town-backend",
	"api_version": "v1",
}

const STATE_MESSAGES := {
	CONNECTING: "Connecting to backend…",
	CONNECTED: "Backend connected",
	TIMEOUT: "Connection timed out",
	UNAVAILABLE: "Backend unavailable",
	RETRY: "Retrying connection…",
}


func message_for(state: StringName) -> String:
	return STATE_MESSAGES.get(state, STATE_MESSAGES[UNAVAILABLE])


func is_retry_visible(state: StringName) -> bool:
	return state != CONNECTED


func is_retry_enabled(state: StringName) -> bool:
	return state == TIMEOUT or state == UNAVAILABLE


func state_for_response(
	result: int,
	response_code: int,
	body: PackedByteArray,
) -> StringName:
	if result == HTTPRequest.RESULT_TIMEOUT:
		return TIMEOUT
	if result != HTTPRequest.RESULT_SUCCESS:
		return UNAVAILABLE
	if response_code < 200 or response_code >= 300:
		return UNAVAILABLE
	if body.is_empty():
		return UNAVAILABLE

	var response_text := body.get_string_from_utf8()
	var json := JSON.new()
	if json.parse(response_text) != OK:
		return UNAVAILABLE
	var parsed: Variant = json.data
	if typeof(parsed) != TYPE_DICTIONARY:
		return UNAVAILABLE

	var payload: Dictionary = parsed
	if _top_level_object_member_count(response_text) != EXPECTED_HEALTH.size():
		return UNAVAILABLE
	if payload.size() != EXPECTED_HEALTH.size():
		return UNAVAILABLE
	for key: String in EXPECTED_HEALTH:
		if not payload.has(key):
			return UNAVAILABLE
		var actual_value: Variant = payload[key]
		if typeof(actual_value) != TYPE_STRING:
			return UNAVAILABLE
		if String(actual_value) != String(EXPECTED_HEALTH[key]):
			return UNAVAILABLE

	return CONNECTED


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
