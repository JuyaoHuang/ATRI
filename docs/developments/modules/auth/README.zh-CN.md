---
status: active
owner: auth
created: 2026-07-09
updated: 2026-07-09
---

# Auth 模块长期设计

本目录保存认证模块的长期设计。用户侧配置入口仍是 [认证系统使用指南](../../../configs/CN/认证系统使用指南.md)。

## 当前文档

| 文档 | 内容 |
| --- | --- |
| [design.zh-CN.md](design.zh-CN.md) | GitHub OAuth、JWT、本地模式、部署模式、前端路由守卫和 WebSocket token 的模块设计。 |
| [design.en-US.md](design.en-US.md) | English version of the authentication module design. |

## 相关协议

| 文档 | 内容 |
| --- | --- |
| [../../api/auth.zh-CN.md](../../api/auth.zh-CN.md) | 认证 REST API、鉴权规则和 WebSocket token 约定。 |
| [../../api/auth.en-US.md](../../api/auth.en-US.md) | English version of authentication REST API and WebSocket token conventions. |

## 收录规则

这里收录跨版本仍应遵守的认证边界、登录流程和安全约束。OAuth App 创建步骤、`.env` 填写方式和部署排障继续放在 `docs/configs/CN/认证系统使用指南.md`。
