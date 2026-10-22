# 内核拆解：开源指纹浏览器到底改了什么

> 本文是对现有开源方案的技术拆解，目的是**决定 Proteus 该做什么、不该做什么**。
> 所有结论都标注了源码位置或实测证据。规则和数据不能引用来源的，不进这份文档。

## 0. 结论先行

| 判断 | 依据 |
|---|---|
| 指纹只能在 **C++ 层**改对，JS 注入必被 `toString`/`stack`/iframe 重注入打穿 | 两个成熟方案无一使用 JS 注入，全部改内核 C++ |
| **协议层（TLS/HTTP2）无人改动** —— 继承官方实现 | 128 个 Chromium 补丁里没有任何 TLS/HTTP2 相关项 |
| Firefox 路线（Camoufox）覆盖的指纹面**显著宽于** Chromium 路线 | 见 §4 覆盖面差距表 |
| 两条路线都**不做**"一致性证明"和"多环境编排" | 见 §6，这是 Proteus 的空间 |
| 一致性规则必须**引用实测**，且应能**修复**而非只是拒绝 | 见 §5，Camoufox `coherence.py` 的做法 |

## 1. 三条技术路线

调研对象（本地已克隆，见 `third_party/`）：

| 项目 | Star | 内核 | 改动层 | 配置方式 | 需自建 |
|---|---|---|---|---|---|
| `adryfish/fingerprint-chromium` | 3.2k | Chromium（基于 ungoogled） | C++ 补丁集 | 命令行开关 | 是 |
| `daijro/camoufox` | 12.7k | Firefox | C++ 补丁集 | 路径寻址配置表 | 是 |
| `kaliiiiiiiiii-Vinyzu/patchright` | 4.9k | 原生 Chrome | 驱动层（改 Playwright 的 CDP 调用） | 无 | 否 |

三种路线不是替代关系，是**不同高度的天花板**：patchright 修的是"驱动留下的痕迹"，两个内核 fork 修的是"浏览器本身说的话"。

## 2. Chromium 路线：fingerprint-chromium

**注意**：主分支 (`main`) **不含补丁代码**。补丁按版本发布在独立分支（如 `148.0.7778.215`），且比发行版延迟约一个月。这是选型时必须计入的风险——你不能立刻审计它当前版本改了什么。

指纹相关补丁共 18 个，位于 `patches/extra/fingerprint/`。

### 2.1 配置如何从命令行进入渲染进程

`000-add-fingerprint-switches.patch` 定义了配置面：

```
--fingerprint=<seed>            --fingerprint-screen-width
--fingerprint-brand             --fingerprint-screen-height
--fingerprint-brand-version     --fingerprint-device-scale-factor
--disable-spoofing              --fingerprint-hardware-concurrency
--fingerprint-platform          --fingerprint-platform-version
--fingerprint-location          --timezone
```

关键在 `content/browser/renderer_host/render_process_host_impl.cc`：这些开关被追加到
`RenderProcessHostImpl::PropagateBrowserCommandLineToRenderer()` 的白名单里。也就是说**浏览器进程解析参数，再把它们转发给每个渲染进程**，每个渲染进程在实现对应 JS API 时读取自己的那份。

一个可复用的设计点：**`--fingerprint=<seed>` 是主种子，其余字段在 C++ 里用 `seed % N` 派生**。见 `021`：

```cpp
static const float kDeviceMemoryValues[] = {8, 16, 32};
return kDeviceMemoryValues[fingerprint % 3];
```

这验证了我们 ADR-0002 的方向（seed 派生），但也暴露了它的弱点：**`seed % N` 无法保证字段之间自洽**，只能保证可复现。他们靠"人工挑选候选值"来兜底，而不是靠规则校验。

### 2.2 每个指纹点改在哪个源码位置

