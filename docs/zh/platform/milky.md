# 接入 Milky（Lagrange V2）

启动 [Lagrange.Milky](https://lagrangedev.github.io/Lagrange.Milky.Document/) 并完成 QQ 扫码登录。最新 V2 源码位于 [Lagrange.Core](https://github.com/LagrangeDev/Lagrange.Core)。

在 AstrBot 的「机器人」页面创建 `Milky (Lagrange V2)` 实例，填写服务根地址（例如 `http://127.0.0.1:3000`）以及 Lagrange 配置里的 `Milky.AccessToken`。此处使用的是服务访问凭证，Signer token 只配置在 Lagrange 中。

也可在 `data/cmd_config.json` 的 `platform` 数组中添加：

```json
{
  "id": "milky",
  "type": "milky",
  "enable": true,
  "milky_url": "http://127.0.0.1:3000",
  "milky_token": "your-milky-access-token"
}
```

AstrBot 通过 `/api/<action>` 调用 HTTP API，通过 `/event` 订阅 WebSocket 事件；连接中断后每 5 秒重试。地址不要包含 `/api` 或 `/event`。若跨机器部署，请使用可达地址；媒体发送使用 base64，不要求两端共享文件系统。

支持私聊、群聊、@、图片、语音、视频、引用及主动发送消息。消息通知不会被当作普通聊天处理，机器人自己的消息会被忽略。插件可通过 `event.bot.call_action()` 调用原生 Milky API，或通过 `event.bot.get_record()` 下载并转换语音（需要 ffmpeg 和相应解码依赖）。

发送语音时会先转换为 Tencent SILK，包括 TTS 提供商生成的 WAV 音频，确保 QQ 可以正常播放并识别时长。

QQ 原生表情使用标准 Milky `face` 消息段，`face_id` 为字符串，`is_large` 默认为 `false`。需要部署包含原生表情补丁的 Lagrange V2：旧版表情（如流泪）和新版表情（如旺柴）均可收发；超级表情暂只支持接收。大肥鱼插件应启用原有的文字转表情逻辑，移除先前针对 Milky 的提前返回。

合并转发和文件暂不经过通用消息链发送；文件可通过原生 `upload_private_file` / `upload_group_file` 接口发送。依赖 OneBot 专有接口或事件结构的插件需要单独适配。视觉、语音识别及 TTS 仍需配置对应模型 API。
