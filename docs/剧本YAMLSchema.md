# 剧本 YAML Schema

## 设计目标

剧本 YAML Schema 用于约束 AI 输出，使小说改编结果既适合人工阅读，也适合程序校验、编辑和导出。第一版 Schema 聚焦剧本初稿，不追求覆盖所有专业制片格式。

## 顶层结构

```yaml
script:
  schema_version: "0.1.0"
  title: ""
  logline: ""
  source:
    type: novel
    chapters_count: 3
    chapter_titles: []
  characters: []
  scenes: []
```

## 字段说明

### script

剧本根节点。所有剧本数据都放在 `script` 下，便于和其他配置或元数据区分。

### schema_version

Schema 版本号。后续字段升级时，可以通过版本号兼容旧剧本。

### title

剧本标题。默认可以沿用小说标题，也可以由作者后续修改。

### logline

一句话故事梗概。用于快速理解作品核心冲突。

### source

来源信息，用于记录本剧本由小说文本改编而来。

```yaml
source:
  type: novel
  chapters_count: 3
  chapter_titles:
    - 第 1 章
    - 第 2 章
    - 第 3 章
```

### characters

人物列表，用于集中记录主要角色。

```yaml
characters:
  - id: char-001
    name: 林澈
    role: protagonist
    description: 年轻调查员，沉默克制。
```

### scenes

场次列表，是剧本的主体。

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
      - type: dialogue
        character: 苏晚
        text: 你终于来了。
```

## beat 类型

`beats` 表示场次内连续发生的内容。第一版支持以下类型：

- `action`：动作或可拍摄行为。
- `dialogue`：人物对白。
- `narration`：必要旁白。
- `transition`：场景转场提示。

## 设计原因

- 使用 YAML：比 JSON 更适合作者阅读和手工编辑。
- 使用 `scenes`：剧本天然以场次推进，方便后续拆分、排序和导出。
- 使用 `beats`：将动作、对白、旁白和转场放在同一序列中，可以保留剧本阅读顺序。
- 保留 `source_chapter`：方便作者追溯每个场次来自小说的哪个章节。
- 使用 `schema_version`：为后续迭代保留兼容空间。
- 角色集中到 `characters`：减少人物信息在多个场次中重复和漂移。

## 待完善

- 字段必填规则。
- 字段类型的正式 JSON Schema 或 YAML Schema 表达。
- 剧本格式导出规则。
- 多幕结构、分集结构和镜头级结构。
