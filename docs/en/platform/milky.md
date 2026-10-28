# Connect Milky (Lagrange V2)

Start [Lagrange.Milky](https://lagrangedev.github.io/Lagrange.Milky.Document/) and complete QQ login. Current V2 sources are maintained in [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core).

Create a `Milky (Lagrange V2)` bot in the Dashboard. Set `milky_url` to the service root, such as `http://127.0.0.1:3000`, and `milky_token` to `Milky.AccessToken` from the Lagrange configuration. The signing token belongs only in Lagrange; it is a separate credential.

The adapter calls `/api/<action>` over HTTP and subscribes to `/event` over WebSocket, reconnecting every five seconds. Do not include either path in the service URL. Media is sent as base64, so the services do not need a shared filesystem.

Private and group messages, mentions, images, audio, video, quotes, and proactive messages are supported. Self messages and non-message notifications do not enter chat processing. Plugins can call native APIs through `event.bot.call_action()` and retrieve audio through `event.bot.get_record()`; audio conversion requires ffmpeg and the relevant codecs.

Lagrange.Milky currently lacks an outgoing QQ face converter. Faces fall back to `[QQ表情:ID]` text. Forwarded messages and files are not sent through generic message chains; native file upload APIs remain available. Plugins using OneBot-specific APIs require adaptation. Vision, speech recognition, and TTS require separate model credentials.
