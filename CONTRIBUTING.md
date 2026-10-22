# 贡献指南

欢迎贡献。这个项目的门槛不在代码量，在**判断力**——请先读完本文再动手。

## 先读什么

| 文档 | 为什么 |
|---|---|
| [README](README.md) | 定位与三个核心观点。**不接受背离定位的 PR** |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 分层与模块边界。代码放错层会被要求重写 |
| [docs/THREAT-MODEL.md](docs/THREAT-MODEL.md) | 技术边界。避免重复讨论"为什么不用 JS 注入" |
| [docs/ACCEPTABLE-USE-POLICY.md](docs/ACCEPTABLE-USE-POLICY.md) | **硬性约束**。违反用途的贡献一律拒绝 |
| [docs/adr/](docs/adr/) | 已定决策。要推翻请写新 ADR，不要在 PR 里悄悄改 |

## 最有价值的贡献

按价值排序：

1. **可复现的一致性缺陷** —— "这个字段组合是矛盾的，这是我的页面和读数"。附四段式（见 THREAT-MODEL §7）
2. **新的候选表数据** —— 真实设备 OS/分辨率/DPR/GPU 的分布统计。这一项直接决定指纹质量
3. **内核适配器** —— 新的 `KernelAdapter` 实现
4. **检测面回归用例** —— 把一个检测点固化成测试
5. **文档与文档纠错**

## 不接受

- 行为层拟真（鼠标轨迹、输入节奏）—— 见 THREAT-MODEL §5，明确不在范围
- 自研内核 fork 相关代码 —— 见 ADR-0001
- 任何"让某个特定风控厂商放行"的调优补丁
- 引入重量级框架作为核心依赖（核心必须是 stdlib）
- 无测试的行为变更

## 开发

**要求**：Python ≥ 3.9。核心零第三方依赖。

```bash
git clone https://github.com/yushui2022/Proteus.git
cd Proteus

# 跑测试（纯标准库，无需安装任何东西）
python -m unittest discover -s tests -v

# 或者装成可编辑包
pip install -e .
```

## 代码规范

- **核心（`src/proteus/fingerprint/`）零第三方依赖**，只用标准库。这是硬性要求：指纹派生必须能在任何环境复现。
- 类型注解必须完整，`from __future__ import annotations`
- 数据模型用 `@dataclass(frozen=True)`，不可变
- 纯函数优先；副作用集中在 `kernel/` `profile/` `proxy/`
- 中文注释可以，**代码标识符一律英文**

## 提交信息

采用 Conventional Commits：

```
feat(fingerprint): 新增 WebGL renderer 与 OS 的强绑定规则
fix(derive): 修正 screen 候选表重复项
docs(adr): 补充 ADR-0002 的复核条件
test(consistency): 覆盖 deviceMemory 越界用例
```

## 新增一致性规则的流程

1. 在 `consistency.py` 加规则，**分配唯一规则码**（`<域>.<问题>`，如 `os.font_profile_mismatch`）
2. 在 `tests/` 加两条用例：**合法值不触发**、**非法值必触发**
3. 在 [THREAT-MODEL.md](docs/THREAT-MODEL.md) §2.1 登记该检测点
4. 判断 `severity`：能被一眼识破的用 `fatal`，可疑但非致命的用 `warn`

**规则码一旦发布不可重命名** —— 它是 API，用户会在日志和 issue 里引用它。

## PR 检查清单

- [ ] `python -m unittest discover -s tests -v` 全绿
- [ ] 新增行为有对应测试
- [ ] 改动落在正确的层（见 ARCHITECTURE §2）
- [ ] 没有引入核心层的第三方依赖
- [ ] 新规则已登记到 THREAT-MODEL
- [ ] 用途符合 AUP

## 行为准则

技术争论请针对代码和数据，不针对人。"这个规则会制造矛盾，因为 X 和 Y 冲突" 是好评论；"这写得不行" 不是。

Issue 里请勿粘贴真实账号、cookie、代理凭证、未脱敏的个人信息。

## 许可证

贡献即表示你同意以 **AGPL-3.0** 授权你的贡献，并同意项目可将其用于商业双许可。提交 PR 时无需额外签署协议。
