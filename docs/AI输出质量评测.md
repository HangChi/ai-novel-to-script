# AI 输出质量评测

## 当前目标

本阶段只验证 OpenAI-compatible Provider 的结构稳定性，不调用真实外部模型。

## 覆盖方式

- 使用 `backend/tests/fixtures/ai_quality_outputs.yaml` 保存 3 个不同风格的 mock 剧本输出。
- 每个 fixture 都必须通过 `validate_script_yaml`。
- 每个 fixture 都需要包含人物、logline、场景地点/时间，以及 `action`、`dialogue`、`narration`、`transition` 四类 beat。
- 测试通过 monkeypatch `_request_completion` 返回 fixture 内容，保证 CI 稳定且无网络依赖。

## 非目标

- 不评价真实模型的文学质量。
- 不接入线上评分服务。
- 不改变 YAML Schema 或 Provider API。
