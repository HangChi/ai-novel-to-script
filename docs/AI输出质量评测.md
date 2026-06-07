# AI 输出质量评测

## 当前目标

当前阶段只验证 OpenAI-compatible Provider 的结构稳定性和错误处理，不评价真实模型的文学质量。测试应保持可离线、可复现、无网络依赖。

## 覆盖方式

- 使用 `backend/tests/fixtures/ai_quality_outputs.yaml` 保存多种 mock 剧本输出。
- 测试通过 monkeypatch `_request_completion` 返回 fixture 内容。
- 每个 fixture 都必须通过 `validate_script_yaml`。
- 每个 fixture 都需要包含人物、logline、场景地点、场景时间，以及 `action`、`dialogue`、`narration`、`transition` 四类 beat。
- Provider 会在首轮 AI 输出未通过 Schema 校验时自动追加一次修复提示；测试覆盖一次修复成功和二次失败后返回校验路径两种情况。
- 测试覆盖从 Markdown 代码块、说明文字和 JSON 风格 YAML key 中提取真实 `script:` YAML。

## 评测维度

| 维度 | 当前检查方式 |
| --- | --- |
| 结构完整性 | 后端 Schema 校验 |
| 字段稳定性 | fixture 必须包含必填字段 |
| beat 覆盖 | fixture 覆盖四类 beat |
| 语言与 key | 字段值可中文或英文，YAML key 保持 Schema 英文 key |
| 错误恢复 | 首轮失败后自动修复一次 |
| 错误透传 | Provider HTTP 错误保留关键说明 |

## 非目标

- 不调用真实外部模型。
- 不评价剧情、对白、节奏或文学风格优劣。
- 不接入线上评分服务。
- 不改变 YAML Schema 或 Provider API。
- 不把个人 API Key 放入测试或 CI。

## 后续计划

- 增加更多小说类型 fixture，例如悬疑、言情、科幻、古风。
- 增加人工评分表，单独评估忠实度、可拍摄性、对白自然度和场次拆分质量。
- 将真实模型抽样评测设计为手动流程，避免 CI 依赖外部服务。
- 记录模型版本、temperature、base URL 和生成时间，便于复现质量问题。
