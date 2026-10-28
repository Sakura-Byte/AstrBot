import asyncio
import base64
import json
from pathlib import Path
from urllib.parse import urlsplit

import aiohttp

from astrbot.api import logger
from astrbot.api.event import MessageChain
from astrbot.api.message_components import (
    At,
    AtAll,
    Face,
    File,
    Forward,
    Image,
    Plain,
    Record,
    Reply,
    Video,
)
from astrbot.api.platform import (
    AstrBotMessage,
    MessageMember,
    MessageType,
    Platform,
    PlatformMetadata,
)
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.register import register_platform_adapter
from astrbot.core.utils.media_utils import MediaResolver

from .milky_event import MilkyMessageEvent


@register_platform_adapter(
    "milky", "Milky HTTP API and WebSocket events", support_streaming_message=False
)
class MilkyAdapter(Platform):
    def __init__(self, platform_config, platform_settings, event_queue) -> None:
        super().__init__(platform_config, event_queue)
        self.settings = platform_settings
        self.base_url = platform_config.get(
            "milky_url", "http://127.0.0.1:3000"
        ).rstrip("/")
        parsed = urlsplit(self.base_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("Milky service URL must use HTTP or HTTPS")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError(
                "Use milky_token for credentials; the service URL must not contain credentials, a query or a fragment"
            )
        self.headers = {}
        if token := platform_config.get("milky_token"):
            self.headers["Authorization"] = f"Bearer {token}"
        self._session: aiohttp.ClientSession | None = None
        self._stopping = asyncio.Event()
        self._metadata = PlatformMetadata(
            name="milky",
            description="Milky HTTP API and WebSocket events",
            id=platform_config["id"],
            adapter_display_name="Milky",
            support_streaming_message=False,
        )

    def meta(self) -> PlatformMetadata:
        return self._metadata

    def get_client(self) -> "MilkyAdapter":
        return self

    async def call_action(self, action: str, **params) -> dict:
        """Call a native Milky API using bearer authentication.

        Args:
            action: Milky API name without a path prefix.
            **params: Native Milky request parameters.

        Returns:
            The response data object.

        Raises:
            RuntimeError: The API returned a failure response.
        """
        if not action.replace("_", "").isalnum():
            raise ValueError("Invalid Milky API name")
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers=self.headers, timeout=aiohttp.ClientTimeout(total=180)
            )
        async with self._session.post(
            f"{self.base_url}/api/{action}", json=params, allow_redirects=False
        ) as response:
            if response.status != 200:
                raise RuntimeError(f"Milky {action}: HTTP {response.status}")
            result = await response.json()
        if result.get("status") != "ok" or result.get("retcode", 0) != 0:
            raise RuntimeError(
                f"Milky {action} failed (retcode={result.get('retcode')})"
            )
        return result.get("data") or {}

    async def get_record(self, file: str, out_format: str = "mp3") -> dict:
        """Resolve incoming audio for plugins that previously used NapCat.

        Args:
            file: A resource URL or Milky resource ID.
            out_format: Desired audio format.

        Returns:
            A local audio file under the conventional ``file`` key.
        """
        if not file.startswith(("http://", "https://", "file://", "base64://")):
            result = await self.call_action("get_resource_temp_url", resource_id=file)
            file = result["url"]
        path = await MediaResolver(file, media_type="audio").to_path(
            target_format=out_format
        )
        return {"file": path}

    async def convert_segments(self, segments: list, depth: int = 0) -> list:
        """Translate incoming segments, including nested quoted messages.

        Args:
            segments: Native incoming Milky segments.
            depth: Current quotation nesting depth.

        Returns:
            AstrBot message components in their original order.
        """
        components = []
        for segment in segments:
            kind, data = segment.get("type"), segment.get("data") or {}
            match kind:
                case "text":
                    components.append(Plain(data.get("text", "")))
                case "mention":
                    components.append(At(qq=str(data["user_id"])))
                case "mention_all":
                    components.append(AtAll())
                case "face":
                    components.append(Face(id=int(data["face_id"])))
                case "image" | "record" | "video":
                    url = data.get("temp_url")
                    if not url:
                        resource = await self.call_action(
                            "get_resource_temp_url", resource_id=data["resource_id"]
                        )
                        url = resource["url"]
                    component_cls = {"image": Image, "record": Record, "video": Video}[
                        kind
                    ]
                    components.append(component_cls(file=url, url=url))
                case "reply" if depth < 4:
                    chain = await self.convert_segments(
                        data.get("segments", []), depth + 1
                    )
                    components.append(
                        Reply(
                            id=str(data["message_seq"]),
                            sender_id=str(data.get("sender_id", "")),
                            sender_nickname=data.get("sender_name", ""),
                            time=data.get("time", 0),
                            chain=chain,
                            message_str="".join(
                                c.text for c in chain if isinstance(c, Plain)
                            ),
                        )
                    )
                case "forward":
                    components.append(Forward(id=data["forward_id"]))
                    if preview := data.get("preview"):
                        components.append(Plain("\n".join(preview)))
                case "file":
                    components.append(
                        Plain(f"[File: {data.get('file_name', 'attachment')}]")
                    )
                case "light_app":
                    components.append(Plain(data.get("app_name") or "[App card]"))
        return components

    async def handle_event(self, payload: dict) -> None:
        """Submit an incoming message without confusing notices with messages.

        Args:
            payload: A Milky WebSocket event envelope.
        """
        if payload.get("event_type") != "message_receive":
            if payload.get("event_type") == "bot_offline":
                self.record_error("Milky reports that the bot is offline")
            return
        data = payload["data"]
        if str(data["sender_id"]) == str(payload["self_id"]):
            return
        scene = data["message_scene"]
        if scene not in ("friend", "group"):
            return
        message = AstrBotMessage()
        message.self_id = str(payload["self_id"])
        message.type = (
            MessageType.GROUP_MESSAGE
            if scene == "group"
            else MessageType.FRIEND_MESSAGE
        )
        member = (
            data.get("group_member") if scene == "group" else data.get("friend")
        ) or {}
        message.sender = MessageMember(
            str(data["sender_id"]),
            member.get("card") or member.get("nickname") or str(data["sender_id"]),
        )
        if scene == "group":
            message.group_id = str(data["peer_id"])
            message.group.group_name = (data.get("group") or {}).get("group_name")
        message.session_id = str(data["peer_id"])
        message.message_id = str(data["message_seq"])
        message.timestamp = data.get("time", payload["time"])
        message.raw_message = payload
        message.message = await self.convert_segments(data.get("segments", []))
        message.message_str = "".join(
            c.text for c in message.message if isinstance(c, Plain)
        )
        self.commit_event(MilkyMessageEvent(message, self))

    async def send_by_session(
        self, session: MessageSession, message_chain: MessageChain
    ) -> None:
        """Send replies or proactive messages using the destination session.

        Args:
            session: Persistent destination session.
            message_chain: Components to send.
        """
        is_group = session.message_type == MessageType.GROUP_MESSAGE
        # Group sessions can include the sender when per-member isolation is enabled.
        peer_id = int(
            session.session_id.split("_")[-1] if is_group else session.session_id
        )
        segments = []
        for component in message_chain.chain:
            if isinstance(component, Plain):
                segments.append({"type": "text", "data": {"text": component.text}})
            elif isinstance(component, At):
                segments.append(
                    {"type": "mention", "data": {"user_id": int(component.qq)}}
                )
            elif isinstance(component, AtAll):
                segments.append({"type": "mention_all", "data": {}})
            elif isinstance(component, Reply):
                segments.append(
                    {"type": "reply", "data": {"message_seq": int(component.id)}}
                )
            elif isinstance(component, Face):
                # Lagrange.Milky currently has no outgoing face segment converter.
                segments.append(
                    {"type": "text", "data": {"text": f"[QQ表情:{component.id}]"}}
                )
            elif isinstance(component, Image | Record | Video):
                if isinstance(component, Image | Record):
                    encoded = await component.convert_to_base64()
                else:
                    path = Path(await component.convert_to_file_path())
                    encoded = base64.b64encode(
                        await asyncio.to_thread(path.read_bytes)
                    ).decode()
                kind = (
                    "image"
                    if isinstance(component, Image)
                    else "record"
                    if isinstance(component, Record)
                    else "video"
                )
                media = {"uri": f"base64://{encoded}"}
                if kind == "image":
                    media["sub_type"] = "normal"
                segments.append({"type": kind, "data": media})
            elif isinstance(component, File):
                raise ValueError(
                    "Milky file uploads must use the native upload_private_file or upload_group_file API"
                )
            else:
                raise ValueError(
                    f"Unsupported outgoing Milky component: {type(component).__name__}"
                )
        if segments:
            await self.call_action(
                "send_group_message" if is_group else "send_private_message",
                **{"group_id" if is_group else "user_id": peer_id, "message": segments},
            )
            await super().send_by_session(session, message_chain)

    async def run(self) -> None:
        try:
            while not self._stopping.is_set():
                try:
                    login = await self.call_action("get_login_info")
                    self.client_self_id = str(login["uin"])
                    parsed = urlsplit(self.base_url)
                    ws_url = (
                        parsed._replace(
                            scheme="wss" if parsed.scheme == "https" else "ws"
                        ).geturl()
                        + "/event"
                    )
                    async with self._session.ws_connect(ws_url, heartbeat=30) as socket:
                        self.clear_errors()
                        logger.info(
                            "Milky event connection established for %s",
                            self.client_self_id,
                        )
                        async for frame in socket:
                            if self._stopping.is_set():
                                break
                            if frame.type == aiohttp.WSMsgType.TEXT:
                                try:
                                    await self.handle_event(json.loads(frame.data))
                                except Exception as exc:
                                    logger.warning(
                                        "Milky event rejected (%s)", type(exc).__name__
                                    )
                            elif frame.type in (
                                aiohttp.WSMsgType.ERROR,
                                aiohttp.WSMsgType.CLOSED,
                            ):
                                break
                    if self._stopping.is_set():
                        break
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    logger.warning(
                        "Milky connection unavailable (%s); retrying in 5 seconds",
                        type(exc).__name__,
                    )
                try:
                    await asyncio.wait_for(self._stopping.wait(), timeout=5)
                except asyncio.TimeoutError:
                    pass
        finally:
            if self._session and not self._session.closed:
                await self._session.close()

    async def terminate(self) -> None:
        self._stopping.set()
        if self._session and not self._session.closed:
            await self._session.close()
