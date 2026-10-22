# Proteus

> **自托管的开源指纹浏览器内核与编排框架。**
> 让"每个 Profile 都是一台自洽的真实设备"成为可复现、可验证、可自动化的工程问题。

<p align="left">
<img alt="status" src="https://img.shields.io/badge/status-M0%20design%20%2B%20core-8a2be2">
<img alt="license" src="https://img.shields.io/badge/license-AGPL--3.0-blue">
<img alt="python" src="https://img.shields.io/badge/python-3.9%2B-3776ab">
</p>

**English** — Proteus is an open-source, self-hostable anti-detect browser core and orchestration framework. It derives a fully self-consistent browser fingerprint from a single seed plus a proxy's geolocation, isolates every profile on disk, and exposes everything over a local API. Licensed AGPL-3.0; commercial licensing available. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design and [docs/ACCEPTABLE-USE-POLICY.md](docs/ACCEPTABLE-USE-POLICY.md) for what this project will not help you do.

---

## 为什么做这个

今天的市场是两极的：

| 层 | 代表 | 问题 |
|---|---|---|
| 反检测库 | patchright / Camoufox / nodriver / botasaurus | 解决"单个会话不被识别"，不解决"管理上百个隔离环境" |
| 商业指纹浏览器 | AdsPower / Multilogin / Dolphin{anty} / Octo / Kameleo | 好用但闭源、不能自托管、数据在别人服务器、按环境数收费 |

**中间缺一层**：一套开源、可自托管、能管理几十到几百个隔离环境、每个环境指纹自洽、并且能被自动化驱动的编排框架。

Proteus 补的就是这一层。它不重造内核，它把内核、指纹一致性、代理编排、环境隔离、团队协作拧成一个能跑的系统。

## 三个核心观点

### 1. 一致性 > 随机性

检测器不关心你的指纹有多稀有，它关心你**自相矛盾**。一个 `Windows NT 10.0` 的 UA，配 macOS 的字体集、`false` 的 `navigator.webdriver` 之外的 20 个 JS 泄漏点、`UTC+8` 的时区、和落在法兰克福的代理 IP —— 这些任意一处对不上，就结束。

随机的指纹不是"更安全"，是**更容易撞出矛盾**。所以 Proteus 追求的是**自洽且稳定**：同一个 Profile，今天和明天的指纹完全一致；换 Profile，整套参数一起换。

### 2. 一个 seed 派生一切

```
seed + 代理地理位置  ──►  一致性指纹模型  ──►  内核注入 + 环境配置
```

所有参数（OS、UA、Client Hints、屏幕、DPR、CPU 核数、内存、WebGL vendor/renderer、字体集、Canvas/Audio 噪声、时区、locale、语言列表）都从 `(seed, proxy_geo)` 通过 SHA-256 确定性派生：

- **可复现** —— 同 seed 在任何机器、任何 Python 版本上产出同一指纹（不依赖 `random` 模块内部实现）
- **可审计** —— 想知道某环境为什么是这套参数，直接重算
- **可校验** —— 派生的结果必须通过一致性规则集，不通过就是 bug，不是"随机到了"

### 3. 不 fork 内核

自己 patch Chromium 的 C++ 代码是**吞金兽**：Chromium 每月一个大版本，你的 patch 集每次都要 rebase，团队得养 3–5 个全职内核工程师。这不是一个人或小团队能长期扛的。

Proteus 走 **内核适配层（kernel adapter）** 路线：定义统一的 `KernelAdapter` 接口，背后可切换

- `fingerprint-chromium`（Chromium fork，C++ 层改指纹，兼容性最好）
- `Camoufox`（Firefox fork，C++ 层改指纹，反检测最强）
- `patchright`（Playwright patch，零编译，最快跑通）

内核的维护交给上游，Proteus 负责编排、一致性、隔离和协作。详见 [ADR-0001](docs/adr/0001-kernel-strategy.md)。

## 当前状态

**M0 —— 设计定稿 + 指纹核心可运行。** 内核接入、图形界面、团队协作还在路线图上（见 [docs/ROADMAP.md](docs/ROADMAP.md)）。

已经能跑的：确定性指纹派生 + 一致性校验器 + 单元测试。这是整个项目的**判断核心**，也是最先该对的东西——如果指纹模型不自洽，后面套什么内核都白搭。

## 仓库结构

