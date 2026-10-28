from typing import TYPE_CHECKING

from astrbot.api.event import AstrMessageEvent, MessageChain
from astrbot.api.platform import Group

if TYPE_CHECKING:
    from .milky_adapter import MilkyAdapter


class MilkyMessageEvent(AstrMessageEvent):
    def __init__(self, message, adapter: "MilkyAdapter") -> None:
        super().__init__(
            message.message_str, message, adapter.meta(), message.session_id
        )
        self.adapter = adapter
        # Expose the client for plugins that retrieve incoming audio via get_record.
        self.bot = adapter

    async def send(self, message: MessageChain) -> None:
        await self.adapter.send_by_session(self.session, message)
        await super().send(message)

    async def get_group(self, group_id: str | None = None, **kwargs) -> Group | None:
        target = group_id or self.get_group_id()
        if not target:
            return None
        result = await self.adapter.call_action("get_group_info", group_id=int(target))
        info = result["group"]
        return Group(
            group_id=str(info["group_id"]),
            group_name=info.get("group_name"),
            member_count=info.get("member_count"),
        )
