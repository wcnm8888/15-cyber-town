extends Control

const BackendHealthState = preload("res://scripts/backend_health_state.gd")

@onready var _status_label: Label = $CenterContainer/VBoxContainer/StatusLabel
@onready var _retry_button: Button = $CenterContainer/VBoxContainer/RetryButton
@onready var _health_client: Node = $BackendHealthClient

var _state_model := BackendHealthState.new()


func _ready() -> void:
	_health_client.state_changed.connect(_render_state)
	_retry_button.pressed.connect(_on_retry_pressed)
	_render_state(_health_client.state)
	_health_client.begin_check(false)


func _on_retry_pressed() -> void:
	_health_client.begin_check(true)


func _render_state(state: StringName) -> void:
	_status_label.text = _state_model.message_for(state)
	_retry_button.visible = _state_model.is_retry_visible(state)
	_retry_button.disabled = not _state_model.is_retry_enabled(state)
