# 剧本 YAML Schema

## 设计目标

剧本 YAML Schema 用于约束 AI 输出，使小说改编结果既适合人工阅读，也适合程序校验、结构化编辑和后续导出。当前版本号为 `0.1.0`，聚焦剧本初稿，不追求覆盖所有专业制片格式。

## 顶层结构

```yaml
script:
  schema_version: "0.1.0"
  title: "示例剧本"
  logline: "一句话故事梗概。"
  source:
    type: novel
    chapters_count: 3
    chapter_titles:
      - 第 1 章
      - 第 2 章
      - 第 3 章
  characters:
    - id: char-001
      name: 林澈
      role: protagonist
      description: 年轻调查员，沉默克制。
  scenes:
    - id: scene-001
      title: 初遇
      source_chapter: 第 1 章
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

`local` Provider 会输出相同的 Schema 形状。为了降低空字段造成的演示疑惑，本地骨架会使用 `TBD` 类占位文本提示作者后续补充。

## 字段说明

### script

剧本根节点。所有剧本数据都放在 `script` 下，便于和其它配置或元数据区分。

### schema_version

Schema 版本号。当前固定为 `0.1.0`。后续字段升级时，可以通过版本号兼容旧剧本。

### title

剧本标题。默认可以沿用小说标题，也可以由作者在结构化预览中修改。

### logline

一句话故事梗概，用于快速理解作品核心冲突。当前版本支持在结构化预览中直接编辑。

### source

来源信息，记录剧本由小说文本改编而来。

```yaml
source:
  type: novel
  chapters_count: 3
  chapter_titles:
    - 第 1 章
    - 第 2 章
    - 第 3 章
```

- `type` 当前固定为 `novel`。
- `chapters_count` 必须是不少于 3 的整数。
- `chapter_titles` 必须是字符串列表，数量应与 `chapters_count` 一致。

### characters

人物列表，用于集中记录主要角色。

```yaml
characters:
  - id: char-001
    name: 林澈
    role: protagonist
    description: 年轻调查员，沉默克制。
```

- `id`：人物稳定标识。
- `name`：人物名称，必填。
- `role`：人物功能或叙事角色，例如 `protagonist`、`supporting`。
- `description`：人物简介，可由 AI 或作者补充。

### scenes

场次列表，是剧本主体。

```yaml
scenes:
  - id: scene-001
    title: 初遇
    source_chapter: 第 1 章
    location: 街边茶馆
    time: 黄昏
    characters:
      - 林澈
      - 苏晚
    beats:
      - type: action
        text: 林澈推门而入，雨水顺着衣角滴落。
```

- `id`：场次稳定标识。
- `title`：场次标题。
- `source_chapter`：来源章节，便于追溯原文。
- `location`：场景地点。
- `time`：场景时间。
- `characters`：本场登场人物名称列表。
- `beats`：场次内连续发生的动作、对白、旁白和转场。

## beat 类型

`beats` 表示场次内按阅读顺序发生的内容。当前支持：

- `action`：动作或可拍摄行为。
- `dialogue`：人物对白，必须包含 `character`。
- `narration`：必要旁白或来自原文的叙述信息。
- `transition`：场景转场提示。

示例：

```yaml
beats:
  - type: narration
    text: 雨夜让整条街显得格外空。
  - type: action
    text: 林澈停在茶馆门口，抬头看向二楼亮着的窗。
  - type: dialogue
    character: 苏晚
    text: 你终于来了。
  - type: transition
    text: 切至茶馆内。
```

## 当前后端校验规则

后端 `POST /api/scripts/validate` 会执行基础结构校验：

- YAML 必须能被解析为映射结构。
- 顶层必须包含 `script`。
- `script.schema_version` 必须为 `0.1.0`。
- `script.title` 和 `script.logline` 必须为字符串。
- `script.source.type` 必须为 `novel`。
- `script.source.chapters_count` 必须是不少于 3 的整数。
- `script.source.chapter_titles` 必须是字符串列表，数量需与 `chapters_count` 一致。
- `script.characters` 必须是列表，人物项需包含字符串类型的 `id` 和 `name`。
- `script.scenes` 必须是非空列表。
- 场次项需包含字符串类型的 `id`、`title`、`source_chapter`、`location` 和 `time`。
- 场次 `characters` 必须是字符串列表。
- 场次 `beats` 必须是非空列表。
- `beat.type` 仅支持 `action`、`dialogue`、`narration`、`transition`。
- `beat.text` 必须是字符串。
- `dialogue` 类型的 beat 必须包含字符串类型的 `character`。

## 序列化策略

当前后端会先把章节解析结果转换为稳定 YAML 骨架：

- `source.chapter_titles` 保留原章节标题。
- `characters` 初始可为空，后续由 AI 或作者补充。
- 每个章节默认生成一个 `scene-xxx` 场次。
- `source_chapter` 指向原章节标题。
- 原章节正文先放入 `narration` beat，避免信息丢失。

远程 AI Provider 会在骨架基础上补全 logline、人物、场景地点、时间和更多 beat。后端会在返回前再次校验 Schema。

## 设计原因

- 使用 YAML：比 JSON 更适合作者阅读和手工编辑。
- 使用 `scenes`：剧本天然以场次推进，方便后续拆分、排序和导出。
- 使用 `beats`：把动作、对白、旁白和转场放在同一序列中，保留剧本阅读顺序。
- 保留 `source_chapter`：便于作者追溯每个场次来自小说的哪个章节。
- 使用 `schema_version`：为后续字段升级保留兼容空间。
- 集中维护 `characters`：减少人物信息在多个场次中重复和漂移。

## 待完善

- 补充正式 JSON Schema 或 YAML Schema 文件。
- 定义 Markdown、Word、Final Draft 等导出格式映射。
- 增加多幕结构、分集结构和镜头级结构。
- 增加人物关系、场景顺序调整和版本历史字段。
