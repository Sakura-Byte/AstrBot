# Connect Milky (Lagrange V2)

Start [Lagrange.Milky](https://lagrangedev.github.io/Lagrange.Milky.Document/) and complete QQ login. Current V2 sources are maintained in [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core).

Create a `Milky (Lagrange V2)` bot in the Dashboard. Set `milky_url` to the service root, such as `http://127.0.0.1:3000`, and `milky_token` to `Milky.AccessToken` from the Lagrange configuration. The signing token belongs only in Lagrange; it is a separate credential.

The adapter calls `/api/<action>` over HTTP and subscribes to `/event` over WebSocket, reconnecting every five seconds. Do not include either path in the service URL. Media is sent as base64, so the services do not need a shared filesystem.

Private and group messages, mentions, images, audio, video, quotes, and proactive messages are supported. Self messages and non-message notifications do not enter chat processing. Plugins can call native APIs through `event.bot.call_action()` and retrieve audio through `event.bot.get_record()`; audio conversion requires ffmpeg and the relevant codecs.

Outgoing voice recordings, including WAV output from TTS providers, are encoded as Tencent SILK before upload so QQ can play them with the correct duration.

Native QQ faces use the standard Milky `face` segment with a string `face_id` and `is_large: false`. Deploy the patched Lagrange V2 core and Milky converter to send and receive both legacy and modern system faces. Animated large faces are receive-only. Enable Dafeiyu's original text-to-face conversion by removing the previous early return for Milky.

Forwarded messages and files are not sent through generic message chains; native file upload APIs remain available. Plugins using OneBot-specific APIs require adaptation. Vision, speech recognition, and TTS require separate model credentials.