| 指纹点 | 源码文件 | 做法 |
|---|---|---|
| UA + Client Hints | `components/embedder_support/user_agent_utils.cc`、`content/browser/client_hints/client_hints.cc`、`blink/.../navigator_ua.cc` | 改 UA 元数据源，同时改 client hints，保证两者同源 |
| `deviceMemory` | `blink/core/frame/navigator_device_memory.cc` | 按 seed 取 `{8,16,32}` |
| `hardwareConcurrency` | `blink/core/frame/navigator_concurrent_hardware.cc` | 同上 |
| WebGL vendor/renderer | `blink/modules/webgl/webgl_rendering_context_base.cc`、`webgl2_rendering_context_base.cc`、新增 `webgl_fingerprint.cc/.h` | 拦截 `getParameter`，用独立的 GPU 数据表 |
| Canvas imageData | `blink/modules/canvas/canvas2d/base_rendering_context_2d.cc`、`platform/graphics/image_data_buffer.cc` | 在**像素缓冲区**层加噪，不在 JS 返回值上加 |
| Canvas toDataURL | `blink/core/html/canvas/html_canvas_element.cc` | 同源加噪，避免两条路径不一致 |
| measureText | `blink/modules/canvas/canvas2d/base_rendering_context_2d.cc` | 文本宽度加噪 |
| ClientRects | `blink/core/dom/document.cc`、`element.cc`、`range.cc`、`ui/gfx/geometry/quad_f.cc` | 连**几何计算**都加噪（不是只改 `getBoundingClientRect` 的返回） |
| 字体 | `blink/platform/fonts/font_cache.cc` | 改字体缓存层 |
| Audio | `blink/modules/webaudio/offline_audio_context.cc` | `OfflineAudioContext` 层 |
| WebGL 时序 | `webgl_fingerprint.cc`（`020`） | `getParameter` 的耗时分桶 |
| **时区** | `blink/core/timezone/timezone_controller.cc` | 改 **ICU** 时区 |
| `navigator.webdriver` | `blink/core/frame/navigator.cc` | 移除 `AutomationControlledEnabled` 分支 |
| Headless UA | `headless/lib/browser/headless_browser_impl.cc` | `"HeadlessChrome"` → `"Chrome"` |
| Closed shadow root | `blink/core/dom/element.cc/.id l` | 新增 `fakeShadowRoot` 属性（见下） |
| CDP `Runtime.enable` | `v8/src/inspector/v8-runtime-agent-impl.cc` | 内核层消除副作用（见下） |

### 2.3 三个值得直接照搬的技巧

**（1）把 CDP 泄漏在内核层消除，而不是在驱动层打补丁**

`001-disable-runtime.enable.patch` 改的是 V8 inspector：

```cpp
void V8RuntimeAgentImpl::addBindings(InspectedContext* context) {
  const String16 contextName = context->humanReadableName();
  return;                       // ← 整个函数体被短路
  // if (!m_enabled) return;
  ...
}
bool enabled() const { return false; }   // ← 永远报告未启用
```

`Runtime.enable` 之所以能被检测，是因为打开后会引发 `addBindings` 注册全局绑定、`messageAdded` 上报 console，这些副作用在 `Error.stack` 等处留下痕迹。patchright 是在驱动层避免发这个命令；这里是把**副作用本身拆掉**，所以即使开了也看不出来。

**教训：能改副作用就不要改调用方。** 驱动层的规避总有"谁在发这个命令"的元问题，内核层没有。

**（2）需要 access closed shadow root 时，新增属性，不要改语义**

7 号补丁没有去改 `shadowRoot` 的 getter（那会让"closed root 的 `shadowRoot` 应返回 null"这条规范失效，反而更好检测），而是新增了一个非标准属性：

```cpp
ShadowRoot* Element::FakeShadowRoot() const { return GetShadowRoot(); }   // 无视 mode
// element.idl:
[PerWorldBindings, ImplementedAs=FakeShadowRoot] readonly attribute ShadowRoot? fakeShadowRoot;
```

**教训：不要修改标准 API 的可观测语义；开一条侧信道。** 任何"让标准 API 返回非标准值"的改动都会制造新的可检测矛盾。

**（3）时区改在 ICU 层，不要在 `Intl` 层伪造**

`018-timezone.patch` 同时改了 `GetCurrentTimezoneId()`（IDL 可见的 `Intl.DateTimeFormat().resolvedOptions().timeZone`）和 `SetIcuTimeZoneAndNotifyV8`（V8 里 `Date` 的底层时区）：

