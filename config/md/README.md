# AI 测试用例生成器 — 设计文档

## 项目概述

根据上传或手动输入的 PRD 文档（Markdown/Word/PDF），通过 AI Skill 流水线自动生成结构化、可执行的测试用例，支持 Excel 和 XMind 导出。工具完全本地运行，数据双重持久化（本地文件 + Supabase）。

---

## 文档索引

| 文档 | 内容 | 面向角色 |
|------|------|----------|
| [需求规格说明书.md](需求规格说明书.md) | 功能需求、非功能需求 | 全员 |
| [系统架构设计.md](系统架构设计.md) | 技术选型、架构图、项目目录 | 开发 |
| [前端界面设计.md](前端界面设计.md) | 页面布局、组件树、交互细节 | 前端 |
| [后端接口设计.md](后端接口设计.md) | 全部 API 接口定义、数据模型 | 前后端 |
| [AI配置规范.md](AI配置规范.md) | Bot 配置、7 个 Skill 完整 Prompt | 后端 / AI |
| [本地数据存储方案.md](本地数据存储方案.md) | 文件目录结构、Supabase 表 DDL | 后端 |
| [项目目录规范.md](项目目录规范.md) | 完整项目文件树、命名规范 | 开发 |
| [开发规范.md](开发规范.md) | 编码规范、分层架构、异常处理 | 开发 |
| [可执行用例示范.md](可执行用例示范.md) | 正确/错误用例对比、防臆想机制 | 测试 / AI |

---

## 快速启动

### 环境要求
- Node.js 18+
- Python 3.10+
- Supabase 项目（已配置在 `.env` 中）

### 1. 初始化 Supabase 数据库表

在 Supabase 控制台的 SQL Editor 中执行 [本地数据存储方案.md](本地数据存储方案.md) 中的 DDL 语句，创建 `projects`、`testcases`、`logs`、`exports` 四张表及对应 RLS 策略。

### 2. 启动后端

```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### 3. 启动前端

```bash
cd frontend
npm install
npm run dev
```

### 4. 使用

1. 浏览器访问 `http://localhost:5173`
2. 上传 PRD 文件（.md/.docx/.pdf）或手动粘贴 Markdown 内容
3. 点击「生成测试用例」，观察 AI Skill 流水线执行进度
4. 查看/编辑/删除生成的用例
5. 导出 Excel 或 XMind 格式文件

---

## 核心设计决策

### 为什么双重存储（本地文件 + Supabase）？

- **本地文件**：原始文件（PDF/Word 等二进制）不适合存数据库；离线时系统仍可正常工作
- **Supabase**：测试用例的结构化数据需要分页、排序、过滤、搜索，这些用 JSON 文件查询效率低
- **双写策略**：每次操作同时写两端，查询优先 Supabase，失败时降级本地文件

### 为什么用 7 个 Skill 流水线而不是一次生成？

单一 prompt 生成全部用例容易遗漏边界用例和异常场景，且 LLM 容易跑偏。拆分成 7 个 Skill 后：
1. 每个 Skill 职责单一，prompt 可以更精准
2. 边界/状态转换补充是独立的 Skill，确保不遗漏
3. 去重 Skill 在最后把关，过滤语义重复的用例
4. 每个 Skill 都可以独立优化 prompt，不影响其他

### 如何防止 AI 生成臆想/固化的测试用例？

| 机制 | 说明 |
|------|------|
| PRD 原文全程注入 | 每个 Skill 的 user prompt 都包含 PRD 原文或摘录 |
| 低温度参数 | temperature=0.1 减少自由发挥 |
| 强制标注缺失信息 | PRD 未明确的约束，用例标注"需与产品确认：xxx" |
| 多轮交叉验证 | 3 个 Skill 独立分析同一 PRD，互相印证 |
| 语义去重 | 最终去重审查，过滤跑偏结果 |
