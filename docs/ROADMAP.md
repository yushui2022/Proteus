# 路线图

> 原则：**先让指纹"对"，再让浏览器"起得来"，最后才是"好用"**。
> 顺序反过来做（先搞界面、先接内核）的项目，最后都绕回来重写指纹层。

每个里程碑都有明确的**退出标准**——不是"做完了"，是"可以被验证通过"。

---

## M0 · 指纹核心（当前）

**目标**：证明"一个 seed 能派生出真正自洽的指纹"这件事成立，且可被机器验证。

| 工作项 | 状态 |
|---|---|
| `Fingerprint` / `GeoProfile` / `Violation` 数据模型 | ✅ |
| 基于 SHA-256 的逐字段确定性派生（零第三方依赖） | ✅ |
| 一致性规则集（13 条核心规则） | ✅ |
| 单元测试：确定性、差异性、自洽性、矛盾捕获 | ✅ |
| CI（GitHub Actions） | ✅ |
| 内置国家 → 时区/locale 样例表 | ✅ 少量 |

**退出标准**
- [x] 同 `(seed, geo)` 跨进程、跨平台结果完全一致
- [x] 500 个 seed × 3 种 OS 派生结果全部通过一致性检查
- [x] 人为注入的字段矛盾 100% 被 `check()` 捕获
- [ ] 规则集覆盖 UI 指纹面（Canvas/WebGL/Audio）的**数值约束**，而不只是 OS 层

---

## M1 · 内核接入

**目标**：真的起一个浏览器，且它的 `navigator` 和我们的模型一模一样。

**这是全项目风险最高的一步**，因为它决定"一致性"是承诺还是事实。

| 工作项 | 说明 |
|---|---|
| `KernelAdapter` 协议定型 | `preflight / launch / verify` 三方法 |
| `PlaywrightAdapter`（patchright） | 零编译，用来快速打通 `verify()` 闭环 |
| `ChromiumAdapter`（fingerprint-chromium） | 默认后端，需处理二进制分发与首次下载 |
| `to_kernel_spec()` | 模型 → 命令行参数 + 首帧注入脚本 |
| **`verify()` 比对器** | 启动后回读真实 `navigator`，逐字段 diff |

**退出标准**
- 拉起一个环境，在 CreepJS 里读出**我们声明的那一套** OS/screen/DPR/时区/语言，而不是宿主机的
- `verify()` 对故意弄坏的内核返回非空违规
- 至少 1 个公开 bot-detection 测试页（如 `bot.sannysoft.com`）全绿

**风险**：不同内核暴露的注入方式差异极大（Chromium 用 CLI flag，Firefox 用 `prefs.js` + patched build）。适配层接口要能容纳这种差异，不要过早抽象成统一配置。

---

## M2 · 环境隔离与代理编排

**目标**：两个并发环境之间，除了"同一台机器"什么都不能共享。

| 工作项 | 说明 |
|---|---|
| Profile 生命周期管理 | `~/.proteus/profiles/<id>/` + `meta.json` |
| 磁盘隔离 | 独立 `user-data-dir` / cache / 扩展目录 |
| 进程池 | N 环境并行，独立调试端口，精确回收 |
| 代理池 | SOCKS5 / HTTP(S)，每 Profile 绑定一个出口 |
| geoIP → geo 推导 | 出口 IP → 国家/时区/locale/语言，喂给指纹引擎 |
| **出口漂移守卫** | 运行中回查出口 IP；geo 变化则标记环境需重新派生 |

**退出标准**
- 同时起 5 个环境，互相读不到对方 cookie / localStorage / indexedDB
- 每个环境的时区、语言与代理出口国一致
- 代理断线时环境被正确标记，而不是默默用直连继续跑（这是最危险的行为）

---

## M3 · API 与 CLI

**目标**：一条命令拉起环境，一行代码接自动化。

| 工作项 | 说明 |
|---|---|
| CLI | `proteus create / list / start / stop / rm / verify` |
| HTTP API | FastAPI，仅绑 `127.0.0.1`，Bearer token |
| CDP 端点 | `GET /profiles/{id}/cdp` → ws 地址 |
| SDK | 返回 Playwright/Puppeteer 可直接用的连接串 |

**退出标准**
- `proteus create --country DE --proxy socks5://... && proteus start <id>` 一条链跑通
- Playwright `connect_over_cdp()` 接进去后，页面指纹与模型一致（复用 M1 的 `verify()`）

---

## M4 · 团队协作（商业化候选）

这部分是**商业产品的真正护城河**，也是 open-core 里适合闭源的部分。

| 工作项 | 说明 |
|---|---|
| 成员与权限 | 环境归属、只读/可启动/可编辑 |
| 环境共享 | 跨成员共享 Profile，不泄露 seed |
| 操作审计 | 谁在何时启动/修改了哪个环境、绑定什么代理 |
| SSO / 私有部署 | 企业需求 |

---

## 不做 / 长期悬置

| 项目 | 理由 |
|---|---|
| 自研 Chromium 内核 fork | 见 [ADR-0001](adr/0001-kernel-strategy.md)，维护成本不可承受 |
| 内置代理/IP 资源 | 是另一门生意，且涉及合规 |
| 移动端指纹（iOS/Android） | 生态完全不同，不在初期范围 |
| 云手机 / 云浏览器托管 | 重资产，且与"自托管"定位冲突 |
| 承诺"绕过特定风控厂商" | 军备竞赛，不写进产品承诺 |

---

## 版本节奏（暂定）

不使用语义化版本的正式承诺，M0–M3 期间一律 `0.x.y`。
`1.0` 的定义是：**M1 + M2 + M3 退出标准全部满足，且连续 4 周没有 fatal 级一致性回归**。