```cpp
String GetCurrentTimezoneId() {
  if (command_line->HasSwitch(switches::kFingerprintTimezone)) { ... }   // IDL 路径
  ...
}
TimeZoneController::TimeZoneController() {
  if (command_line->HasSwitch(switches::kFingerprintTimezone))
    SetIcuTimeZoneAndNotifyV8(String::FromUtf8(timezone_str));           // V8 路径
}
```

只改前者的话，`new Date().getTimezoneOffset()` 仍然是宿主机时区——**立刻构成矛盾**。

**教训：在多个 API 共享的"最底层数据源"上改，不要在每个 API 上分别伪造。** 找共性源头，一次改对。

## 3. Firefox 路线：Camoufox

12.7k star，48 个补丁，是当前开源里指纹面覆盖最全的。

### 3.1 配置机制：路径寻址，而非命令行开关

`fingerprint-injection.patch` 展示了完全不同的做法。在 `dom/base/moz.build` 里挂一个独立目录：

```
LOCAL_INCLUDES += ["/camoucfg"]
```

然后每个 getter 开头插一行按 **JS 属性路径**寻址的查询：

```cpp
double nsGlobalWindowInner::GetInnerWidth(CallerType aCallerType, ErrorResult& aError) {
  if (auto value = MaskConfig::GetDouble("window.innerWidth"))
    return value.value();
  FORWARD_TO_OUTER_OR_THROW(...
}
```

对比两种配置方式：

| | fingerprint-chromium | Camoufox |
|---|---|---|
| 载体 | 命令行开关 | 配置文件 + `MaskConfig` |
| 加字段成本 | 新增 switch + 改转发白名单 + 改实现 | 只在实现处加一行查询 |
| 命名 | `--fingerprint-screen-width` | `"screen.width"` |
| 与 JS API 对应 | 需人工映射 | 一一对应，自解释 |
| 覆盖 Worker/Utility 进程 | 需单独处理 | 同一套 key，`WorkerNavigator` 也用 |

**Camoufox 的机制明显更优**：加一个指纹点不需要碰"分发层"，key 直接是 JS 路径，跨进程天然一致。Proteus 的 `KernelAdapter` 若要支持多内核，应把这种"路径寻址"作为统一抽象，而不是把开关列表当接口。

### 3.2 一条反直觉的自我约束

同一个补丁里，`outerWidth`/`outerHeight` **故意不伪装**，注释写明了原因：

> window.outerWidth/outerHeight are deliberately NOT read from MaskConfig. browser-init.js resizes the real window to the drawn size, and innerWidth/innerHeight report the real content area, so a fixed outer size contradicted inner whenever the window ended up a different size: the WM clamped or auto-maximized it, or Juggler resized it for a viewport. Pages then saw innerWidth > outerWidth (measured 1853 > 1680 on GNOME).

**这是本项目最该学的一条原则：能改真实状态，就不要改读数。** 伪造一个静态的 `outerWidth`，一旦窗口管理器真的把窗口缩放成别的尺寸，读数就和真实布局矛盾（实测出现 `innerWidth(1853) > outerWidth(1680)` 这种不可能的组合）。正确做法是**真的把窗口调成目标尺寸**，让读数自然正确。

推论到 Proteus：`screen.width/height` 也应该优先通过真实窗口/显示设置实现，只有在无法做到时才降级为伪造，并同时伪造所有相关派生值（`availWidth`、`matchMedia`、`screenX`）。

## 4. 覆盖面差距（选型关键）

Camoufox 有、而 fingerprint-chromium **完全没有**对应补丁的指纹面：

