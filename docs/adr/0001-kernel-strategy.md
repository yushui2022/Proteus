# ADR-0001：不 fork Chromium 内核，改用适配层

- **状态**：已接受
- **日期**：2025-09
- **决策者**：维护者
- **相关**：[ARCHITECTURE.md](../ARCHITECTURE.md) §4、[ROADMAP.md](../ROADMAP.md) M1

## 背景

指纹浏览器要真正"改对"指纹，绝大部分字段只能在浏览器内核的 **C++ 层**修改。JS 注入（`Page.addScriptToEvaluateOnNewDocument`、`Object.defineProperty` 覆盖）会被以下手段逐一打穿：

- `Function.prototype.toString()` 检测原生函数被替换
- `Error().stack` 里的文件路径与行号异常
- iframe / Worker / SharedWorker 上下文重注入
- `Symbol.toStringTag`、`Object.getOwnPropertyDescriptor` 比对
- 属性 descriptor 的 `configurable`/`enumerable` 与原生不一致

因此存在一个看似显然的选项：**自己 fork Chromium，在 C++ 层改。**

## 决策

**不 fork。** 采用 `KernelAdapter` 适配层，内核作为外部可替换依赖，候选：

- `fingerprint-chromium`（Chromium fork，C++ 层改 JS 可见指纹，不动网络栈）
- `Camoufox`（Firefox fork，C++ 层改指纹，反检测强度最高）
- `patchright`（Playwright 补丁，零编译，仅用于开发与测试）

## 理由

### 1. 维护成本不可承受

Chromium 大约每 4 周一个大版本。自研 C++ 指纹补丁集每次都要 rebase 到新内核，冲突点集中在渲染、GPU、字体、网络栈这些最不稳定的区域。商业产品（Multilogin 的 Mimic、GoLogin 的 Orbita）为此养着专门的 3–5 人内核团队。

对一个人或小团队而言，这不是"难"，是**数学上不成立**：你花 6 个月做出的内核补丁，18 个月后就跟不上上游了。

### 2. 项目的差异化不在这里

内核解决"单个会话能否被识破"，Proteus 解决"上百个环境能否被正确管理、且每个都自洽"。后者才是市场缺口（见 README「为什么做这个」），也是更适合开源社区协作的层次。

### 3. 上游已经做对了

`fingerprint-chromium` 与 Camoufox 都是在 C++ 层做正确的事，且**不动协议栈特征**（这一点极其关键，见 [THREAT-MODEL.md](../THREAT-MODEL.md) §3）。站在它们上面，比自己从零改一遍更可靠。

### 4. 规避上游风险

代价是依赖上游的存续。缓解措施：

- 适配层接口足够窄（`preflight / launch / verify`），换内核成本低
- 至少维护两条可用后端（Chromium + Firefox），避免单一上游风险
- 指纹**模型**完全属于本项目，内核只负责注入——模型不依赖任何内核

## 后果

**正面**
- 团队焦点集中在指纹一致性、编排、协作
- 内核升级由上游承担
- 可同时支持 Chromium（兼容性）与 Firefox（反检测强度）

**负面**
- 受限于上游暴露的注入能力；上游不支持的字段，我们也做不了
- 需处理内核二进制的分发与首次下载体验
- 用户会问"为什么不自己改内核"，需要反复解释

## 备选方案与被否理由

| 方案 | 否掉的理由 |
|---|---|
| 自研 Chromium fork | 维护成本不可承受（见理由 1） |
| 纯 Playwright + patchright | 反检测上限太低，`navigator` 深层字段改不动 |
| 纯 JS 注入（不换内核） | 必然被 `toString`/`stack`/iframe 重注入打穿 |
| 只用 Camoufox | Firefox 兼容性风险，部分站点白名单偏向 Chromium |

## 复核条件

出现以下任一情况时重新评估本决策：

1. `fingerprint-chromium` 与 Camoufox **同时**停止维护超过 6 个月
2. 项目获得稳定的全职投入（≥ 2 人专职内核方向）
3. 上游的内核改造方式被证明无法覆盖超过 40% 的目标指纹字段
