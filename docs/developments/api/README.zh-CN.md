# API 与协议文档

本目录保存稳定接口和事件协议文档。

适合放置：

- REST API 协议
- WebSocket 消息协议
- 前后端事件格式
- 错误码和兼容性约定

不适合放置：

- 某次接口改造过程日志
- 模块内部 provider 接口
- 临时验收 payload 记录

协议发生变更时，应同步更新相关 feature 文档和模块设计文档中的引用。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [auth.zh-CN.md](auth.zh-CN.md) | 认证 REST API、HTTP 鉴权规则和 WebSocket token 约定。 |
| [auth.en-US.md](auth.en-US.md) | English version of authentication REST API, HTTP authorization rules, and WebSocket token conventions. |
