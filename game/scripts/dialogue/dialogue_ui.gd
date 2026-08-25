extends Control

const DialogueState = preload("res://scripts/dialogue/dialogue_state.gd")

@onready var _status_label: Label = $CenterContainer/VBoxContainer/StatusLabel
@onready var _reply_label: Label = $CenterContainer/VBoxContainer/ReplyLabel
@onready var _message_input: TextEdit = $CenterContainer/VBoxContainer/MessageInput
@onready var _character_count: Label = $CenterContainer/VBoxContainer/CharacterCountLabel
@onready var _send_button: Button = $CenterContainer/VBoxContainer/ButtonRow/SendButton
@onready var _retry_button: Button = $CenterContainer/VBoxContainer/ButtonRow/RetryButton
@onready var _trace_label: Label = $CenterContainer/VBoxContainer/TraceLabel
@onready var _relationship_label: Label = $CenterContainer/VBoxContainer/RelationshipLabel
@onready var _dialogue_client: Node = $DialogueClient
@onready var _relationship_client: Node = $RelationshipClient

var _state_model := DialogueState.new()


func _ready() -> void:
	_dialogue_client.state_changed.connect(_render_state)
	_relationship_client.snapshot_changed.connect(_render_relationship)
	_message_input.text_changed.connect(_on_message_changed)
	_send_button.pressed.connect(_on_send_pressed)
	_retry_button.pressed.connect(_on_retry_pressed)
	_update_character_count()
	_render_state(_dialogue_client.state)
	_relationship_client.refresh()
	_render_relationship(_relationship_client.state)


func _on_send_pressed() -> void:
	_dialogue_client.begin_send(_message_input.text)


func _on_retry_pressed() -> void:
	_dialogue_client.retry()


func _on_message_changed() -> void:
	_update_character_count()
	_dialogue_client.notify_input_changed(_message_input.text)
	_render_state(_dialogue_client.state)


func _update_character_count() -> void:
	_character_count.text = "%d / 1000" % _message_input.text.strip_edges().length()


func _render_state(next_state: StringName) -> void:
	_status_label.text = _state_model.message_for(next_state)
	_reply_label.text = _dialogue_client.latest_reply
	_reply_label.visible = not _reply_label.text.is_empty()
	_trace_label.text = (
		"Trace: %s" % _dialogue_client.latest_trace_id
		if not _dialogue_client.latest_trace_id.is_empty()
		else ""
	)
	_trace_label.visible = not _trace_label.text.is_empty()
	var in_flight: bool = _dialogue_client.is_request_in_flight()
	_message_input.editable = not in_flight
	_send_button.disabled = in_flight
	_retry_button.visible = _dialogue_client.can_retry()
	_retry_button.disabled = not _dialogue_client.can_retry()
	if next_state == DialogueState.SUCCESS and _dialogue_client.latest_status == "completed":
		_relationship_client.refresh(_dialogue_client.latest_request_id())


func _render_relationship(next_state: StringName) -> void:
	if next_state == &"loading" and not _relationship_client.has_verified_snapshot:
		_relationship_label.text = "Relationship: loading…"
		return
	if next_state == &"unavailable" and not _relationship_client.has_verified_snapshot:
		_relationship_label.text = "Relationship unavailable"
		return
	_relationship_label.text = "Affection: %d/100\nStage: %s" % [
		_relationship_client.score,
		_relationship_client.stage.capitalize(),
	]
	if not _relationship_client.latest_event.is_empty():
		var event: Dictionary = _relationship_client.latest_event
		_relationship_label.text += "\nChange: %+d\nReason: %s" % [
			int(event["applied_delta"]),
			String(event["reason_code"]),
		]