| 补丁 | 覆盖的指纹点 | Chromium 侧 |
|---|---|---|
| `webrtc-ip-spoofing` (49 KB) | `RTCPeerConnection` 暴露的内网 IP ↔ 公网 IP 矛盾 | ❌ 只有 ungoogled 的 `webrtc-ip-handling-policy` 默认值 |
| `trusted-automation-events` (17 KB) | 合成事件 `event.isTrusted` | ❌ 无 |
| `speech-voices-spoofing` / `voice-spoofing` | `speechSynthesis.getVoices()` | ❌ 无 |
| `media-device-spoofing` | `enumerateDevices()` 设备列表 | ❌ 无 |
| `media-codec-spoofing` | `canPlayType()` 编解码器集合 | ❌ 无 |
| `touchscreen-fingerprint-spoofing` | `maxTouchPoints` / 触摸能力 | ❌ 无 |
| `geolocation-spoofing` | 地理位置 API | ⚠️ `--fingerprint-location` 存在，覆盖范围待核实 |
| `locale-spoofing` | `navigator.languages` / ICU locale | ⚠️ 部分 |
| `font-hijacker` / `font-list-spoofing` / `anti-font-fingerprinting` | 字体枚举、系统字体、CSS2 字体 | ⚠️ 只有 `font_cache.cc` 一处 |
| `debugger-invisible-to-content` | CDP 对页面不可见 | ✅ `001` 等价 |
| `window-setter-seal` | `window` 上的 setter 被篡改的痕迹 | ❌ 无 |
| `wheel-native-ticks` | 滚轮事件的原生 tick 单位 | ❌ 无 |
| `force-default-pointer` | 指针类型一致性 | ❌ 无 |
| `screen-spoofing` (20 KB) | screen 全套 | ✅ 有 width/height/scale，其余不明 |

**结论：Chromium 路线的补丁集覆盖约 15 个指纹点，Camoufox 覆盖约 40 个。**

这推翻了我此前的默认假设（"Chromium 兼容性好所以是当然的默认选择"）。真实情况是：**Chromium 路线差得比想象多，尤其在 automation 特征（`isTrusted`）和 WebRTC 这两个高频检测点上完全是空白。**

选型的真实权衡变成：
- 选 Chromium：站点兼容性好、UA 形态主流，但**必须自己补 6–10 个关键补丁**（WebRTC、isTrusted、speechSynthesis、mediaDevices、maxTouchPoints…）
- 选 Camoufox：覆盖面最全，但 Firefox 内核 + Firefox 形态 UA，部分风控对非 Chromium 有额外权重

## 5. 一致性怎么做才算对：Camoufox `coherence.py`

`python/src/camoufox/coherence.py`（430 行）是目前开源里最好的一致性实现，比我们的 M0 规则集成熟一个量级。三个设计点值得直接采纳：

**（1）规则带"修复"，不只是"拒绝"**

```python
class Rule(NamedTuple):
    name: str
    check: Callable[[Dict, str], Optional[str]]     # 返回缺陷描述
    repair: Optional[Callable[[Dict, str], None]]   # 就地修复；None 表示无法凭空造出正确值
```

`apply()` 先 `repair` 再 `validate`。修复策略是"**取最近的合法值**"：DPR `1.818` → Windows 的 `1.75`；竖向屏 `1440x2560` → 交换为 `2560x1440`（保留面板真实尺寸，而不是编造新数字）。

我们的 M0 只有 `check()`，任何违规都是 `fatal` 直接拒绝启动。**这太粗暴**：用户给的 seed 落在不可修复的组合上时，正确做法是修到最近合法值，而不是让他换个 seed 碰运气。

**（2）规则必须引用实测**

模块 docstring 直接写明 ground truth 的来源、日期和机器：

> Ground truth used below was captured from stock Firefox 152.0.4, headed, on three machines on 2026-09-17: a 16-core Linux box (1920x1080, colorDepth 24, dpr 1, "Radeon HD 3200 Graphics, or similar"), a 16-core Windows 11 laptop with a touchscreen (3456x2160 at dpr 2.5 -> 1382x864 CSS, colorDepth 24, maxTouchPoints 5, ANGLE/Intel), and a 10-core Apple Silicon Mac mini (2560x1440, colorDepth 30, dpr 2, "Apple M1, or similar" — the machine is an M4, and Firefox generalises the renderer string itself).

并附一句判据：**"a rule nobody can trace is a rule nobody can revise."**

这条直接适用于我们：M0 里 `deviceMemory` 上限、`hardwareConcurrency` 奇偶这些都是**没有实测来源的规则**，下面 §7 证明它们就是错的。

**（3）缺陷产生于"池合并"时刻**

> Each pool is sampled on its own, so a combination that no machine has ever had can be built out of individually plausible parts... That class of defect cannot be removed by cleaning the pools, because it is created when they are combined.

