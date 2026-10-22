# 架构设计

> 本文描述 Proteus 的分层、各层职责、模块边界与数据流。它解释**为什么这么切**，不只是**切成了什么**。

## 1. 设计约束

以下四条约束决定了整个架构，任何设计选择都要先满足它们：

| # | 约束 | 推论 |
|---|---|---|
| C1 | **不维护 Chromium 内核** | 必须有 `KernelAdapter` 抽象；内核是可替换的外部依赖 |
| C2 | **指纹必须可复现** | 派生过程必须是纯函数，输入 `(seed, geo)`，输出确定 |
| C3 | **指纹必须自洽** | 派生之后必须过一致性规则集；不一致视为缺陷而非随机 |
| C4 | **环境必须真正隔离** | 每 Profile 独立 `user-data-dir`、独立 cache、独立扩展、独立 machine-id |

## 2. 分层

```
┌───────────────────────────────────────────────────────────────┐
│  L4  接入层      CLI  ·  HTTP API  ·  Web 管理台  ·  SDK      │
├───────────────────────────────────────────────────────────────┤
│  L3  编排层      Profile 生命周期 · 调度 · 端口/进程池 · 审计  │
├───────────────────────────────────────────────────────────────┤
│  L2  领域层      指纹引擎  ·  代理编排  ·  存储隔离            │
├───────────────────────────────────────────────────────────────┤
│  L1  适配层      KernelAdapter:  chromium | camoufox | pw     │
├───────────────────────────────────────────────────────────────┤
│  L0  内核        外部二进制（不由本项目维护）                  │
└───────────────────────────────────────────────────────────────┘
```

**依赖方向严格向下**：L3 可以调 L2/L1，L1 不认识 L2。`fingerprint` 模块**不 import 任何内核代码**，它是纯计算。这条保证了指纹引擎可以脱离浏览器单独测试和验证。

## 3. L2 领域层

### 3.1 指纹引擎 `proteus.fingerprint`

三段式：**派生 → 校验 → 注入**。

```
seed ──┐
       ├──► derive() ──► Fingerprint ──► check() ──► [Violation] ──► 拒绝启动
geo  ──┘                                   │
                                           └──► 通过 ──► to_kernel_spec()
```

#### 派生 `derive.py`

不用 `random` 模块。每个字段独立计算：

```python
index = int.from_bytes(sha256(f"{seed}:{field}")[:8], "big") % len(choices)
```

好处：
- **跨版本稳定** —— CPython 的 `random.Random(seed)` 在版本间不保证一致，SHA-256 保证
- **字段独立** —— 新增一个字段不会改变已有字段的取值（避免升级后所有 Profile 指纹漂移）
- **可审计** —— 任意字段可手算复现

字段分两类：

| 类别 | 来源 | 字段 |
|---|---|---|
| **geo 派生**（不由 seed 决定） | 代理出口 IP | `country` `timezone` `locale` `languages` |
| **seed 派生** | seed | `os_family` `platform` `ua` `ua_major` `screen_*` `dpr` `hardware_concurrency` `device_memory` `webgl_*` `font_profile` `noise` |

**geo 优先**：时区、语言不能随机。代理在德国就是 `Europe/Berlin` + `de-DE`，这是硬约束，seed 无权干涉。

#### 校验 `consistency.py`

规则集，每条规则是一对多的"字段值域约束"。当前实现的核心规则：

| 规则码 | 检查内容 |
|---|---|
| `os.platform_mismatch` | `os_family` 与 `platform`（`navigator.platform`）匹配 |
| `os.ua_mismatch` | `os_family` 与 UA 字符串中的 OS token 匹配 |
| `os.font_profile_mismatch` | 字体集与 OS 匹配（给了 Windows UA 却量出 macOS 字体是典型破绽） |
| `os.webgl_vendor_mismatch` | WebGL vendor 与 OS 匹配 |
| `os.dpr_implausible` | macOS 的 DPR 不应低于 2 |
| `ua.major_mismatch` | `ua_major` 与 UA 字符串中的版本号一致 |
| `hardware.concurrency_range` | `hardwareConcurrency` 在 2–64 且为偶数 |
| `hardware.device_memory_range` | `deviceMemory` 在 {1,2,4,8}（Chromium 封顶 8） |
| `screen.geometry` | 宽高为正、宽 ≥ 高、与 DPR 组合合理 |
| `locale.language_mismatch` | `languages[0]` 的语言子标签与 `locale` 一致 |
| `geo.timezone_format` | 时区为 IANA 名或 UTC |
| `noise.canvas_range` | Canvas 噪声落在 -128..127 带宽内 |
| `noise.audio_range` | AudioContext 噪声 < 1e-4，不改变可听输出 |

返回 `Violation(code, severity, message)`。`severity="fatal"` 的任意一条都会阻止 Profile 启动——**宁可起不来，也不要起一个会被一眼识破的浏览器**。

规则集是**可扩展的公共接口**：检测技术演进时，新规则加进来，老规则保留为回归测试。

#### 注入 `to_kernel_spec()`

