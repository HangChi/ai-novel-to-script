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
- 结构化预览与局部编辑：将当前 YAML 映射为结构化视图，支持编辑剧本标题、logline、人物、场景基础信息和 beats（含对白说话人）。
- 自动同步：结构化编辑会即时写回 YAML，并提示当前内容可直接校验、复制或下载。
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
│   ├── 剧本YAMLSchema.md
│   └── examples/
├── frontend/
├── backend/
├── sql/
└── docker-compose.yml
```

## 技术栈与第三方依赖

当前框架采用前后端分离架构，MVP 阶段暂不引入数据库。AI Provider 使用可配置的运行时服务调用，当前不引入 AI SDK。

| 模块 | 技术或依赖 | 用途 |
| --- | --- | --- |
| 后端 | FastAPI | 提供 HTTP API 服务 |
| 后端 | Uvicorn | 本地运行 ASGI 服务 |
| 后端测试 | pytest | 运行后端自动化测试 |
| 后端测试 | httpx | 支撑 FastAPI 测试客户端 |
| 后端 | PyYAML | 将剧本结构序列化为 YAML |
| 前端 | React | 构建交互界面 |
| 前端 | React DOM | 将 React 应用挂载到浏览器 DOM |
| 前端 | Vite | 前端开发服务器与构建工具 |
| 前端 | TypeScript | 前端静态类型检查 |
| 前端 | @vitejs/plugin-react | Vite 的 React 编译插件 |
| 前端类型 | @types/react | React 的 TypeScript 类型声明 |
| 前端类型 | @types/react-dom | React DOM 的 TypeScript 类型声明 |
| 前端 E2E | Playwright | 运行真实 Chromium 浏览器端到端烟测 |

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

#### AI Provider 配置

默认配置不需要密钥：

```powershell
$env:AI_PROVIDER="local"
```

`local` 模式会返回稳定的 YAML 骨架，适合本地开发和测试。启用 OpenAI-compatible Provider 时，需要配置：

```powershell
$env:AI_PROVIDER="openai"
$env:OPENAI_API_KEY="你的 API Key"
$env:OPENAI_MODEL="你的模型名称"
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
```

可选配置：

```powershell
$env:OPENAI_TEMPERATURE="0.3"
$env:AI_PROVIDER_TIMEOUT_SECONDS="60"
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

### 浏览器端到端烟测（可选）

首次运行浏览器 E2E 前，需要安装 Playwright Chromium：

```powershell
cd frontend
npm run e2e:install
```

浏览器 E2E 用于自动验证演示主流程，不是日常启动命令：

```powershell
cd frontend
npm run smoke:e2e
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

当前前端工作台支持直接粘贴文本，也支持导入本地 `.txt` 或 `.md` 文件。

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

## 演示素材

仓库内置了一组可直接复现的示例素材：

- 输入文本：`docs/examples/rain-letter-novel.txt`
- 期望 YAML 骨架：`docs/examples/rain-letter-script.yaml`

本地启动前后端后，可在前端导入示例文本，点击“生成 YAML”，查看 YAML 与结构化视图，编辑剧本标题、logline、场景标题、地点、时间和 beats，确认同步状态提示后，再使用“校验 YAML”“复制 YAML”或“下载 YAML”验证完整流程。

## 评委复现流程

### 一键启动

在项目根目录运行：

```powershell
.\scripts\start-local-demo.ps1
```

脚本会复用或启动：

- 后端 API：`http://127.0.0.1:8000`
- 前端工作台：`http://127.0.0.1:5173`

也可以附带运行烟测：

```powershell
.\scripts\start-local-demo.ps1 -RunSmoke
```

`-RunSmoke` 会在启动或复用前后端后运行真实浏览器 E2E，覆盖打开页面、导入示例、生成 YAML、查看结构化预览、编辑标题/logline/场景信息/beats、校验 YAML、复制和下载。首次运行前需先在 `frontend` 目录执行 `npm install` 和 `npm run e2e:install`。

### 页面演示

1. 打开 `http://127.0.0.1:5173`。
2. 点击“导入文件”，选择 `docs/examples/rain-letter-novel.txt`。
3. 点击“生成 YAML”。
4. 查看右侧“结构化预览”，确认标题、logline、人物、场景和 beats 已从 YAML 映射到页面。
5. 修改剧本标题、logline、场景标题、地点、时间和 beats，确认 YAML 内容同步更新，并显示“结构化修改已同步到 YAML”。
6. 点击“校验 YAML”，确认显示“YAML 结构有效”。
7. 点击“复制 YAML”或“下载 YAML”，验证当前剧本内容可以导出。

## 初始开发计划

1. 定义剧本 YAML Schema 文档。
2. 实现小说章节解析与基础校验。
3. 实现 AI 改编提示词与结构化输出流程。
4. 增加 YAML Schema 校验。
5. 提供命令行或 Web 界面，方便作者上传文本并导出剧本。

## 仓库状态

当前仓库已建立文档、前端、后端、SQL 与部署配置目录，并搭建了基础前后端框架、章节解析、剧本 YAML 初稿骨架、生成接口、YAML 校验接口、AI Provider 和前端 YAML 预览、结构化预览、标题/logline、人物、场景基础信息与 beats（含对白说话人）结构化编辑、同步状态提示、YAML 编辑、校验、复制、下载、本地文本导入能力。后续会逐步补充登场人物编辑、场景增删、更完整的双向同步和持久化能力。
