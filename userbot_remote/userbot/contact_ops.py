"""Entity resolution and dialog listing helpers for Telethon."""

from __future__ import annotations

from telethon.errors import RPCError
from telethon.tl.custom import Dialog
from telethon.utils import get_display_name


async def resolve_entity(client, identifier):
    """Resolve a Telegram entity from username, phone, id, or dialog title.

    Args:
        client: Active Telethon client.
        identifier: Chat/user identifier in string or integer form.

    Returns:
        A Telethon entity object.

    Raises:
        ValueError: If the entity cannot be resolved.
    """

    if identifier is None:
        raise ValueError("Target chat ko'rsatilmagan.")

    if hasattr(identifier, "id"):
        return identifier

    raw = str(identifier).strip()
    if not raw:
        raise ValueError("Bo'sh target yuborildi.")

    try:
        if raw.startswith("@"):
            return await client.get_entity(raw)
        if raw.lstrip("+").isdigit():
            try:
                return await client.get_entity(raw)
            except RPCError:
                return await client.get_entity(int(raw.lstrip("+")))
        return await client.get_entity(raw)
    except Exception:
        lowered = raw.lower()
        exact_match = None
        partial_match = None
        async for dialog in client.iter_dialogs():
            title = (dialog.name or "").strip()
            username = getattr(dialog.entity, "username", None)
            candidate_pool = {title.lower()}
            if username:
                candidate_pool.add(username.lower())
                candidate_pool.add(f"@{username.lower()}")
            if lowered in candidate_pool:
                exact_match = dialog.entity
                break
            if lowered in title.lower() or (username and lowered in username.lower()):
                partial_match = dialog.entity
        if exact_match is not None:
            return exact_match
        if partial_match is not None:
            return partial_match
    raise ValueError(f"Entity topilmadi: {raw}")


async def get_all_dialogs(client) -> list[dict]:
    """Return all dialogs visible to the owner's Telegram account.

    Args:
        client: Active Telethon client.

    Returns:
        A list of dialog metadata dictionaries.
    """

    dialogs: list[dict] = []
    async for dialog in client.iter_dialogs():
        dialogs.append(_dialog_to_dict(dialog))
    return dialogs


def _dialog_to_dict(dialog: Dialog) -> dict:
    """Convert a Telethon dialog into a serializable dictionary."""

    username = getattr(dialog.entity, "username", None)
    dialog_type = "user"
    if dialog.is_group:
        dialog_type = "group"
    elif dialog.is_channel:
        dialog_type = "channel"
    return {
        "id": dialog.id,
        "title": dialog.name or get_display_name(dialog.entity),
        "username": username,
        "type": dialog_type,
        "unread_count": dialog.unread_count,
    }
