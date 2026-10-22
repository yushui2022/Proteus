# 威胁模型与检测面清单

> 这不是"如何绕过检测"的手册，而是**本项目的技术边界说明书**。
> 它回答一个问题：Proteus 打算在哪些层做正确的事，哪些层明确做不到。

## 0. 一个诚实的前提

**没有任何指纹浏览器能永久保证"不被检测"。** 检测方与规避方是持续的军备竞赛，任何声称"100% 通过"的产品要么在撒谎，要么在卖你一个会过期的快照。

Proteus 的承诺只有一条：**让指纹内部不矛盾，并且这个不矛盾是可验证的。** 至于某个特定风控厂商今天更看重哪个特征，不在承诺范围内。

## 1. 检测面分层

```
┌─────────────────────────────────────────────┐
│ 行为层    鼠标轨迹 / 时序 / 输入事件         │  ← 本项目的空白区
├─────────────────────────────────────────────┤
│ 应用层    JS API 一致性 / 跨上下文泄漏       │  ← 核心战场
├─────────────────────────────────────────────┤
│ 协议层    TLS JA3/JA4 / HTTP2 指纹           │  ← 依赖内核，只能选
├─────────────────────────────────────────────┤
│ 网络层    IP 声誉 / ASN / geo                │  ← 依赖代理质量
└─────────────────────────────────────────────┘
```

## 2. 应用层（本项目主战场）

### 2.1 一致性类（Proteus 负责）

这类检测的本质是"找出字段之间的矛盾"，是 M0 一致性规则集的直接对手。

| 检测点 | 矛盾形态 | Proteus 对策 |
|---|---|---|
| UA vs 字体集 | Windows UA + macOS 字体 | `os.font_profile_mismatch` |
| UA vs `navigator.platform` | `Win32` UA + `MacIntel` | `os.platform_mismatch` |
| UA vs Client Hints | `Chrome/120` vs `sec-ch-ua: "131"` | `ua.major_mismatch` |
| WebGL renderer vs OS | Apple GPU 字符串 + Windows 平台 | `os.webgl_vendor_mismatch` |
| 屏幕 vs DPR | 1920×1080 @ DPR 3 | `screen.geometry` / `os.dpr_implausible` |
| `deviceMemory` 越界 | 报告 16/32 GB | `hardware.device_memory_range` |
| `hardwareConcurrency` 异常 | 报告 3 核 / 128 核 | `hardware.concurrency_range` |
| 语言 vs 时区 | `zh-CN` + `America/New_York`（无代理语境） | geo 驱动的 locale 派生 |
| **时区 vs IP 归属** | 出口在德国，`Intl` 报 UTC+8 | 代理 geoIP → 时区强制推导（M2） |

### 2.2 API 面类（依赖内核层）

| 检测点 | 说明 | 覆盖方式 |
|---|---|---|
| Canvas / WebGL 渲染哈希 | 同硬件同浏览器应稳定；伪造需在渲染层 | 内核 C++ 层（fingerprint-chromium / Camoufox） |
| AudioContext 指纹 | 浮点运算差异 | 同上 |
| 字体枚举（`measureText` / `FontFace` 探测） | 字体集必须与 OS 自洽 | 内核层提供字体集 |
| `Permissions.query` 一致性 | 声明的能力与实际返回值不符 | 内核层 |
| `navigator.webdriver` | 基础项 | 内核层 |
| 插件 / MIME 类型 | Chrome 系应为 PDF 插件集合 | 内核层 |
| WebRTC 本地 IP 泄漏 | `RTCPeerConnection` 暴露内网地址，与公网 IP 矛盾 | 内核层 + 启动参数 |
| `hardwareConcurrency` 真实值 vs 声明值 | 可用 Worker 实测推翻 | 需内核层钳制 |

**关键判断**：2.2 里几乎所有项**只能在 C++ 层做对**。JS 注入（`addScriptToEvaluateOnNewDocument`）能用 `Function.prototype.toString`、`Error.stack`、iframe 重注入、`Symbol.toStringTag` 等手段打穿。这就是为什么 Proteus 不自己实现注入，而是接 `fingerprint-chromium` / Camoufox。

