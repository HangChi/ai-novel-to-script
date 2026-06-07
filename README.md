# AI Novel to Script

> 七牛云 x XEngineer 暑期实训项目：6.5-6.7批次，题目三：AI 小说转剧本工具

demo视频.mp4
链接: https://pan.baidu.com/s/1nfBxY-2P2Z7eLfGETdWAig?pwd=kh2h 提取码: kh2h 复制这段内容后打开百度网盘手机App，操作更方便哦

AI Novel to Script 是一款面向小说作者和编剧的 AI 辅助改编工具。它可以把至少 3 个章节的小说文本转换为结构化剧本 YAML 初稿，并提供结构化预览、局部编辑、Schema 校验、复制和下载能力，帮助作者更快完成从小说叙事到剧本草稿的第一轮整理。

当前版本以本地可复现演示为优先目标：默认 `local` 模式不需要任何 API Key，会返回稳定的 YAML 骨架；填写远程模型密钥后，也可以在页面上选择 DeepSeek-V4-Pro、Kimi-2.6 或 GLM-4.7-FlashX 生成 AI 改编初稿。

## 核心能力

- 小说输入：支持直接粘贴文本，也支持导入本地 `.txt` 或 `.md` 文件。
- 章节校验：要求至少 3 个章节，并支持常见中文、英文和 Markdown 章节标题格式。
- 剧本生成：输出符合 `0.1.0` Schema 的 YAML 剧本初稿。
- 模型选择：支持本地骨架、DeepSeek-V4-Pro、Kimi-2.6、GLM-4.7-FlashX 和通用 OpenAI-compatible Provider。
- 结构化预览：把 YAML 映射为标题、logline、人物、场景、登场人物和 beats。
- 局部编辑：支持编辑标题、logline、人物、场景信息、对白说话人、beat 类型与文本，并支持新增、删除人物、场景和 beat。
- 同步导出：结构化编辑会即时写回 YAML；校验、复制和下载都使用页面里的最新内容。
- 安全配置：AI 状态接口只暴露配置完整性和缺失项，不返回任何 API Key。

## 技术栈

| 模块 | 技术 | 用途 |
| --- | --- | --- |
| 后端 | FastAPI | 提供 HTTP API |
| 后端 | Uvicorn | 本地运行 ASGI 服务 |
| 后端 | PyYAML | YAML 序列化与解析 |
| 后端测试 | pytest、httpx | 单元测试与 API 测试 |
| 前端 | React 19、TypeScript | 构建工作台界面 |
| 前端 | Vite | 开发服务器与构建 |
| 前端 E2E | Playwright | 浏览器端到端烟测 |

## 项目结构

```text
.
├── README.md
├── .env.example
├── backend/
│   ├── app/
│   ├── tests/
│   ├── main.py
│   └── requirements.txt
├── frontend/
│   ├── src/
│   ├── package.json
│   └── vite.config.ts
├── docs/
│   ├── AI输出质量评测.md
│   ├── 剧本YAMLSchema.md
│   ├── 开发日志.md
│   ├── 持久化评估.md
│   ├── 接口文档.md
│   ├── 数据库设计.md
│   ├── 测试文档.md
│   ├── 用户手册.md
│   ├── 系统设计.md
│   ├── 部署文档.md
│   ├── 需求说明.md
│   └── examples/
├── scripts/
│   ├── e2e-smoke.mjs
│   ├── start-local-demo.ps1
│   └── stop-local-demo.ps1
└── docker-compose.yml
```

## 快速复现

### 1. 安装依赖

建议使用 Windows PowerShell，在项目根目录执行：

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt

cd frontend
npm install
cd ..
```

如果需要运行浏览器端到端烟测，再执行：

```powershell
cd frontend
npm run e2e:install
cd ..
```

### 2. 启动本地演示

保持后端虚拟环境处于激活状态，在项目根目录运行：

```powershell
.\scripts\start-local-demo.ps1
```

脚本会启动或复用：

- 前端工作台：`http://127.0.0.1:5173`
- 后端健康检查：`http://127.0.0.1:8000/api/health`

停止演示：

```powershell
.\scripts\stop-local-demo.ps1
```

如果只想预览会停止哪些进程：

```powershell
.\scripts\stop-local-demo.ps1 -DryRun
```

### 3. 页面演示流程

1. 打开 `http://127.0.0.1:5173`。
2. 点击“导入文件”，选择 `docs/examples/rain-letter-novel.txt`。
3. 保持模型为“本地骨架”，或选择已配置密钥的远程模型。
4. 点击“生成 YAML”。
5. 在结构化预览中检查标题、logline、人物、场景和 beats。
6. 修改标题、logline、人物、场景信息或 beats，确认页面提示已同步到 YAML。
7. 点击“校验 YAML”，确认显示结构有效。
8. 点击“复制 YAML”或“下载 YAML”，验证导出内容是最新版本。

