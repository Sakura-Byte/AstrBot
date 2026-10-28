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

当前 Lagrange.Milky 没有 QQ 原生表情的发送转换器，`Face` 会回退为文本 `[QQ表情:编号]`。合并转发和文件暂不经过通用消息链发送；文件可通过原生 `upload_private_file` / `upload_group_file` 接口发送。依赖 OneBot 专有接口或事件结构的插件需要单独适配。视觉、语音识别及 TTS 仍需配置对应模型 API。
