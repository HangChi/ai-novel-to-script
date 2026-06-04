# AI Novel to Script

AI Novel to Script 是一款面向小说作者的 AI 辅助剧本创作工具，目标是将 3 个章节以上的小说文本自动转换为结构化剧本初稿，降低小说改编剧本的门槛，提升创作与打磨效率。

## 项目目标

- 将多章节小说内容解析为可编辑的剧本结构。
- 输出标准化 YAML，方便作者、编剧和后续工具继续修改。
- 保留小说中的人物、场景、对白、动作和叙事线索。
- 为作者提供可快速迭代的剧本初稿，而不是一次性替代人工创作。

## 核心能力

- 多章节输入：支持至少 3 个章节以上的小说文本。
- 剧本结构化：自动提取章节、场次、人物、对白、动作、旁白和转场。
- YAML 输出：生成稳定、可读、可编辑的剧本 YAML。
- Schema 约束：通过文档定义剧本 YAML Schema，说明字段含义与设计原因。
- AI 辅助改编：在忠于原文的基础上，将小说叙事改写为适合剧本阅读和后期创作的形式。

## 项目结构

```text
project/
├── README.md
├── docs/
│   ├── 需求说明.md
│   ├── 系统设计.md
│   ├── 数据库设计.md
│   ├── 接口文档.md
│   ├── 部署文档.md
│   ├── 测试文档.md
│   ├── 用户手册.md
│   ├── 开发日志.md
│   └── 剧本YAMLSchema.md
├── frontend/
├── backend/
├── sql/
└── docker-compose.yml
```

## 技术栈与第三方依赖

当前框架采用前后端分离架构，MVP 阶段暂不引入数据库，也暂不接入 AI SDK。

| 模块 | 技术或依赖 | 用途 |
| --- | --- | --- |
| 后端 | FastAPI | 提供 HTTP API 服务 |
| 后端 | Uvicorn | 本地运行 ASGI 服务 |
| 后端测试 | pytest | 运行后端自动化测试 |
| 后端测试 | httpx | 支撑 FastAPI 测试客户端 |
| 前端 | React | 构建交互界面 |
| 前端 | React DOM | 将 React 应用挂载到浏览器 DOM |
| 前端 | Vite | 前端开发服务器与构建工具 |
| 前端 | TypeScript | 前端静态类型检查 |
| 前端 | @vitejs/plugin-react | Vite 的 React 编译插件 |
| 前端类型 | @types/react | React 的 TypeScript 类型声明 |
| 前端类型 | @types/react-dom | React DOM 的 TypeScript 类型声明 |

## 本地开发

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python -m uvicorn app.main:app --reload --port 8000
```

后端健康检查地址：

```text
http://127.0.0.1:8000/api/health
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

前端默认地址：

```text
http://127.0.0.1:5173
```

## 预期输入

用户可以提供由多个章节组成的小说文本，例如：

```text
第 1 章 ...
...
第 2 章 ...
...
第 3 章 ...
...
```

后续实现会支持更灵活的输入方式，例如纯文本文件、Markdown 文件或 Web 表单。

## 预期输出

工具将输出结构化 YAML 剧本初稿，便于继续编辑、校验和导出。

```yaml
script:
  title: 示例剧本
  source:
    type: novel
    chapters_count: 3
  scenes:
    - id: scene-001
      title: 初遇
      location: 街边茶馆
      time: 黄昏
      characters:
        - 林澈
        - 苏晚
      beats:
        - type: action
          text: 林澈推门而入，雨水顺着衣角滴落。
        - type: dialogue
          character: 苏晚
          text: 你终于来了。
```

## 初始开发计划

1. 定义剧本 YAML Schema 文档。
2. 实现小说章节解析与基础校验。
3. 实现 AI 改编提示词与结构化输出流程。
4. 增加 YAML Schema 校验。
5. 提供命令行或 Web 界面，方便作者上传文本并导出剧本。

## 仓库状态

当前仓库已建立文档、前端、后端、SQL 与部署配置目录，并搭建了基础前后端框架。后续会逐步补充章节解析、AI 生成、YAML 校验、示例输入输出和测试用例。