## 常用命令

### 后端

```powershell
cd backend
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python main.py -p 8000 --reload
```

### 前端

```powershell
cd frontend
npm run build
npm run dev
```

### 演示烟测

```powershell
.\scripts\start-local-demo.ps1 -RunSmoke
```

或在已安装前端依赖和 Playwright Chromium 后运行：

```powershell
cd frontend
npm run smoke:e2e
```

## AI Provider 配置

默认配置不需要密钥：

```text
AI_PROVIDER=local
AI_MODEL_ID=local
AI_OUTPUT_LANGUAGE=auto
```

需要远程模型时，复制配置模板并填写对应密钥：

```powershell
Copy-Item .env.example .env
```

常用配置示例：

```text
DEEPSEEK_API_KEY=你的 DeepSeek API Key
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_TEMPERATURE=0.3

KIMI_API_KEY=你的 Kimi API Key
KIMI_MODEL=kimi-k2.6
KIMI_BASE_URL=https://api.moonshot.ai/v1
# 内置 Kimi-2.6 会使用非 thinking 模式和固定 temperature=0.6

GLM_API_KEY=你的 GLM API Key
GLM_MODEL=glm-4.7-flashx
GLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM_TEMPERATURE=0.3
```

后端启动时会自动读取项目根目录 `.env` 和 `backend/.env`；系统环境变量优先于配置文件。也可以通过 `AI_CONFIG_FILE` 指向其它配置文件。真实 API Key 只应放在本地 `.env` 或系统环境变量中，不要提交到仓库。

## API 概览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 健康检查 |
| `GET` | `/api/ai/status` | 当前 AI Provider 配置状态 |
| `GET` | `/api/ai/models` | 前端模型下拉选项 |
| `POST` | `/api/scripts/generate` | 根据小说文本生成剧本 YAML |
| `POST` | `/api/scripts/validate` | 校验剧本 YAML 是否符合 Schema |

接口细节见 [docs/接口文档.md](docs/接口文档.md)。

## 文档地图

- [需求说明](docs/需求说明.md)：产品目标、用户需求、MVP 范围和验收标准。
- [系统设计](docs/系统设计.md)：前后端模块、数据流、错误处理和扩展方向。
- [剧本 YAML Schema](docs/剧本YAMLSchema.md)：YAML 字段、beat 类型和当前校验规则。
- [接口文档](docs/接口文档.md)：后端 API 请求、响应和错误码。
- [用户手册](docs/用户手册.md)：面向使用者的操作步骤和常见问题。
- [部署文档](docs/部署文档.md)：本地启动、配置、烟测和部署注意事项。
- [测试文档](docs/测试文档.md)：测试策略、自动化覆盖和验收清单。
- [数据库设计](docs/数据库设计.md)：当前不落库的原因和后续实体设计。
- [持久化评估](docs/持久化评估.md)：何时引入持久化以及 PR 拆分建议。
- [AI 输出质量评测](docs/AI输出质量评测.md)：远程 Provider mock 质量回归方式。
- [开发日志](docs/开发日志.md)：按日期记录的重要功能、修复和文档变更。

## PR 与提交规范

本项目要求保持清晰、可追溯的提交和 PR 记录。

- 提交信息使用有意义的语义描述，例如 `feat: 完成用户登录模块`、`fix: 修复数据展示错误`、`docs: 完善项目复现文档`。
- 每个 PR 只做一件事。大功能应拆成多个可以独立验证的小 PR，避免把功能、重构、样式和文档混在一起。
- PR 标题用一句话说明新增或修改了什么。
- PR 描述必须包含功能描述、实现思路和测试方式。
- 合并前必须确认主分支在任意时间都能运行并复现演示效果。
- PR 合并后删除对应功能分支，保持分支列表清爽。

推荐 PR 描述模板：

```markdown
## 功能描述

说明本 PR 新增或修改了什么，以及使用方式。

## 实现思路

说明核心实现逻辑、技术选型或文档调整口径。

## 测试方式

- [ ] 后端测试：`cd backend && .\.venv\Scripts\python -m pytest`
- [ ] 前端构建：`cd frontend && npm run build`
- [ ] 演示烟测：`.\scripts\start-local-demo.ps1 -RunSmoke`
```

## 当前状态

当前主分支已具备本地演示能力：在默认 `local` 模式下，不依赖外部 AI 服务即可完成导入示例小说、生成 YAML、结构化编辑、校验、复制和下载。后续重点是补充持久化、版本历史、更多导出格式和更细粒度的 AI 输出质量评测。