```
Proteus/
├─ src/proteus/
│  ├─ fingerprint/       # 核心：seed -> 指纹模型 -> 一致性校验   ← M0 已实现
│  │  ├─ model.py        #   数据模型（Fingerprint / GeoProfile / Violation）
│  │  ├─ derive.py       #   确定性派生（SHA-256 逐字段，stdlib only）
│  │  └─ consistency.py  #   一致性规则集
│  ├─ kernel/            # 内核适配层：chromium / camoufox / playwright   ← M1
│  ├─ proxy/             # 代理池、连通性探测、geoIP -> 时区/locale 推导   ← M2
│  ├─ profile/           # 环境生命周期与磁盘隔离                        ← M2
│  ├─ api/               # 本地 HTTP API + CDP 端点暴露                  ← M3
│  └─ cli/               # proteus create / run / list                  ← M3
├─ tests/                # 单元测试（stdlib unittest，零依赖）
├─ docs/                 # 架构、路线图、威胁模型、AUP、ADR
└─ .github/workflows/    # CI
```

## 快速开始

核心零第三方依赖，纯标准库。

```bash
git clone https://github.com/yushui2022/Proteus.git
cd Proteus

# 跑测试 —— 什么都不用装
python -m unittest discover -s tests -v

# 想在自己的代码里 import proteus（本包本身零依赖）
pip install -e .
```

```python
from proteus.fingerprint import GeoProfile, derive, check

geo = GeoProfile.for_country("DE")          # 或直接传时区/locale
fp = derive(seed=20250922, geo=geo)

print(fp.os_family, fp.platform, fp.ua_major)
print(fp.timezone, fp.languages)
print(fp.screen_width, fp.screen_height, "@", fp.device_pixel_ratio)

violations = check(fp)
assert not violations, violations           # 派生结果必须自洽
```

同一个 `seed` 永远得到同一个指纹：

```python
assert derive(seed=20250922, geo=geo) == derive(seed=20250922, geo=geo)
```

`GEO` 目前只内置了少量国家样例（用于让一致性检查有意义），完整的 geoIP 库化在 M2。**代理的位置决定时区/locale，不由随机决定**——这是本项目最重要的一条约束。

## 路线图摘要

| 里程碑 | 内容 | 退出标准 |
|---|---|---|
| **M0** 指纹核心 | 确定性派生 + 一致性规则 + 测试 | 500 个 seed 全通过；注入矛盾能被捕获 |
| **M1** 内核接入 | `KernelAdapter` + Chromium 后端 | 起真浏览器，`navigator` 全字段与模型一致 |
| **M2** 环境与代理 | Profile 磁盘隔离 + 代理池 + geoIP 推导 | 两环境 cookie/存储/指纹互不可见 |
| **M3** API 与 CLI | 本地 API、CDP 端点、命令行 | 一条命令拉起并自动化接入 |
| **M4** 团队协作 | 成员/权限/共享/审计（闭源模块候选） | — |

完整内容见 [docs/ROADMAP.md](docs/ROADMAP.md)。

## 可接受使用政策（摘要）

Proteus 面向**合法**的多环境场景：跨境店铺运营、广告投放与质量检查、QA 自动化、多账号合规管理、隐私研究与安全测试、反爬策略验证。

**明确禁止**：账号盗用与批量注册、支付欺诈、薅羊毛与优惠滥用、刷量与虚假流量、DDoS、绕过他人访问控制、任何违反目标站点服务条款的自动化。详见 [docs/ACCEPTABLE-USE-POLICY.md](docs/ACCEPTABLE-USE-POLICY.md)。

违反上述条款的使用与本项目无关，作者不提供任何形式的技术支持。

## 参与贡献

欢迎。请先读 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md)——**能提供"某检测点在这里被识破了"的可复现证据，是最有价值的贡献**。

## 许可证

**AGPL-3.0**（见 [LICENSE](LICENSE)）。

简单说：你可以自由使用、修改、分发，但如果你把它作为网络服务提供给他人，**你必须公开你的修改**。这条是为了防止有人拿开源成果做闭源 SaaS 直接竞争。

需要闭源商用授权，或有企业需求（私有协议、SSO、审计、定制内核），请联系维护者。

## 名词

- **Fingerprint** —— 浏览器向站点暴露的全部特征集合的总和
- **Profile / 环境** —— 一套独立的指纹 + 独立的磁盘存储 + 独立的代理，等价于"一台设备"
- **一致性（consistency）** —— 指纹各字段之间不互相矛盾
- **seed** —— 决定一个 Profile 全部指纹参数的整数种子
- **geo** —— 代理出口 IP 的地理位置，决定时区、locale、语言
