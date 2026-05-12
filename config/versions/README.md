# 版本迭代记录

## 规范

### 文件命名

```
YYYYMMDD-NNNN-short-description.md
```

- `YYYYMMDD`：变更日期
- `NNNN`：当日序号，4 位数字从 0001 开始，确保按文件名排序即为时间顺序
- `short-description`：变更简述（英文小写、连字符分隔）

### 模板

```markdown
---
date: YYYY-MM-DD
type: hotfix | feature | optimization
---

# 标题

## Description
变更内容和原因。

## Affected Files
- `path/file.py`: 变更说明

## Notes
额外上下文、决策理由、后续任务。
```

### type 分类

| type | 使用场景 |
|------|----------|
| `hotfix` | Bug 修复、错误修正、紧急补丁 |
| `feature` | 新功能、新接口、新组件、新页面 |
| `optimization` | 性能优化、代码重构、清理、配置调整 |

### 原则

- **每次变更新增一个文件，永远不覆盖旧文件**
- 文件名序号确保 `ls` 即按时间排列
- 每次提交时顺带新增对应的版本记录
- 热修复、小优化、大功能都值得记录——不区分变更规模