这正是 ADR-0002 想表达的意思，但他们的表述更精确：**不是候选表脏，是组合才产生不可能**。所以校验必须放在"组装完成之后"，且要跨池。

## 6. 两条路线都没做的事（= Proteus 的空间）

调研 3 个主项目 + 7 个周边，下面这些**没有任何开源方案覆盖**：

1. **可复现的一致性证明** —— 有校验器，但没有"启动后回读真实 `navigator` 并与模型 diff"的闭环。Camoufox 的 coherence 校验的是**配置**，不是**页面实际读到的东西**。
2. **多环境编排** —— 三个项目都是"单会话"工具。没有 Profile 管理、没有代理编排、没有环境池、没有本地 API。
3. **公开的对标数据** —— 没有任何项目发布跨方案的实测对比。这正是中立开源项目能占的位置。
4. **真机指纹分布** —— BrowserForge 用贝叶斯网络（`bayesian_network.py`）从真实统计采样，是目前最好的做法，但它是独立的 Python 库，没有与任何内核的注入结果做闭环验证。

## 7. 实测推翻了我们的三条规则

用本机 Edge（Chromium 155）无头模式读取真实值：

```json
{
 "deviceMemory": 32,          ← 32 GB 机器
 "hardwareConcurrency": 16,
 "platform": "Win32",
 "userAgent": "... HeadlessChrome/155.0.0.0 Safari/537.36 Edg/155.0.0.0",
 "languages": ["zh-CN","en","en-GB","en-US"],
 "timezone": "Asia/Shanghai",
 "webdriver": false,
 "dpr": 1,
 "screen": [800, 600, 800, 600]
}
```

对照我们的 M0 规则：

| 我们的规则 | 实测 / 上游实测 | 结论 |
|---|---|---|
| `deviceMemory ∈ {1,2,4,8}`，理由"Chromium 封顶 8" | 本机实测 `32`；fingerprint-chromium 用 `{8,16,32}` | **规则错误**，会误杀高内存机器 |
| macOS `DPR >= 2` | Camoufox 实测注释："macOS reports 1 or 2 and nothing between" | **规则错误**，外接非 Retina 屏的 Mac 就是 1 |
| `hardwareConcurrency` 必须为偶数 | Camoufox：Apple M3 Pro 是 6P+5E = **11**，且 Apple Silicon 无 SMT | **规则错误**，奇数核在 Apple Silicon 上是真实的 |

另外实测还显示：
- 无头 Chromium 的 UA 里带 `HeadlessChrome/155` —— 正是 `010-headless.patch` 要修的
- 无头模式 `screen` 报 `800x600`（不是宿主机分辨率）—— 所以 screen 必须显式设置，不能"继承"
- `webdriver` 在无头 Edge 下已经是 `false`（该检测点已被上游弱化）

## 8. 对 Proteus 的直接输入

1. **内核抽象用"路径寻址 + 配置表"**，照 Camoufox 的 `MaskConfig` 形态，不要照 fingerprint-chromium 的开关列表。
2. **校验器要有 `repair`**，`check → repair → re-check`，只有修不掉的才拒绝启动。
3. **规则必须带证据字段**：每条规则的 `message` 里包含实测来源或机器条件，否则不许合入。
4. **暂不定内核**。若走 Chromium，必须新增 WebRTC / `isTrusted` / `speechSynthesis` / `maxTouchPoints` 至少 4 个补丁才有竞争力；若走 Camoufox，则接受 Firefox 形态。
5. **`verify()` 是差异化核心**，因为两个上游都只校验配置、不校验页面实读。
6. **字段集要扩**：目前缺 `screen.colorDepth/pixelDepth/availWidth/availHeight`、`maxTouchPoints`、`navigator.oscpu`、`window.outerHeight`（chrome 高度约束）。

## 参考

本地克隆位置：`G:\Projects\proteus-research\third_party\`

- `fingerprint-chromium-148/patches/extra/fingerprint/*.patch`
- `camoufox/browser/patches/*.patch`
- `camoufox/python/src/camoufox/coherence.py`
- `browserforge/browserforge/fingerprints/generator.py`、`bayesian_network.py`
