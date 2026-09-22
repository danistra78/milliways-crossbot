"""Tool schemas — was das LLM liest, um zu entscheiden, wann welches Tool
aufgerufen wird."""

SEND = {
    "name": "crossbot_send",
    "description": (
        "Sendet eine Nachricht an genau einen anderen Bot ueber den "
        "Cross-Bot Message Bus. Nutze dies fuer direkte Bot-zu-Bot-Kommunikation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_bot": {"type": "string", "description": "Name des sendenden Bots (muss zum verwendeten Key passen)"},
            "to_bot": {"type": "string", "description": "Name des Ziel-Bots"},
            "body": {"type": "string", "description": "Nachrichtentext"},
            "subject": {"type": "string", "description": "Optionaler Betreff"},
        },
        "required": ["from_bot", "to_bot", "body"],
    },
}

BROADCAST = {
    "name": "crossbot_broadcast",
    "description": (
        "Sendet eine Nachricht an ALLE Mitglieder einer Gruppe gleichzeitig. "
        "Nutze dies statt crossbot_send, wenn mehrere Bots dieselbe Nachricht bekommen sollen."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "from_bot": {"type": "string", "description": "Name des sendenden Bots"},
            "to_group": {"type": "string", "description": "Name der Zielgruppe"},
            "body": {"type": "string", "description": "Nachrichtentext"},
            "subject": {"type": "string", "description": "Optionaler Betreff"},
        },
        "required": ["from_bot", "to_group", "body"],
    },
}

PENDING = {
    "name": "crossbot_pending",
    "description": (
        "Holt die haengigen (noch unbeantworteten) Nachrichten fuer einen Bot, "
        "aelteste zuerst (FIFO). Nutze dies, um das eigene Postfach abzufragen."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "bot_name": {"type": "string", "description": "Name des Bots, dessen Postfach abgefragt wird"},
            "limit": {"type": "integer", "description": "Max. Anzahl Nachrichten (Standard 100, max 1000)"},
        },
        "required": ["bot_name"],
    },
}

RESPOND = {
    "name": "crossbot_respond",
    "description": "Beantwortet eine haengige Nachricht und schliesst sie ab (status wird 'done').",
    "parameters": {
        "type": "object",
        "properties": {
            "msg_id": {"type": "integer", "description": "ID der Nachricht"},
            "response_text": {"type": "string", "description": "Antworttext"},
        },
        "required": ["msg_id", "response_text"],
    },
}

CANCEL = {
    "name": "crossbot_cancel",
    "description": "Nimmt eine noch offene (pending) Nachricht zurueck, bevor sie beantwortet wurde.",
    "parameters": {
        "type": "object",
        "properties": {
            "msg_id": {"type": "integer", "description": "ID der zurueckzunehmenden Nachricht"},
        },
        "required": ["msg_id"],
    },
}

STATUS = {
    "name": "crossbot_status",
    "description": "Fragt den aktuellen Status (pending/done/cancelled) und ggf. die Antwort einer Nachricht ab.",
    "parameters": {
        "type": "object",
        "properties": {
            "msg_id": {"type": "integer", "description": "ID der Nachricht"},
        },
        "required": ["msg_id"],
    },
}

REGISTER_BOT = {
    "name": "crossbot_register_bot",
    "description": (
        "Registriert einen neuen Bot am Message Bus (Admin-Key noetig) und gibt "
        "dessen Key EINMALIG zurueck. Nutze dies nur, um einen neuen Bot ans System anzubinden."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Eindeutiger Name des neuen Bots"},
        },
        "required": ["name"],
    },
}

REVOKE_BOT = {
    "name": "crossbot_revoke_bot",
    "description": "Widerruft den Key eines Bots, entfernt ihn aus allen Gruppen (Admin-Key noetig).",
    "parameters": {
        "type": "object",
        "properties": {
            "name": {"type": "string", "description": "Name des zu widerrufenden Bots"},
        },
        "required": ["name"],
    },
}

LIST_BOTS = {
    "name": "crossbot_list_bots",
    "description": "Listet alle am Message Bus registrierten Bots inkl. letztem Aktivitaets-Zeitpunkt.",
    "parameters": {"type": "object", "properties": {}},
}

LIST_GROUPS = {
    "name": "crossbot_list_groups",
    "description": "Listet alle existierenden Gruppen (fuer Broadcast).",
    "parameters": {"type": "object", "properties": {}},
}

GROUP_MEMBERS = {
    "name": "crossbot_group_members",
    "description": "Listet die Mitglieder einer Gruppe.",
    "parameters": {
        "type": "object",
        "properties": {
            "group": {"type": "string", "description": "Name der Gruppe"},
        },
        "required": ["group"],
    },
}

GROUP_ADD = {
    "name": "crossbot_group_add",
    "description": "Fuegt einen Bot einer Gruppe hinzu (Admin-Key noetig).",
    "parameters": {
        "type": "object",
        "properties": {
            "group": {"type": "string", "description": "Name der Gruppe"},
            "bot": {"type": "string", "description": "Name des Bots"},
        },
        "required": ["group", "bot"],
    },
}

GROUP_REMOVE = {
    "name": "crossbot_group_remove",
    "description": "Entfernt einen Bot aus einer Gruppe (Admin-Key noetig).",
    "parameters": {
        "type": "object",
        "properties": {
            "group": {"type": "string", "description": "Name der Gruppe"},
            "bot": {"type": "string", "description": "Name des Bots"},
        },
        "required": ["group", "bot"],
    },
}
