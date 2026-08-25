extends SceneTree

const DIALOGUE_SCENE_PATH := "res://scenes/dialogue.tscn"
const DEADLINE_MILLISECONDS := 18000
const COMMANDS := [
	"Remember: game_alias=BLUE-47",
	"What is my game_alias?",
	"Forget: game_alias",
	"What is my game_alias?",
]

var _client: Node
var _message_input: TextEdit
var _send_button: Button
var _reply_label: Label
var _step := 0
var _finished := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var packed_scene: PackedScene = load(DIALOGUE_SCENE_PATH)
	if packed_scene == null:
		_fail("existing dialogue scene could not be loaded")
		return
	var scene: Control = packed_scene.instantiate()
	root.add_child(scene)
	_client = scene.get_node("DialogueClient")
	_message_input = scene.get_node("CenterContainer/VBoxContainer/MessageInput")
	_send_button = scene.get_node("CenterContainer/VBoxContainer/ButtonRow/SendButton")
	_reply_label = scene.get_node("CenterContainer/VBoxContainer/ReplyLabel")
	_client.state_changed.connect(_on_state_changed)
	_send_current()

	var deadline := Time.get_ticks_msec() + DEADLINE_MILLISECONDS
	while not _finished and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _finished:
		_fail("long-term memory fake loopback exceeded its deadline")


func _send_current() -> void:
	_message_input.text = COMMANDS[_step]
	_message_input.text_changed.emit()
	_send_button.pressed.emit()


func _on_state_changed(state: StringName) -> void:
	if state == &"idle" or state == &"loading":
		return
	if state != &"success":
		_fail("long-term memory dialogue entered state %s at step %d" % [state, _step])
		return
	call_deferred("_verify_step")


func _verify_step() -> void:
	await process_frame
	if _send_button.disabled or not _reply_label.visible:
		_fail("long-term memory response was not rendered safely")
		return
	if _step == 1 and not _reply_label.text.contains("BLUE-47"):
		_fail("persisted game alias was not recalled in the real dialogue UI")
		return
	if _step == 3:
		if _reply_label.text.contains("BLUE-47") or not _reply_label.text.contains("do not know"):
			_fail("forgotten memory was recalled or its absence was fabricated")
			return
		_finished = true
		print("GODOT_FAKE_LONG_TERM_MEMORY=PASS")
		quit(0)
		return

	_step += 1
	call_deferred("_send_current")


func _fail(message: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("GODOT_FAKE_LONG_TERM_MEMORY=FAIL ", message)
	quit(1)
