---
name: 一致性缺陷 / Consistency defect
about: 报告一个字段矛盾或检测面遗漏（本项目最有价值的贡献）
title: "[fp] "
labels: consistency
---

<!--
请按四段式填写（见 docs/THREAT-MODEL.md §7）。
不要贴真实账号、cookie、代理凭证或未脱敏的个人信息。
-->

## 1. 最小复现

<!-- 可独立打开的最小页面或最小脚本，不要贴整站 -->

```html
<!-- 示例：只保留触发检测的那几行 -->
```

## 2. 期望值 vs 实际值

| 字段 | 模型声明（Proteus） | 页面实测 |
|---|---|---|
| 例如 `navigator.platform` | `Win32` | `MacIntel` |

## 3. 检测层

<!-- 勾选一项 -->
- [ ] 应用层 —— JS API 一致性 / 跨上下文泄漏
- [ ] 协议层 —— TLS / HTTP2 指纹
- [ ] 网络层 —— IP 声誉 / geo 漂移
- [ ] 行为层 —— 本项目明确不做，仅记录

## 4. 归因

<!-- 你判断问题出在哪一环 -->
- [ ] `derive` 派生出矛盾的值（候选表 / 派生逻辑错）
- [ ] `check` 漏了规则（值本身可疑但没被拦下）
- [ ] 内核没把值注入进去（模型对，内核没生效）
- [ ] 不确定

## 环境

- Proteus 版本 / commit：
- Python 版本：
- OS：
- 内核（fingerprint-chromium / Camoufox / patchright）：

## 违规输出

```text
# 贴 check(fp) 或 fatal 违规列表；没有则留空
```
