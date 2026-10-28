import asyncio
import base64
import wave
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from aiohttp import web

from astrbot.api.event import MessageChain
from astrbot.api.message_components import At, Face, Image, Plain, Record, Reply
from astrbot.api.platform import MessageType
from astrbot.core.platform.message_session import MessageSession
from astrbot.core.platform.sources.milky.milky_adapter import MilkyAdapter
from astrbot.core.utils.metrics import Metric


@pytest_asyncio.fixture
async def service(monkeypatch):
    monkeypatch.setattr(Metric, "upload", AsyncMock())
    calls = []
    app = web.Application()

    async def api(request):
        assert request.headers.get("Authorization") == "Bearer test-secret"
        body = await request.json()
        action = request.match_info["action"]
        calls.append((action, body))
        if action == "fail":
            return web.json_response({"status": "failed", "retcode": 123})
        if action == "unauthorized":
            return web.Response(status=401)
        data = {"uin": 2469731573} if action == "get_login_info" else {"message_seq": 9}
        if action == "get_resource_temp_url":
            data = {"url": "https://example.com/audio.silk"}
        return web.json_response({"status": "ok", "retcode": 0, "data": data})

    async def events(request):
        assert request.headers.get("Authorization") == "Bearer test-secret"
        socket = web.WebSocketResponse()
        await socket.prepare(request)
        await socket.send_json(envelope("friend"))
        async for _ in socket:
            pass
        return socket

    app.router.add_post("/api/{action}", api)
    app.router.add_get("/event", events)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    adapter = MilkyAdapter(
        {
            "id": "milky-test",
            "milky_url": f"http://127.0.0.1:{port}",
            "milky_token": "test-secret",
        },
        {},
        asyncio.Queue(),
    )
    try:
        yield adapter, calls
    finally:
        await adapter.terminate()
        await runner.cleanup()


def envelope(scene):
    return {
        "event_type": "message_receive",
        "time": 100,
        "self_id": 2469731573,
        "data": {
            "message_scene": scene,
            "peer_id": 300 if scene == "group" else 200,
            "sender_id": 200,
            "message_seq": 7,
            "time": 99,
            "friend": {"nickname": "Friend"},
            "group_member": {"nickname": "Nickname", "card": "Group card"},
            "group": {"group_name": "Test group"},
            "segments": [{"type": "text", "data": {"text": "hello"}}],
        },
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("scene", ["friend", "group"])
async def test_receive_identity_and_sessions(service, scene):
    adapter, _ = service
    await adapter.handle_event(envelope(scene))
    event = adapter._event_queue.get_nowait()
    assert event.get_sender_id() == "200"
    assert event.message_obj.timestamp == 99
    assert event.message_obj.self_id == "2469731573"
    assert event.message_str == "hello"
    assert event.get_group_id() == ("300" if scene == "group" else "")
    assert event.get_sender_name() == ("Group card" if scene == "group" else "Friend")
    assert event.bot is adapter


@pytest.mark.asyncio
async def test_self_and_notice_events_are_ignored(service):
    adapter, _ = service
    payload = envelope("friend")
    payload["data"]["sender_id"] = payload["self_id"]
    await adapter.handle_event(payload)
    await adapter.handle_event({"event_type": "message_recall"})
    assert adapter._event_queue.empty()


@pytest.mark.asyncio
async def test_quote_media_and_mentions(service):
    adapter, _ = service
    parts = await adapter.convert_segments(
        [
            {"type": "mention", "data": {"user_id": 123}},
            {"type": "image", "data": {"temp_url": "https://example.com/image.png"}},
            {"type": "record", "data": {"resource_id": "audio"}},
            {
                "type": "reply",
                "data": {
                    "message_seq": 2,
                    "sender_id": 3,
                    "segments": [{"type": "text", "data": {"text": "quoted"}}],
                },
            },
        ]
    )
    assert isinstance(parts[0], At)
    assert parts[1].url == "https://example.com/image.png"
    assert parts[2].file == "https://example.com/audio.silk"
    assert isinstance(parts[3], Reply)
    assert parts[3].message_str == "quoted"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind,session_id,action,key,peer",
    [
        (MessageType.FRIEND_MESSAGE, "200", "send_private_message", "user_id", 200),
        (MessageType.GROUP_MESSAGE, "200_300", "send_group_message", "group_id", 300),
    ],
)
async def test_proactive_send_and_native_faces(
    service, kind, session_id, action, key, peer
):
    adapter, calls = service
    await adapter.send_by_session(
        MessageSession("milky-test", kind, session_id),
        MessageChain([Plain("hello"), At(qq="123"), Reply(id="7"), Face(id=1)]),
    )
    assert calls[-1] == (
        action,
        {
            key: peer,
            "message": [
                {"type": "text", "data": {"text": "hello"}},
                {"type": "mention", "data": {"user_id": 123}},
                {"type": "reply", "data": {"message_seq": 7}},
                {"type": "face", "data": {"face_id": "1", "is_large": False}},
            ],
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("face_id", ["9", "277"])
async def test_receive_native_faces(service, face_id):
    adapter, _ = service
    payload = envelope("friend")
    payload["data"]["segments"] = [
        {"type": "face", "data": {"face_id": face_id, "is_large": False}}
    ]
    await adapter.handle_event(payload)
    event = adapter._event_queue.get_nowait()
    assert isinstance(event.message_obj.message[0], Face)
    assert event.message_obj.message[0].id == int(face_id)


@pytest.mark.asyncio
async def test_image_is_portable_base64(service, monkeypatch):
    adapter, calls = service
    monkeypatch.setattr(Image, "convert_to_base64", AsyncMock(return_value="aW1hZ2U="))
    await adapter.send_by_session(
        MessageSession("milky-test", MessageType.FRIEND_MESSAGE, "200"),
        MessageChain([Image.fromURL("https://example.com/image.png")]),
    )
    assert calls[-1][1]["message"][0]["data"] == {
        "uri": "base64://aW1hZ2U=",
        "sub_type": "normal",
    }


@pytest.mark.asyncio
async def test_tts_wav_is_encoded_as_tencent_silk(service, tmp_path):
    adapter, calls = service
    audio = tmp_path / "tts.wav"
    with wave.open(str(audio), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(24000)
        output.writeframes(b"\x00\x00" * 24000)
    await adapter.send_by_session(
        MessageSession("milky-test", MessageType.FRIEND_MESSAGE, "200"),
        MessageChain([Record(file=str(audio))]),
    )
    segment = calls[-1][1]["message"][0]
    assert segment["type"] == "record"
    payload = base64.b64decode(segment["data"]["uri"].removeprefix("base64://"))
    assert payload.startswith(b"\x02#!SILK_V3")
    assert audio.is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["fail", "unauthorized"])
async def test_api_failures_are_not_success(service, action):
    adapter, _ = service
    with pytest.raises(RuntimeError, match="Milky"):
        await adapter.call_action(action)


@pytest.mark.asyncio
async def test_websocket_receives_and_terminates(service):
    adapter, _ = service
    task = asyncio.create_task(adapter.run())
    try:
        event = await asyncio.wait_for(adapter._event_queue.get(), timeout=3)
        assert event.message_str == "hello"
        await adapter.terminate()
        await asyncio.wait_for(task, timeout=3)
        assert adapter._session.closed
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize(
    "url",
    ["ftp://example.com", "http://u:p@example.com", "http://example.com?token=secret"],
)
def test_invalid_service_urls(url):
    with pytest.raises(ValueError):
        MilkyAdapter({"id": "test", "milky_url": url}, {}, asyncio.Queue())
