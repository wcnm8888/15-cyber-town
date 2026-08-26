extends SceneTree

const DIALOGUE_SCENE_PATH := "res://scenes/dialogue.tscn"
const DEADLINE_MILLISECONDS := 18000
const NPCS := [
	{"npc_id": "neon_guide", "display_name": "Nia"},
	{"npc_id": "signal_archivist", "display_name": "Ivo"},
	{"npc_id": "night_courier", "display_name": "Rhea"},
]

var _scene: Control
var _dialogue_client: Node
var _relationship_client: Node
var _selector: OptionButton
var _title_label: Label
var _status_label: Label
var _reply_label: Label
var _message_input: TextEdit
var _send_button: Button
var _retry_button: Button
var _trace_label: Label
var _relationship_label: Label
var _npc_index := 0
var _conversation_ids: Array[String] = []
var _finished := false


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	var packed_scene: PackedScene = load(DIALOGUE_SCENE_PATH)
	if packed_scene == null:
		_fail("dialogue scene could not be loaded")
		return
	_scene = packed_scene.instantiate()
	root.add_child(_scene)
	_dialogue_client = _scene.get_node("DialogueClient")
	_relationship_client = _scene.get_node("RelationshipClient")
	_selector = _scene.get_node("CenterContainer/VBoxContainer/NpcRow/NpcSelector")
	_title_label = _scene.get_node("CenterContainer/VBoxContainer/TitleLabel")
	_status_label = _scene.get_node("CenterContainer/VBoxContainer/StatusLabel")
	_reply_label = _scene.get_node("CenterContainer/VBoxContainer/ReplyLabel")
	_message_input = _scene.get_node("CenterContainer/VBoxContainer/MessageInput")
	_send_button = _scene.get_node("CenterContainer/VBoxContainer/ButtonRow/SendButton")
	_retry_button = _scene.get_node("CenterContainer/VBoxContainer/ButtonRow/RetryButton")
	_trace_label = _scene.get_node("CenterContainer/VBoxContainer/TraceLabel")
	_relationship_label = _scene.get_node("CenterContainer/VBoxContainer/RelationshipLabel")
	_dialogue_client.state_changed.connect(_on_dialogue_state_changed)

	if _selector.item_count != NPCS.size():
		_fail("NPC selector did not expose the fixed allowlist")
		return
	_start_current_npc()

	var deadline := Time.get_ticks_msec() + DEADLINE_MILLISECONDS
	while not _finished and Time.get_ticks_msec() < deadline:
		await process_frame
	if not _finished:
		_fail("multi-NPC fake loopback exceeded its safety deadline")


func _start_current_npc() -> void:
	var expected: Dictionary = NPCS[_npc_index]
	if _npc_index > 0:
		_selector.select(_npc_index)
		_selector.item_selected.emit(_npc_index)
		if _reply_label.visible or _trace_label.visible or _retry_button.visible:
			_fail("NPC switch retained visible reply, trace or Retry state")
			return
		if not _message_input.text.is_empty():
			_fail("NPC switch retained the prior input")
			return
		if _relationship_label.text != "Relationship: loading…":
			_fail("NPC switch did not clear the prior relationship snapshot")
			return

	if (
		_title_label.text != String(expected["display_name"])
		or _dialogue_client.active_npc_id() != String(expected["npc_id"])
		or _relationship_client.active_npc_id() != String(expected["npc_id"])
	):
		_fail("active NPC identity did not match the selected allowlist item")
		return

	var conversation_id: String = _dialogue_client.conversation_id()
	if conversation_id in _conversation_ids:
		_fail("NPC switch reused an earlier conversation id")
		return
	_conversation_ids.append(conversation_id)

	_message_input.text = "Synthetic %s-only dialogue." % expected["display_name"]
	_message_input.text_changed.emit()
	_send_button.pressed.emit()
	var payload: Dictionary = JSON.parse_string(_dialogue_client._frozen_payload_json)
	if (
		String(payload["npc_id"]) != String(expected["npc_id"])
		or String(payload["conversation_id"]) != conversation_id
	):
		_fail("dialogue payload did not use the selected NPC scope")
		return
	if _status_label.text != "%s is thinking…" % expected["display_name"]:
		_fail("selected NPC loading state was not rendered")


func _on_dialogue_state_changed(state: StringName) -> void:
	if state == &"loading" or state == &"idle":
		return
	if state != &"success":
		_fail("multi-NPC dialogue entered an unexpected state: %s" % state)
		return
	call_deferred("_verify_current_success")


func _verify_current_success() -> void:
	await process_frame
	var expected: Dictionary = NPCS[_npc_index]
	if (
		_status_label.text != "Reply received"
		or not _reply_label.visible
		or not _reply_label.text.contains(String(expected["display_name"]))
		or not _trace_label.visible
	):
		_fail("selected NPC reply or trace was not rendered")
		return

	var relationship_deadline := Time.get_ticks_msec() + 2000
	while (
		not _relationship_label.text.contains("Reason: rule_friendly")
		and Time.get_ticks_msec() < relationship_deadline
	):
		await process_frame
	if (
		not _relationship_client.has_verified_snapshot
		or not _relationship_label.text.contains("Affection: 21/100")
		or not _relationship_label.text.contains("Reason: rule_friendly")
	):
		_fail("selected NPC relationship snapshot was not independently refreshed")
		return

	if _npc_index == NPCS.size() - 1:
		_finished = true
		print("GODOT_MULTI_NPC_FAKE=PASS npcs=Nia,Ivo,Rhea conversations=3")
		quit(0)
		return
	_npc_index += 1
	call_deferred("_start_current_npc")


func _fail(reason: String) -> void:
	if _finished:
		return
	_finished = true
	printerr("GODOT_MULTI_NPC_FAKE=FAIL reason=%s" % reason)
	quit(1)
