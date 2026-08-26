extends RefCounted

const DEFAULT_NPC_ID := "neon_guide"
const _DEFINITIONS := [
	{"npc_id": "neon_guide", "display_name": "Nia"},
	{"npc_id": "signal_archivist", "display_name": "Ivo"},
	{"npc_id": "night_courier", "display_name": "Rhea"},
]


func definitions() -> Array[Dictionary]:
	var result: Array[Dictionary] = []
	for definition: Dictionary in _DEFINITIONS:
		result.append(definition.duplicate())
	return result


func is_allowed(npc_id: String) -> bool:
	return not display_name_for(npc_id).is_empty()


func display_name_for(npc_id: String) -> String:
	for definition: Dictionary in _DEFINITIONS:
		if String(definition["npc_id"]) == npc_id:
			return String(definition["display_name"])
	return ""
