"""Crossbot-Plugin fuer Hermes Agent — Registrierung."""

from . import schemas, tools

_TOOLS = (
    ("crossbot_send", schemas.SEND, tools.crossbot_send),
    ("crossbot_broadcast", schemas.BROADCAST, tools.crossbot_broadcast),
    ("crossbot_pending", schemas.PENDING, tools.crossbot_pending),
    ("crossbot_respond", schemas.RESPOND, tools.crossbot_respond),
    ("crossbot_cancel", schemas.CANCEL, tools.crossbot_cancel),
    ("crossbot_status", schemas.STATUS, tools.crossbot_status),
    ("crossbot_register_bot", schemas.REGISTER_BOT, tools.crossbot_register_bot),
    ("crossbot_revoke_bot", schemas.REVOKE_BOT, tools.crossbot_revoke_bot),
    ("crossbot_list_bots", schemas.LIST_BOTS, tools.crossbot_list_bots),
    ("crossbot_list_groups", schemas.LIST_GROUPS, tools.crossbot_list_groups),
    ("crossbot_group_members", schemas.GROUP_MEMBERS, tools.crossbot_group_members),
    ("crossbot_group_add", schemas.GROUP_ADD, tools.crossbot_group_add),
    ("crossbot_group_remove", schemas.GROUP_REMOVE, tools.crossbot_group_remove),
)


def register(ctx):
    for name, schema, handler in _TOOLS:
        ctx.register_tool(name=name, toolset="crossbot", schema=schema, handler=handler)