把 `Fingerprint` 翻译成内核能吃的形式（命令行参数、首帧注入脚本、prefs 文件）。不同内核消费方式不同，所以注入逻辑放在 `kernel/` 而不是 `fingerprint/`——领域层只负责"什么是对的"，适配层负责"怎么塞进去"。

### 3.2 代理编排 `proteus.proxy`

职责：

1. **代理池** —— 自有 IP / 住宅代理 / SOCKS5 / HTTP，每 Profile 绑定一个出口
2. **连通性探测** —— 启动前验证代理可用
3. **geoIP 反查** —— 出口 IP → 国家/城市/时区/locale，喂给指纹引擎
4. **出口一致性守卫** —— 启动后回查实际出口 IP 是否漂移（住宅代理会掉线换 IP）；漂移且 geo 变化时**必须重新派生指纹**，否则时区就和 IP 对不上了

第 4 点是最容易被忽略的工程点。商业产品里"指纹和 IP 对不上"是最高频的翻车原因。

### 3.3 存储隔离 `proteus.profile`

一个 Profile 对应磁盘上一个目录：

```
~/.proteus/profiles/<profile_id>/
├─ meta.json          # seed, geo, 代理绑定, 创建时间, 状态
├─ chromium/          # user-data-dir（cookie / localStorage / indexedDB / cache）
├─ extensions/        # 该环境专属扩展
└─ logs/
```

隔离要求：`--user-data-dir` 独立、`--disk-cache-dir` 独立、禁用跨环境共享的 GPU shader cache、每环境独立进程组（便于精确 kill）。

## 4. L1 适配层

```python
class KernelAdapter(Protocol):
    name: str
    def preflight(self) -> None: ...          # 二进制存在、版本可接受
    def launch(self, spec: KernelSpec) -> Session: ...
    def verify(self, session: Session) -> list[Violation]: ...  # 回读真实字段比对模型
```

`verify()` 是这套架构的关键闭环：启动后**真的去 `navigator` 里读一遍**，跟模型比对，不匹配就当失败。没有这一步，"指纹一致性"只是纸面承诺。

内置后端计划：

| 适配器 | 内核 | 适用 |
|---|---|---|
| `ChromiumAdapter` | `fingerprint-chromium` | 默认。兼容性最好，C++ 层改指纹 |
| `CamoufoxAdapter` | Camoufox（Firefox） | 反检测要求最高时 |
| `PlaywrightAdapter` | patchright | 零编译，开发/测试用 |

## 5. L3 编排层

- **进程池** —— N 个环境并行，每环境独立端口（CDP `--remote-debugging-port`）与临时目录
- **生命周期** —— `created → starting → running → stopped / failed`，异常时保证回收子进程和数据目录锁
- **审计** —— 谁在什么时候启动了哪个环境、绑定哪个代理（团队协作模块的基础）

## 6. L4 接入层

- **HTTP API**（FastAPI）：`POST /profiles` `POST /profiles/{id}/start` `GET /profiles/{id}/cdp` `DELETE /profiles/{id}`
- **CDP 端点**：返回 `ws://127.0.0.1:<port>/devtools/browser/<id>`，用户直接接 Playwright/Puppeteer/Selenium
- **CLI**：`proteus create --seed 123 --country DE --proxy socks5://...`
- **安全**：API 只绑 `127.0.0.1`，带 token；默认不开外网

## 7. 一次启动的完整数据流

```
CLI/API 请求
   │
   ▼
[L3] 校验代理连通性 ──► [L2 proxy] 出口 IP ──► geoIP ──► GeoProfile
   │
   ▼
[L2 fingerprint] derive(seed, geo) ──► Fingerprint
   │
   ▼
[L2 fingerprint] check(fp) ──► 有 fatal？ ──► 拒绝启动，返回违规列表
   │                                     └──► 无 ──┐
   ▼                                              │
[L1] adapter.launch(spec(fp)) ◄───────────────────┘
   │
   ▼
[L1] adapter.verify(session) ──► 回读真实 navigator 字段 ──► 与 fp 比对
   │
   ▼
[L3] 返回 CDP ws 端点 + 审计记录
```

## 8. 明确不做的事

- **不做内核 fork**（ADR-0001）
- **不承诺"永不被检测"**——军备竞赛是持续的，见 [THREAT-MODEL.md](THREAT-MODEL.md)
- **不内置代理销售** —— 只做代理**接入与编排**，不做 IP 资源生意
- **不做指纹"随机化"开关** —— 只有一致性

## 9. 待定问题

1. **`verify()` 的可信度**：JS 回读本身可能被内核 patch 影响，需要一个"干净回读通道"（比如脱离页面上下文的 CDP `Runtime.evaluate`），待 M1 验证
2. **多版本共存**：同时跑 Chromium 和 Firefox 内核时，Profile 目录结构是否需要区分
3. **指纹库来源**：真实设备采样 vs 公开统计。倾向先用公开统计做合理分布，避免造假数据
4. **`noise` 类字段的可复现性**：Canvas/Audio 噪声如果是逐会话随机，会破坏"同一 Profile 指纹稳定"的承诺——必须由 seed 确定性生成