### 2.3 反调试/反自动化特征

| 检测点 | 说明 | 对策 |
|---|---|---|
| `Runtime.enable` 泄漏 | CDP 一旦开 `Runtime.enable`，`Error.stack` 出现异常特征 | 用 patchright 已修补；或避免开 |
| CDP 命令时序指纹 | 注入脚本的执行时机早于/晚于正常 | 由内核层统一注入，不用 CDP 逐页注入 |
| `navigator.webdriver` | — | 内核层 |
| 空白 CDP 页面 / 无痕差异 | `about:blank` 上下文特征 | 内核层 |
| 扩展存在痕迹 | Manifest V3 的 DOM 标记 | 内核层或不用扩展 |
| 鼠标/键盘事件 `isTrusted` | 合成事件 `isTrusted=false` | **空白区**：需真实输入层（如 OS 级注入），本项目不承诺 |

## 3. 协议层（本项目不做，只能选）

TLS ClientHello（JA3/JA4）与 HTTP/2 SETTINGS/优先级指纹在**网络栈**里生成，JS 层完全无感知、无法干预。

含义：
- 用官方 Chrome 内核 → 指纹就是官方 Chrome 的，天然合法
- 用改过的内核 → **必须保证没有改动协议栈特征**，否则一个"合法的 Chrome JA3 + 假的 UA"就是硬矛盾

Proteus 的立场：**协议层不做任何定制**，直接继承内核。这是安全的默认值，也是为什么选 fingerprint-chromium 这类"只改 JS 可见层、不动网络栈"的 fork。

## 4. 网络层（由代理质量决定，本项目只做编排）

| 风险 | 说明 | Proteus 对策 |
|---|---|---|
| IP 声誉 | 数据中心 IP 被大批拉黑 | 不做 IP 生意，但支持住宅代理接入 |
| ASN 异常 | 家用宽带 IP 属于云厂商 ASN | 同上 |
| geo 漂移 | 住宅代理中途换出口，时区突然对不上 | **出口漂移守卫**（M2 硬性要求） |
| 多环境共用 IP | 关联封号的头号原因 | 每 Profile 强制绑定唯一出口 |

## 5. 行为层（明确空白）

鼠标轨迹、点击间隔、页面停留、滚动模式、输入节奏——这些**Proteus 一律不做**。

理由：行为拟真是独立的研究方向（人类轨迹模型、贝塞尔曲线抖动、输入节奏分布），且强依赖具体业务场景。塞进指纹浏览器只会做出一个"看起来能过、实际过不了"的半成品。

需要行为层的用户请自行在自动化层（Playwright/Puppeteer）实现，Proteus 只负责把浏览器交给他们。

## 6. 项目的自我约束

| 约束 | 理由 |
|---|---|
| 不追求"指纹越稀有越好" | 稀有 = 可追踪。目标是**落在真实设备分布内** |
| 不提供"随机指纹"开关 | 随机化必然制造矛盾，见 README 核心观点 1 |
| 不承诺特定风控厂商通过率 | 军备竞赛，不可承诺 |
| 不用 JS 层伪造替代内核层 | JS 层必然被 `toString` / `stack` 打穿 |

## 7. 如何验证（贡献者指南）

任何"这个检测点被识破了"的贡献，请附：

1. **可复现的最小页面**（不要贴整站）
2. **期望值 vs 实际值**（我们模型说应该是 A，实际读到 B）
3. **检测层判断**（应用层 / 协议层 / 行为层）
4. **归因**（是 `derive` 错了，还是 `check` 漏了规则，还是内核没注入进去）

这套四段式能让问题从"好像被检测了"变成"第 3 类字段的第 2 条规则漏了"，才有得修。

常用自测面：
- `bot.sannysoft.com` —— 基础自动化特征
- `abrahamjuliot.github.io/creepjs` —— 综合指纹一致性
- `browserleaks.com/{canvas,webgl,fonts,javascript}` —— 分项
- `pixelscan.net` —— 综合评分
