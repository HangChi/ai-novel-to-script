import { type ChangeEvent, useEffect, useState } from "react";

import "./App.css";

type HealthStatus = "idle" | "checking" | "ok" | "error";
type AIProviderStatusState = "idle" | "loading" | "ready" | "warning" | "error";
type GenerationStatus = "idle" | "generating" | "success" | "error";
type ImportStatus = "idle" | "importing" | "success" | "error";
type ValidationStatus = "idle" | "validating" | "valid" | "invalid" | "error";
type CopyStatus = "idle" | "copying" | "copied" | "error";
type YamlMode = "preview" | "edit";

type StructuredPreviewStatus = "ready" | "empty" | "error";

const BEAT_TYPE_OPTIONS = ["action", "dialogue", "narration", "transition"] as const;

type GenerateScriptResponse = {
  status: "completed";
  schema_version: string;
  yaml: string;
};

type ScriptValidationError = {
  code: string;
  path: string;
  message: string;
};

type ValidateScriptResponse = {
  valid: boolean;
  errors: ScriptValidationError[];
};

type AIProviderStatusResponse = {
  provider: string;
  mode: "local" | "remote" | "unsupported";
  configured: boolean;
  model: string;
  base_url: string;
  missing_config: string[];
};

type ApiErrorResponse = {
  detail?: {
    code?: string;
    message?: string;
  };
};

type StructuredCharacter = {
  id: string;
  name: string;
  role: string;
  description: string;
};

type StructuredBeat = {
  type: string;
  text: string;
  character?: string;
};

type StructuredScene = {
  id: string;
  title: string;
  location: string;
  time: string;
  characters: string[];
  beats: StructuredBeat[];
};

type StructuredScript = {
  title: string;
  logline: string;
  characters: StructuredCharacter[];
  scenes: StructuredScene[];
};

type StructuredPreviewResult =
  | {
      status: "ready";
      script: StructuredScript;
    }
  | {
      status: Exclude<StructuredPreviewStatus, "ready">;
      message: string;
    };

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const SAMPLE_TITLE = "雨夜来信";
const SAMPLE_TEXT = "第 1 章 初遇\n林澈推门而入，雨水顺着衣角滴落。\n\n第 2 章 暗线\n苏晚在旧信封里发现陌生地址。\n\n第 3 章 选择\n两人在清晨的站台前做出决定。";
const INITIAL_YAML = 'script:\n  schema_version: "0.1.0"\n  title: ""\n  scenes: []\n';

function countLikelyChapters(text: string) {
  const matches = text.match(/^\s*(?:#{1,6}\s+)?(?:第\s*(?:\d+|[零〇一二两三四五六七八九十百千万]+)\s*[章节回话]|chapter\s+\d+|\d+\s*[.．、]\s*\S)/gim);

  return matches?.length ?? 0;
}

async function readJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return {};
  }
}

function getApiErrorMessage(payload: unknown) {
  const errorPayload = payload as ApiErrorResponse;
  const code = errorPayload.detail?.code;
  const message = errorPayload.detail?.message;

  if (code && message) {
    return `${code}: ${message}`;
  }

  return "生成失败，请检查后端服务和输入内容。";
}

function getFileTitle(fileName: string) {
  const title = fileName.replace(/\.(?:txt|md|markdown)$/i, "").trim();

  return title || "未命名剧本";
}

function readYamlScalar(rawValue: string) {
  const value = rawValue.trim();

  if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
    return value.slice(1, -1);
  }

  return value;
}

function escapeYamlDoubleQuotedValue(value: string) {
  return value.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
}

function formatYamlStringField(fieldName: string, value: string) {
  return `  ${fieldName}: "${escapeYamlDoubleQuotedValue(value)}"`;
}

function updateScriptStringField(yamlText: string, fieldName: "title" | "logline", value: string) {
  const lines = yamlText.split(/\r?\n/);
  const fieldPattern = new RegExp(`^  ${fieldName}:\\s*.*$`);
  const existingIndex = lines.findIndex((line) => fieldPattern.test(line));
  const formattedLine = formatYamlStringField(fieldName, value);

  if (existingIndex >= 0) {
    lines[existingIndex] = formattedLine;
    return lines.join("\n");
  }

  const schemaIndex = lines.findIndex((line) => /^  schema_version:\s*.*$/.test(line));
  const titleIndex = lines.findIndex((line) => /^  title:\s*.*$/.test(line));
  const insertAfterIndex = fieldName === "title" ? schemaIndex : titleIndex >= 0 ? titleIndex : schemaIndex;

  if (insertAfterIndex >= 0) {
    lines.splice(insertAfterIndex + 1, 0, formattedLine);
    return lines.join("\n");
  }

  const scriptIndex = lines.findIndex((line) => line.trim() === "script:");

  if (scriptIndex >= 0) {
    lines.splice(scriptIndex + 1, 0, formattedLine);
    return lines.join("\n");
  }

  return yamlText;
}

function getSceneRanges(lines: string[]) {
  const scenesIndex = lines.findIndex((line) => /^  scenes:\s*$/.test(line));

  if (scenesIndex < 0) {
    return [];
  }

  const ranges: Array<{ start: number; end: number }> = [];

  for (let index = scenesIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];

    if (line.trim() && (line.match(/^ */)?.[0].length ?? 0) <= 2) {
      break;
    }

    if (/^    -\s+id:\s*.*$/.test(line)) {
      const previousRange = ranges[ranges.length - 1];

      if (previousRange) {
        previousRange.end = index;
      }

      ranges.push({ start: index, end: lines.length });
    }
  }

  const lastRange = ranges[ranges.length - 1];

  if (lastRange) {
    for (let index = lastRange.start + 1; index < lines.length; index += 1) {
      const line = lines[index];

      if (line.trim() && (line.match(/^ */)?.[0].length ?? 0) <= 2) {
        lastRange.end = index;
        break;
      }
    }
  }

  return ranges;
}

function getSceneFieldOrder(line: string) {
  if (/^    -\s+id:\s*.*$/.test(line)) {
    return 0;
  }

  const match = line.match(/^      (title|source_chapter|location|time|characters|beats):/);

  if (!match) {
    return -1;
  }

  return ["id", "title", "source_chapter", "location", "time", "characters", "beats"].indexOf(match[1]);
}

function updateSceneStringField(
  yamlText: string,
  sceneIndex: number,
  fieldName: "title" | "location" | "time",
  value: string,
) {
  const lines = yamlText.split(/\r?\n/);
  const range = getSceneRanges(lines)[sceneIndex];

  if (!range) {
    return yamlText;
  }

  const fieldPattern = new RegExp(`^      ${fieldName}:\\s*.*$`);
  const formattedLine = `      ${fieldName}: "${escapeYamlDoubleQuotedValue(value)}"`;

  for (let index = range.start + 1; index < range.end; index += 1) {
    if (fieldPattern.test(lines[index])) {
      lines[index] = formattedLine;
      return lines.join("\n");
    }
  }

  const targetOrder = getSceneFieldOrder(`      ${fieldName}:`);
  let insertAfterIndex = range.start;

  for (let index = range.start; index < range.end; index += 1) {
    const fieldOrder = getSceneFieldOrder(lines[index]);

    if (fieldOrder >= 0 && fieldOrder < targetOrder) {
      insertAfterIndex = index;
    }
  }

  lines.splice(insertAfterIndex + 1, 0, formattedLine);
  return lines.join("\n");
}

function getBeatRanges(lines: string[], sceneRange: { start: number; end: number }) {
  const beatsIndex = lines.findIndex((line, index) => {
    return index > sceneRange.start && index < sceneRange.end && /^      beats:\s*(?:\[\])?\s*$/.test(line);
  });

  if (beatsIndex < 0 || /\[\]\s*$/.test(lines[beatsIndex])) {
    return { beatsIndex, ranges: [] };
  }

  const ranges: Array<{ start: number; end: number }> = [];

  for (let index = beatsIndex + 1; index < sceneRange.end; index += 1) {
    const line = lines[index];

    if (line.trim() && (line.match(/^ */)?.[0].length ?? 0) <= 6) {
      break;
    }

    if (/^        -\s+type:\s*.*$/.test(line)) {
      const previousRange = ranges[ranges.length - 1];

      if (previousRange) {
        previousRange.end = index;
      }

      ranges.push({ start: index, end: sceneRange.end });
    }
  }

  const lastRange = ranges[ranges.length - 1];

  if (lastRange) {
    for (let index = lastRange.start + 1; index < sceneRange.end; index += 1) {
      const line = lines[index];

      if (/^        -\s+type:\s*.*$/.test(line) || (line.trim() && (line.match(/^ */)?.[0].length ?? 0) <= 6)) {
        lastRange.end = index;
        break;
      }
    }
  }

  return { beatsIndex, ranges };
}

function ensureDialogueCharacter(lines: string[], beatRange: { start: number; end: number }) {
  for (let index = beatRange.start + 1; index < beatRange.end; index += 1) {
    if (/^          character:\s*.*$/.test(lines[index])) {
      return;
    }
  }

  lines.splice(beatRange.start + 1, 0, '          character: "TBD"');
  beatRange.end += 1;
}

function updateBeatStringField(
  yamlText: string,
  sceneIndex: number,
  beatIndex: number,
  fieldName: "type" | "text" | "character",
  value: string,
) {
  const lines = yamlText.split(/\r?\n/);
  const sceneRange = getSceneRanges(lines)[sceneIndex];

  if (!sceneRange) {
    return yamlText;
  }

  const beatRange = getBeatRanges(lines, sceneRange).ranges[beatIndex];

  if (!beatRange) {
    return yamlText;
  }

  if (fieldName === "type") {
    lines[beatRange.start] = `        - type: "${escapeYamlDoubleQuotedValue(value)}"`;

    if (value === "dialogue") {
      ensureDialogueCharacter(lines, beatRange);
    }

    return lines.join("\n");
  }

  if (fieldName === "character") {
    const characterLine = `          character: "${escapeYamlDoubleQuotedValue(value)}"`;

    for (let index = beatRange.start + 1; index < beatRange.end; index += 1) {
      if (/^          character:\s*.*$/.test(lines[index])) {
        lines[index] = characterLine;
        return lines.join("\n");
      }
    }

    lines.splice(beatRange.start + 1, 0, characterLine);
    return lines.join("\n");
  }

  const formattedLine = `          text: "${escapeYamlDoubleQuotedValue(value)}"`;

  for (let index = beatRange.start + 1; index < beatRange.end; index += 1) {
    if (/^          text:\s*.*$/.test(lines[index])) {
      lines[index] = formattedLine;
      return lines.join("\n");
    }
  }

  let insertAfterIndex = beatRange.start;

  for (let index = beatRange.start + 1; index < beatRange.end; index += 1) {
    if (/^          character:\s*.*$/.test(lines[index])) {
      insertAfterIndex = index;
    }
  }

  lines.splice(insertAfterIndex + 1, 0, formattedLine);
  return lines.join("\n");
}

function nextSceneId(lines: string[]) {
  let max = 0;

  for (const line of lines) {
    const match = line.match(/id:\s*"?scene-(\d+)"?/);

    if (match) {
      max = Math.max(max, Number(match[1]));
    }
  }

  return `scene-${String(max + 1).padStart(3, "0")}`;
}

function addScene(yamlText: string) {
  const lines = yamlText.split(/\r?\n/);
  const nextId = nextSceneId(lines);
  const block = [
    `    - id: ${nextId}`,
    '      title: ""',
    '      source_chapter: ""',
    '      location: ""',
    '      time: ""',
    '      characters: []',
    '      beats:',
    '        - type: "narration"',
    '          text: ""',
  ];

  const emptyIndex = lines.findIndex((line) => /^  scenes:\s*\[\]\s*$/.test(line));

  if (emptyIndex >= 0) {
    lines[emptyIndex] = "  scenes:";
    lines.splice(emptyIndex + 1, 0, ...block);
    return lines.join("\n");
  }

  const ranges = getSceneRanges(lines);

  if (ranges.length === 0) {
    const scenesIndex = lines.findIndex((line) => /^  scenes:\s*$/.test(line));

    if (scenesIndex < 0) {
      return yamlText;
    }

    lines.splice(scenesIndex + 1, 0, ...block);
    return lines.join("\n");
  }

  const lastRange = ranges[ranges.length - 1];
  lines.splice(lastRange.end, 0, ...block);
  return lines.join("\n");
}

function removeScene(yamlText: string, sceneIndex: number) {
  const lines = yamlText.split(/\r?\n/);
  const ranges = getSceneRanges(lines);
  const range = ranges[sceneIndex];

  if (!range || ranges.length <= 1) {
    return yamlText;
  }

  lines.splice(range.start, range.end - range.start);
  return lines.join("\n");
}

function addBeatToScene(yamlText: string, sceneIndex: number) {
  const lines = yamlText.split(/\r?\n/);
  const sceneRange = getSceneRanges(lines)[sceneIndex];

  if (!sceneRange) {
    return yamlText;
  }

  const beatLines = ['        - type: "narration"', '          text: ""'];
  const beatsInfo = getBeatRanges(lines, sceneRange);

  if (beatsInfo.beatsIndex >= 0) {
    if (/\[\]\s*$/.test(lines[beatsInfo.beatsIndex])) {
      lines[beatsInfo.beatsIndex] = "      beats:";
      lines.splice(beatsInfo.beatsIndex + 1, 0, ...beatLines);
      return lines.join("\n");
    }

    const lastBeatRange = beatsInfo.ranges[beatsInfo.ranges.length - 1];
    const insertAtIndex = lastBeatRange ? lastBeatRange.end : beatsInfo.beatsIndex + 1;
    lines.splice(insertAtIndex, 0, ...beatLines);
    return lines.join("\n");
  }

  const targetOrder = getSceneFieldOrder("      beats:");
  let insertAfterIndex = sceneRange.start;

  for (let index = sceneRange.start; index < sceneRange.end; index += 1) {
    const fieldOrder = getSceneFieldOrder(lines[index]);

    if (fieldOrder >= 0 && fieldOrder < targetOrder) {
      insertAfterIndex = index;
    }
  }

  lines.splice(insertAfterIndex + 1, 0, "      beats:", ...beatLines);
  return lines.join("\n");
}

function removeBeatFromScene(yamlText: string, sceneIndex: number, beatIndex: number) {
  const lines = yamlText.split(/\r?\n/);
  const sceneRange = getSceneRanges(lines)[sceneIndex];

  if (!sceneRange) {
    return yamlText;
  }

  const beatRanges = getBeatRanges(lines, sceneRange).ranges;
  const beatRange = beatRanges[beatIndex];

  if (!beatRange || beatRanges.length <= 1) {
    return yamlText;
  }

  lines.splice(beatRange.start, beatRange.end - beatRange.start);
  return lines.join("\n");
}

function getSceneCharacterInfo(lines: string[], sceneRange: { start: number; end: number }) {
  const charactersIndex = lines.findIndex(
    (line, index) =>
      index > sceneRange.start &&
      index < sceneRange.end &&
      /^      characters:\s*(?:\[\])?\s*$/.test(line),
  );

  if (charactersIndex < 0 || /\[\]\s*$/.test(lines[charactersIndex])) {
    return { charactersIndex, items: [] as number[] };
  }

  const items: number[] = [];

  for (let index = charactersIndex + 1; index < sceneRange.end; index += 1) {
    const line = lines[index];

    if (line.trim() && (line.match(/^ */)?.[0].length ?? 0) <= 6) {
      break;
    }

    if (/^        -\s*.*$/.test(line)) {
      items.push(index);
    }
  }

  return { charactersIndex, items };
}

function updateSceneCharacter(yamlText: string, sceneIndex: number, characterIndex: number, value: string) {
  const lines = yamlText.split(/\r?\n/);
  const sceneRange = getSceneRanges(lines)[sceneIndex];

  if (!sceneRange) {
    return yamlText;
  }

  const lineIndex = getSceneCharacterInfo(lines, sceneRange).items[characterIndex];

  if (lineIndex === undefined) {
    return yamlText;
  }

  lines[lineIndex] = `        - "${escapeYamlDoubleQuotedValue(value)}"`;
  return lines.join("\n");
}

function addSceneCharacter(yamlText: string, sceneIndex: number) {
  const lines = yamlText.split(/\r?\n/);
  const sceneRange = getSceneRanges(lines)[sceneIndex];

  if (!sceneRange) {
    return yamlText;
  }

  const info = getSceneCharacterInfo(lines, sceneRange);

  if (info.charactersIndex < 0) {
    return yamlText;
  }

  const newLine = '        - ""';

  if (/\[\]\s*$/.test(lines[info.charactersIndex])) {
    lines[info.charactersIndex] = "      characters:";
    lines.splice(info.charactersIndex + 1, 0, newLine);
    return lines.join("\n");
  }

  const lastItem = info.items[info.items.length - 1];
  const insertAtIndex = lastItem !== undefined ? lastItem + 1 : info.charactersIndex + 1;
  lines.splice(insertAtIndex, 0, newLine);
  return lines.join("\n");
}

function removeSceneCharacter(yamlText: string, sceneIndex: number, characterIndex: number) {
  const lines = yamlText.split(/\r?\n/);
  const sceneRange = getSceneRanges(lines)[sceneIndex];

  if (!sceneRange) {
    return yamlText;
  }

  const info = getSceneCharacterInfo(lines, sceneRange);
  const lineIndex = info.items[characterIndex];

  if (lineIndex === undefined) {
    return yamlText;
  }

  lines.splice(lineIndex, 1);

  if (info.items.length === 1) {
    lines[info.charactersIndex] = "      characters: []";
  }

  return lines.join("\n");
}

function getIndentedSection(lines: string[], startIndex: number, parentIndent: number) {
  const section: string[] = [];

  for (let index = startIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];

    if (!line.trim()) {
      section.push(line);
      continue;
    }

    const indent = line.match(/^ */)?.[0].length ?? 0;

    if (indent <= parentIndent) {
      break;
    }

    section.push(line);
  }

  return section;
}

function readScriptField(lines: string[], fieldName: string) {
  const fieldPattern = new RegExp(`^  ${fieldName}:\\s*(.*)$`);
  const line = lines.find((candidate) => fieldPattern.test(candidate));
  const match = line?.match(fieldPattern);

  return match ? readYamlScalar(match[1]) : "";
}

function getCharacterRanges(lines: string[]) {
  const charactersIndex = lines.findIndex((line) => /^  characters:\s*$/.test(line));

  if (charactersIndex < 0) {
    return { charactersIndex, ranges: [] as Array<{ start: number; end: number }> };
  }

  const ranges: Array<{ start: number; end: number }> = [];

  for (let index = charactersIndex + 1; index < lines.length; index += 1) {
    const line = lines[index];

    if (line.trim() && (line.match(/^ */)?.[0].length ?? 0) <= 2) {
      break;
    }

    if (/^    -\s+id:\s*.*$/.test(line)) {
      const previousRange = ranges[ranges.length - 1];

      if (previousRange) {
        previousRange.end = index;
      }

      ranges.push({ start: index, end: lines.length });
    }
  }

  const lastRange = ranges[ranges.length - 1];

  if (lastRange) {
    for (let index = lastRange.start + 1; index < lines.length; index += 1) {
      const line = lines[index];

      if (line.trim() && (line.match(/^ */)?.[0].length ?? 0) <= 2) {
        lastRange.end = index;
        break;
      }
    }
  }

  return { charactersIndex, ranges };
}

function getCharacterFieldOrder(fieldName: "id" | "name" | "role" | "description") {
  return ["id", "name", "role", "description"].indexOf(fieldName);
}

function nextCharacterId(lines: string[]) {
  let max = 0;

  for (const line of lines) {
    const match = line.match(/id:\s*"?char-(\d+)"?/);

    if (match) {
      max = Math.max(max, Number(match[1]));
    }
  }

  return `char-${String(max + 1).padStart(3, "0")}`;
}

function updateCharacterField(
  yamlText: string,
  characterIndex: number,
  fieldName: "name" | "role" | "description",
  value: string,
) {
  const lines = yamlText.split(/\r?\n/);
  const range = getCharacterRanges(lines).ranges[characterIndex];

  if (!range) {
    return yamlText;
  }

  const fieldPattern = new RegExp(`^      ${fieldName}:\\s*.*$`);
  const formattedLine = `      ${fieldName}: "${escapeYamlDoubleQuotedValue(value)}"`;

  for (let index = range.start + 1; index < range.end; index += 1) {
    if (fieldPattern.test(lines[index])) {
      lines[index] = formattedLine;
      return lines.join("\n");
    }
  }

  const targetOrder = getCharacterFieldOrder(fieldName);
  let insertAfterIndex = range.start;

  for (let index = range.start; index < range.end; index += 1) {
    const fieldMatch = lines[index].match(/^      (name|role|description):/);
    const order = /^    -\s+id:\s*.*$/.test(lines[index])
      ? 0
      : fieldMatch
        ? getCharacterFieldOrder(fieldMatch[1] as "name" | "role" | "description")
        : -1;

    if (order >= 0 && order < targetOrder) {
      insertAfterIndex = index;
    }
  }

  lines.splice(insertAfterIndex + 1, 0, formattedLine);
  return lines.join("\n");
}

function addCharacter(yamlText: string) {
  const lines = yamlText.split(/\r?\n/);
  const nextId = nextCharacterId(lines);
  const block = [
    `    - id: "${nextId}"`,
    '      name: ""',
    '      role: ""',
    '      description: ""',
  ];

  const emptyIndex = lines.findIndex((line) => /^  characters:\s*\[\]\s*$/.test(line));

  if (emptyIndex >= 0) {
    lines[emptyIndex] = "  characters:";
    lines.splice(emptyIndex + 1, 0, ...block);
    return lines.join("\n");
  }

  const info = getCharacterRanges(lines);

  if (info.charactersIndex < 0) {
    return yamlText;
  }

  const lastRange = info.ranges[info.ranges.length - 1];
  const insertAtIndex = lastRange ? lastRange.end : info.charactersIndex + 1;
  lines.splice(insertAtIndex, 0, ...block);
  return lines.join("\n");
}

function removeCharacter(yamlText: string, characterIndex: number) {
  const lines = yamlText.split(/\r?\n/);
  const range = getCharacterRanges(lines).ranges[characterIndex];

  if (!range) {
    return yamlText;
  }

  lines.splice(range.start, range.end - range.start);

  const after = getCharacterRanges(lines);

  if (after.charactersIndex >= 0 && after.ranges.length === 0) {
    lines[after.charactersIndex] = "  characters: []";
  }

  return lines.join("\n");
}

function parseStructuredCharacters(lines: string[]) {
  const charactersIndex = lines.findIndex((line) => /^  characters:\s*(?:\[\])?\s*$/.test(line));

  if (charactersIndex < 0 || /\[\]\s*$/.test(lines[charactersIndex])) {
    return [];
  }

  const characters: StructuredCharacter[] = [];
  const section = getIndentedSection(lines, charactersIndex, 2);
  let currentCharacter: StructuredCharacter | null = null;

  for (const line of section) {
    const itemMatch = line.match(/^    -\s+id:\s*(.*)$/);
    const fieldMatch = line.match(/^      (name|role|description):\s*(.*)$/);

    if (itemMatch) {
      currentCharacter = {
        id: readYamlScalar(itemMatch[1]),
        name: "",
        role: "",
        description: "",
      };
      characters.push(currentCharacter);
      continue;
    }

    if (currentCharacter && fieldMatch) {
      currentCharacter[fieldMatch[1] as keyof Omit<StructuredCharacter, "id">] = readYamlScalar(fieldMatch[2]);
    }
  }

  return characters;
}

function parseStructuredScenes(lines: string[]) {
  const scenesIndex = lines.findIndex((line) => /^  scenes:\s*(?:\[\])?\s*$/.test(line));

  if (scenesIndex < 0 || /\[\]\s*$/.test(lines[scenesIndex])) {
    return [];
  }

  const scenes: StructuredScene[] = [];
  const section = getIndentedSection(lines, scenesIndex, 2);
  let currentScene: StructuredScene | null = null;
  let currentBeat: StructuredBeat | null = null;
  let mode: "sceneCharacters" | "beats" | null = null;

  for (const line of section) {
    const sceneMatch = line.match(/^    -\s+id:\s*(.*)$/);

    if (sceneMatch) {
      currentScene = {
        id: readYamlScalar(sceneMatch[1]),
        title: "",
        location: "",
        time: "",
        characters: [],
        beats: [],
      };
      currentBeat = null;
      mode = null;
      scenes.push(currentScene);
      continue;
    }

    if (!currentScene) {
      continue;
    }

    const sceneFieldMatch = line.match(/^      (title|location|time):\s*(.*)$/);

    if (sceneFieldMatch) {
      currentScene[sceneFieldMatch[1] as keyof Pick<StructuredScene, "title" | "location" | "time">] = readYamlScalar(sceneFieldMatch[2]);
      mode = null;
      continue;
    }

    if (/^      characters:\s*\[\]\s*$/.test(line)) {
      currentScene.characters = [];
      mode = null;
      continue;
    }

    if (/^      characters:\s*$/.test(line)) {
      mode = "sceneCharacters";
      continue;
    }

    if (/^      beats:\s*(?:\[\])?\s*$/.test(line)) {
      mode = /\[\]\s*$/.test(line) ? null : "beats";
      currentBeat = null;
      continue;
    }

    if (mode === "sceneCharacters") {
      const characterMatch = line.match(/^        -\s*(.*)$/);

      if (characterMatch) {
        currentScene.characters.push(readYamlScalar(characterMatch[1]));
      }

      continue;
    }

    if (mode === "beats") {
      const beatMatch = line.match(/^        -\s+type:\s*(.*)$/);
      const beatFieldMatch = line.match(/^          (text|character):\s*(.*)$/);

      if (beatMatch) {
        currentBeat = {
          type: readYamlScalar(beatMatch[1]),
          text: "",
        };
        currentScene.beats.push(currentBeat);
        continue;
      }

      if (currentBeat && beatFieldMatch) {
        currentBeat[beatFieldMatch[1] as keyof Pick<StructuredBeat, "text" | "character">] = readYamlScalar(beatFieldMatch[2]);
      }
    }
  }

  return scenes;
}

function parseStructuredScriptPreview(yamlText: string): StructuredPreviewResult {
  if (!yamlText.trim()) {
    return {
      status: "empty",
      message: "暂无 YAML 内容可预览。",
    };
  }

  const lines = yamlText.split(/\r?\n/);

  if (!lines.some((line) => line.trim() === "script:")) {
    return {
      status: "error",
      message: "未找到 script 根节点，暂时无法生成结构化预览。",
    };
  }

  const script = {
    title: readScriptField(lines, "title"),
    logline: readScriptField(lines, "logline"),
    characters: parseStructuredCharacters(lines),
    scenes: parseStructuredScenes(lines),
  };

  if (!script.title && !script.logline && script.characters.length === 0 && script.scenes.length === 0) {
    return {
      status: "empty",
      message: "当前 YAML 还没有可展示的剧本标题、人物或场景。",
    };
  }

  return {
    status: "ready",
    script,
  };
}

function displayValue(value: string, fallback = "未填写") {
  return value.trim() || fallback;
}

function getAIProviderName(status: AIProviderStatusResponse | null) {
  if (!status) {
    return "AI 状态";
  }

  if (status.provider === "local") {
    return "本地骨架";
  }

  if (status.provider === "deepseek") {
    return "DeepSeek";
  }

  if (status.provider === "openai") {
    return "OpenAI-compatible";
  }

  return status.provider;
}

function getAIProviderDetail(status: AIProviderStatusResponse | null) {
  if (!status) {
    return "未检测";
  }

  if (status.mode === "unsupported") {
    return "不支持的 Provider";
  }

  if (!status.configured) {
    return `缺少 ${status.missing_config.join(", ")}`;
  }

  if (status.mode === "local") {
    return "配置正常，无需密钥";
  }

  return `${status.model} · 配置正常`;
}

function getAIProviderGenerationLabel(status: AIProviderStatusResponse | null) {
  const providerName = getAIProviderName(status);

  return providerName === "AI 状态" ? "AI Provider" : providerName;
}

function App() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("idle");
  const [healthMessage, setHealthMessage] = useState("未检测");
  const [aiProviderStatusState, setAIProviderStatusState] = useState<AIProviderStatusState>("idle");
  const [aiProviderStatus, setAIProviderStatus] = useState<AIProviderStatusResponse | null>(null);
  const [generationStatus, setGenerationStatus] = useState<GenerationStatus>("idle");
  const [generationMessage, setGenerationMessage] = useState("待生成");
  const [importStatus, setImportStatus] = useState<ImportStatus>("idle");
  const [importMessage, setImportMessage] = useState("");
  const [validationStatus, setValidationStatus] = useState<ValidationStatus>("idle");
  const [validationMessage, setValidationMessage] = useState("待校验");
  const [validationErrors, setValidationErrors] = useState<ScriptValidationError[]>([]);
  const [copyStatus, setCopyStatus] = useState<CopyStatus>("idle");
  const [yamlMode, setYamlMode] = useState<YamlMode>("preview");
  const [scriptTitle, setScriptTitle] = useState(SAMPLE_TITLE);
  const [sourceText, setSourceText] = useState(SAMPLE_TEXT);
  const [yamlText, setYamlText] = useState(INITIAL_YAML);
  const [structuredSyncMessage, setStructuredSyncMessage] = useState("等待 YAML 内容");

  const characterCount = sourceText.trim().length;
  const chapterCount = countLikelyChapters(sourceText);
  const isGenerating = generationStatus === "generating";
  const isProviderBlocked =
    Boolean(aiProviderStatus && !aiProviderStatus.configured) || aiProviderStatus?.mode === "unsupported";
  const isValidating = validationStatus === "validating";
  const isCopying = copyStatus === "copying";
  const inputMessage = importStatus === "idle" ? generationMessage : importMessage;
  const inputMessageStatus = importStatus === "idle" ? generationStatus : importStatus;
  const copyButtonLabel = copyStatus === "copied" ? "已复制" : copyStatus === "error" ? "复制失败" : "复制 YAML";
  const structuredPreview = parseStructuredScriptPreview(yamlText);

  useEffect(() => {
    void checkAIProviderStatus();
  }, []);

  function resetValidationState(message = "待校验") {
    setValidationStatus("idle");
    setValidationMessage(message);
    setValidationErrors([]);
  }

  function updateYamlText(nextYamlText: string, syncMessage = "YAML 已修改，结构化视图会重新解析。") {
    setYamlText(nextYamlText);
    resetValidationState("YAML 已修改，待校验");
    setCopyStatus("idle");
    setStructuredSyncMessage(syncMessage);
  }

  function updateStructuredYamlText(nextYamlText: string) {
    updateYamlText(nextYamlText, "结构化修改已同步到 YAML，可直接校验、复制或下载。");
  }

  function updateScriptMetadata(fieldName: "title" | "logline", value: string) {
    updateStructuredYamlText(updateScriptStringField(yamlText, fieldName, value));
  }

  function updateSceneMetadata(sceneIndex: number, fieldName: "title" | "location" | "time", value: string) {
    updateStructuredYamlText(updateSceneStringField(yamlText, sceneIndex, fieldName, value));
  }

  function updateBeatMetadata(sceneIndex: number, beatIndex: number, fieldName: "type" | "text" | "character", value: string) {
    updateStructuredYamlText(updateBeatStringField(yamlText, sceneIndex, beatIndex, fieldName, value));
  }

  function updateCharacterMetadata(characterIndex: number, fieldName: "name" | "role" | "description", value: string) {
    updateStructuredYamlText(updateCharacterField(yamlText, characterIndex, fieldName, value));
  }

  function addCharacterEntry() {
    updateStructuredYamlText(addCharacter(yamlText));
  }

  function removeCharacterEntry(characterIndex: number) {
    updateStructuredYamlText(removeCharacter(yamlText, characterIndex));
  }

  function addSceneBeat(sceneIndex: number) {
    updateStructuredYamlText(addBeatToScene(yamlText, sceneIndex));
  }

  function removeSceneBeat(sceneIndex: number, beatIndex: number) {
    updateStructuredYamlText(removeBeatFromScene(yamlText, sceneIndex, beatIndex));
  }

  function updateSceneCharacterEntry(sceneIndex: number, characterIndex: number, value: string) {
    updateStructuredYamlText(updateSceneCharacter(yamlText, sceneIndex, characterIndex, value));
  }

  function addSceneCharacterEntry(sceneIndex: number) {
    updateStructuredYamlText(addSceneCharacter(yamlText, sceneIndex));
  }

  function removeSceneCharacterEntry(sceneIndex: number, characterIndex: number) {
    updateStructuredYamlText(removeSceneCharacter(yamlText, sceneIndex, characterIndex));
  }

  function addSceneEntry() {
    updateStructuredYamlText(addScene(yamlText));
  }

  function removeSceneEntry(sceneIndex: number) {
    updateStructuredYamlText(removeScene(yamlText, sceneIndex));
  }

  async function checkBackend() {
    setHealthStatus("checking");
    setHealthMessage("检测中");

    try {
      const response = await fetch(`${API_BASE_URL}/api/health`);

      if (!response.ok) {
        throw new Error(`Health check failed with ${response.status}`);
      }

      const payload = (await response.json()) as { status?: string };

      if (payload.status !== "ok") {
        throw new Error("Unexpected health response");
      }

      setHealthStatus("ok");
      setHealthMessage("已连接");
      await checkAIProviderStatus();
    } catch {
      setHealthStatus("error");
      setHealthMessage("未连接");
    }
  }

  async function checkAIProviderStatus() {
    setAIProviderStatusState("loading");

    try {
      const response = await fetch(`${API_BASE_URL}/api/ai/status`);

      if (!response.ok) {
        throw new Error(`AI status check failed with ${response.status}`);
      }

      const payload = (await response.json()) as AIProviderStatusResponse;

      setAIProviderStatus(payload);
      setAIProviderStatusState(payload.configured && payload.mode !== "unsupported" ? "ready" : "warning");
    } catch {
      setAIProviderStatus(null);
      setAIProviderStatusState("error");
    }
  }

  async function generateScript() {
    setGenerationStatus("generating");
    setGenerationMessage(`正在调用 ${getAIProviderGenerationLabel(aiProviderStatus)} 生成`);
    setImportStatus("idle");
    resetValidationState("生成中，待校验");
    setCopyStatus("idle");

    try {
      const response = await fetch(`${API_BASE_URL}/api/scripts/generate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          title: scriptTitle,
          content: sourceText,
          output_format: "yaml",
        }),
      });
      const payload = await readJsonSafely(response);

      if (!response.ok) {
        throw new Error(getApiErrorMessage(payload));
      }

      const result = payload as GenerateScriptResponse;

      updateYamlText(result.yaml, "生成结果已同步到 YAML 和结构化视图。");
      setYamlMode("preview");
      setGenerationStatus("success");
      setGenerationMessage(`${getAIProviderGenerationLabel(aiProviderStatus)} 已生成 schema ${result.schema_version}`);
      setValidationMessage("已生成，待校验");
    } catch (error) {
      setGenerationStatus("error");
      setGenerationMessage(error instanceof Error ? error.message : "生成失败，请稍后重试。");
    }
  }

  async function validateYaml() {
    setValidationStatus("validating");
    setValidationMessage("校验中");
    setValidationErrors([]);

    try {
      const response = await fetch(`${API_BASE_URL}/api/scripts/validate`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          schema_version: "0.1.0",
          yaml: yamlText,
        }),
      });
      const payload = await readJsonSafely(response);

      if (!response.ok) {
        throw new Error(getApiErrorMessage(payload));
      }

      const result = payload as ValidateScriptResponse;

      if (result.valid) {
        setValidationStatus("valid");
        setValidationMessage("YAML 结构有效");
        setValidationErrors([]);
        return;
      }

      setValidationStatus("invalid");
      setValidationMessage(`发现 ${result.errors.length} 个结构问题`);
      setValidationErrors(result.errors);
    } catch (error) {
      setValidationStatus("error");
      setValidationMessage(error instanceof Error ? error.message : "校验失败，请稍后重试。");
      setValidationErrors([]);
    }
  }

  async function copyYaml() {
    setCopyStatus("copying");

    try {
      if (!navigator.clipboard?.writeText) {
        throw new Error("Clipboard is unavailable.");
      }

      await navigator.clipboard.writeText(yamlText);
      setCopyStatus("copied");
      window.setTimeout(() => setCopyStatus("idle"), 1600);
    } catch {
      setCopyStatus("error");
    }
  }

  function downloadYaml() {
    const blob = new Blob([yamlText], { type: "application/x-yaml;charset=utf-8" });
    const downloadUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");

    link.href = downloadUrl;
    link.download = "script-draft.yaml";
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 0);
  }

  function resetSourceText() {
    setScriptTitle(SAMPLE_TITLE);
    setSourceText(SAMPLE_TEXT);
    setGenerationStatus("idle");
    setGenerationMessage("待生成");
    setImportStatus("idle");
    setImportMessage("");
  }

  function resetYamlText() {
    updateYamlText(INITIAL_YAML, "已重置为初始 YAML，结构化视图会重新解析。");
    setYamlMode("preview");
    setGenerationStatus("idle");
    setGenerationMessage("待生成");
    setValidationMessage("已重置，待校验");
  }

  async function importSourceFile(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget;
    const file = input.files?.[0];

    if (!file) {
      return;
    }

    setImportStatus("importing");
    setImportMessage("导入中");

    try {
      const text = await file.text();

      if (!text.trim()) {
        throw new Error("文件内容不能为空。");
      }

      setScriptTitle(getFileTitle(file.name));
      setSourceText(text);
      setGenerationStatus("idle");
      setGenerationMessage("待生成");
      setImportStatus("success");
      setImportMessage(`已导入 ${file.name}`);
      resetValidationState("导入新文本后待生成");
      setCopyStatus("idle");
    } catch (error) {
      setImportStatus("error");
      setImportMessage(error instanceof Error ? error.message : "导入失败，请选择文本文件。");
    } finally {
      input.value = "";
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-block">
          <p className="eyebrow">AI Novel to Script</p>
          <h1>小说转剧本工作台</h1>
        </div>
        <div className="topbar-actions">
          <div className={`ai-status-card ${aiProviderStatusState}`} data-testid="ai-provider-status">
            <span>AI</span>
            <strong>{getAIProviderName(aiProviderStatus)}</strong>
            <small>{aiProviderStatusState === "loading" ? "检测中" : getAIProviderDetail(aiProviderStatus)}</small>
          </div>
          <span className={`status-pill ${healthStatus}`}>{healthMessage}</span>
          <button
            className="status-button"
            type="button"
            onClick={checkBackend}
            disabled={healthStatus === "checking"}
          >
            {healthStatus === "checking" ? "检测中..." : "检测后端"}
          </button>
        </div>
      </header>

      <aside className="summary-rail" aria-label="草稿概览">
        <div className="metric-block">
          <span>章节</span>
          <strong>{chapterCount}</strong>
        </div>
        <div className="metric-block">
          <span>字数</span>
          <strong>{characterCount}</strong>
        </div>
        <div className="metric-block">
          <span>状态</span>
          <strong>{chapterCount >= 3 ? "可生成" : "待补全"}</strong>
        </div>
      </aside>

      <main className="workspace-shell">
        <section className="editor-panel input-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Source</p>
              <h2>小说文本</h2>
            </div>
            <div className="panel-actions">
              <label className="ghost-button file-import-button">
                导入文件
                <input
                  data-testid="source-file-input"
                  type="file"
                  accept=".txt,.md,text/plain,text/markdown"
                  onChange={importSourceFile}
                />
              </label>
              <button className="ghost-button" type="button" onClick={resetSourceText}>
                示例
              </button>
              <button
                className="ghost-button"
                type="button"
                onClick={() => {
                  setSourceText("");
                  setImportStatus("idle");
                  setImportMessage("");
                }}
              >
                清空
              </button>
            </div>
          </div>
          <label className="title-field">
            <span>剧本标题</span>
            <input
              aria-label="剧本标题"
              data-testid="script-title-input"
              value={scriptTitle}
              onChange={(event) => setScriptTitle(event.target.value)}
              placeholder="未命名剧本"
            />
          </label>
          <textarea
            aria-label="小说文本输入"
            data-testid="source-text-input"
            value={sourceText}
            onChange={(event) => setSourceText(event.target.value)}
            placeholder={"第 1 章 ...\n\n第 2 章 ...\n\n第 3 章 ..."}
          />
          <div className="panel-footer">
            <span className={`generation-message ${inputMessageStatus}`}>{inputMessage}</span>
            <button
              className="generate-button"
              data-testid="generate-yaml-button"
              type="button"
              onClick={generateScript}
              disabled={isGenerating || isProviderBlocked}
            >
              {isGenerating ? "生成中..." : "生成 YAML"}
            </button>
          </div>
        </section>

        <section className="editor-panel structure-panel structured-preview-panel" data-testid="structured-preview" aria-label="YAML 结构化预览">
            <div className="panel-heading structured-preview-heading">
              <div>
                <p className="panel-kicker">Structure</p>
                <h3>结构化预览</h3>
              </div>
              <span>
                {structuredPreview.status === "ready"
                  ? `${structuredPreview.script.scenes.length} 场景`
                  : "待解析"}
              </span>
            </div>
            {structuredPreview.status === "ready" ? (
              <div className="structured-preview-content">
                <p className="structured-sync-status" data-testid="structured-sync-status">
                  {structuredSyncMessage}
                </p>
                <div className="script-overview">
                  <div className="script-field">
                    <label htmlFor="structured-title-input">剧本标题</label>
                    <input
                      id="structured-title-input"
                      data-testid="structured-title-input"
                      value={structuredPreview.script.title}
                      onChange={(event) => updateScriptMetadata("title", event.target.value)}
                      placeholder="未填写"
                    />
                  </div>
                  <div className="script-field logline-field">
                    <label htmlFor="structured-logline-input">Logline</label>
                    <textarea
                      id="structured-logline-input"
                      data-testid="structured-logline-input"
                      value={structuredPreview.script.logline}
                      onChange={(event) => updateScriptMetadata("logline", event.target.value)}
                      placeholder="未填写"
                      rows={3}
                    />
                  </div>
                </div>

                <div className="structured-section">
                  <div className="structured-section-heading">
                    <strong>人物</strong>
                    <span>{structuredPreview.script.characters.length}</span>
                  </div>
                  {structuredPreview.script.characters.length > 0 ? (
                    <ul className="character-editor-list">
                      {structuredPreview.script.characters.map((character, index) => (
                        <li key={`${character.id}-${index}`} data-testid="structured-character">
                          <div className="character-field-grid">
                            <div className="character-field">
                              <label htmlFor={`structured-character-name-input-${index}`}>姓名</label>
                              <input
                                id={`structured-character-name-input-${index}`}
                                data-testid={`structured-character-name-input-${index}`}
                                value={character.name}
                                onChange={(event) => updateCharacterMetadata(index, "name", event.target.value)}
                                placeholder={character.id || "未命名人物"}
                              />
                            </div>
                            <div className="character-field">
                              <label htmlFor={`structured-character-role-input-${index}`}>角色</label>
                              <input
                                id={`structured-character-role-input-${index}`}
                                data-testid={`structured-character-role-input-${index}`}
                                value={character.role}
                                onChange={(event) => updateCharacterMetadata(index, "role", event.target.value)}
                                placeholder="角色待补充"
                              />
                            </div>
                          </div>
                          <div className="character-field">
                            <label htmlFor={`structured-character-description-input-${index}`}>描述</label>
                            <textarea
                              id={`structured-character-description-input-${index}`}
                              data-testid={`structured-character-description-input-${index}`}
                              value={character.description}
                              onChange={(event) => updateCharacterMetadata(index, "description", event.target.value)}
                              rows={2}
                              placeholder="描述待补充"
                            />
                          </div>
                          <button
                            className="small-ghost-button"
                            data-testid={`structured-character-delete-button-${index}`}
                            type="button"
                            onClick={() => removeCharacterEntry(index)}
                          >
                            删除人物
                          </button>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="structured-empty">暂无人物</p>
                  )}
                  <button
                    className="small-ghost-button add-character-button"
                    data-testid="structured-add-character-button"
                    type="button"
                    onClick={addCharacterEntry}
                  >
                    新增人物
                  </button>
                </div>

                <div className="structured-section">
                  <div className="structured-section-heading">
                    <strong>场景</strong>
                    <span>{structuredPreview.script.scenes.length}</span>
                  </div>
                  {structuredPreview.script.scenes.length > 0 ? (
                    <ol className="scene-preview-list">
                      {structuredPreview.script.scenes.map((scene, sceneIndex) => (
                        <li key={`${scene.id}-${scene.title}-${sceneIndex}`} data-testid="structured-scene">
                          <div className="scene-editor-toolbar">
                            <strong>场景 {sceneIndex + 1}</strong>
                            <button
                              className="small-ghost-button"
                              data-testid={`structured-scene-delete-button-${sceneIndex}`}
                              type="button"
                              onClick={() => removeSceneEntry(sceneIndex)}
                              disabled={structuredPreview.script.scenes.length <= 1}
                            >
                              删除场景
                            </button>
                          </div>
                          <div className="scene-field-grid">
                            <div className="scene-field">
                              <label htmlFor={`structured-scene-title-input-${sceneIndex}`}>场景标题</label>
                              <input
                                id={`structured-scene-title-input-${sceneIndex}`}
                                data-testid={`structured-scene-title-input-${sceneIndex}`}
                                value={scene.title}
                                onChange={(event) => updateSceneMetadata(sceneIndex, "title", event.target.value)}
                                placeholder={scene.id || `场景 ${sceneIndex + 1}`}
                              />
                            </div>
                            <div className="scene-field">
                              <label htmlFor={`structured-scene-location-input-${sceneIndex}`}>地点</label>
                              <input
                                id={`structured-scene-location-input-${sceneIndex}`}
                                data-testid={`structured-scene-location-input-${sceneIndex}`}
                                value={scene.location}
                                onChange={(event) => updateSceneMetadata(sceneIndex, "location", event.target.value)}
                                placeholder="未填写"
                              />
                            </div>
                            <div className="scene-field">
                              <label htmlFor={`structured-scene-time-input-${sceneIndex}`}>时间</label>
                              <input
                                id={`structured-scene-time-input-${sceneIndex}`}
                                data-testid={`structured-scene-time-input-${sceneIndex}`}
                                value={scene.time}
                                onChange={(event) => updateSceneMetadata(sceneIndex, "time", event.target.value)}
                                placeholder="未填写"
                              />
                            </div>
                          </div>
                          <div className="scene-character-editor">
                            <div className="scene-character-editor-heading">
                              <span>登场人物</span>
                              <button
                                className="small-ghost-button"
                                data-testid={`structured-scene-add-character-button-${sceneIndex}`}
                                type="button"
                                onClick={() => addSceneCharacterEntry(sceneIndex)}
                              >
                                新增登场人物
                              </button>
                            </div>
                            {scene.characters.length > 0 ? (
                              <ul className="scene-character-list">
                                {scene.characters.map((character, index) => (
                                  <li key={`${scene.id}-character-${index}`}>
                                    <input
                                      data-testid={`structured-scene-character-input-${sceneIndex}-${index}`}
                                      value={character}
                                      onChange={(event) => updateSceneCharacterEntry(sceneIndex, index, event.target.value)}
                                      placeholder="登场人物"
                                      aria-label={`场景 ${sceneIndex + 1} 登场人物 ${index + 1}`}
                                    />
                                    <button
                                      className="small-ghost-button"
                                      data-testid={`structured-scene-character-delete-button-${sceneIndex}-${index}`}
                                      type="button"
                                      onClick={() => removeSceneCharacterEntry(sceneIndex, index)}
                                    >
                                      删除
                                    </button>
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="structured-empty">暂无登场人物</p>
                            )}
                          </div>
                          <div className="beat-editor-list">
                            {scene.beats.length > 0 ? (
                              <ul className="beat-preview-list">
                                {scene.beats.map((beat, beatIndex) => (
                                  <li key={`${scene.id}-${beat.type}-${beatIndex}`} data-testid="structured-beat">
                                    <div className="beat-editor-toolbar">
                                      <label htmlFor={`structured-beat-type-select-${sceneIndex}-${beatIndex}`}>
                                        Beat {beatIndex + 1}
                                      </label>
                                      <select
                                        id={`structured-beat-type-select-${sceneIndex}-${beatIndex}`}
                                        data-testid={`structured-beat-type-select-${sceneIndex}-${beatIndex}`}
                                        value={beat.type}
                                        onChange={(event) => updateBeatMetadata(sceneIndex, beatIndex, "type", event.target.value)}
                                      >
                                        {BEAT_TYPE_OPTIONS.includes(beat.type as (typeof BEAT_TYPE_OPTIONS)[number]) ? null : (
                                          <option value={beat.type}>{displayValue(beat.type, "unknown")}</option>
                                        )}
                                        {BEAT_TYPE_OPTIONS.map((beatType) => (
                                          <option key={beatType} value={beatType}>
                                            {beatType}
                                          </option>
                                        ))}
                                      </select>
                                      <button
                                        className="small-ghost-button"
                                        data-testid={`structured-beat-delete-button-${sceneIndex}-${beatIndex}`}
                                        type="button"
                                        onClick={() => removeSceneBeat(sceneIndex, beatIndex)}
                                        disabled={scene.beats.length <= 1}
                                      >
                                        删除
                                      </button>
                                    </div>
                                    {beat.type === "dialogue" ? (
                                      <input
                                        className="beat-character-input"
                                        data-testid={`structured-beat-character-input-${sceneIndex}-${beatIndex}`}
                                        value={beat.character ?? ""}
                                        onChange={(event) => updateBeatMetadata(sceneIndex, beatIndex, "character", event.target.value)}
                                        placeholder="说话人"
                                        aria-label={`Beat ${beatIndex + 1} 说话人`}
                                      />
                                    ) : beat.character ? (
                                      <span className="beat-character-label">{beat.character}</span>
                                    ) : null}
                                    <textarea
                                      data-testid={`structured-beat-text-input-${sceneIndex}-${beatIndex}`}
                                      value={beat.text}
                                      onChange={(event) => updateBeatMetadata(sceneIndex, beatIndex, "text", event.target.value)}
                                      rows={3}
                                      placeholder="内容待补充"
                                    />
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="structured-empty">暂无 beats</p>
                            )}
                            <button
                              className="small-ghost-button add-beat-button"
                              data-testid={`structured-add-beat-button-${sceneIndex}`}
                              type="button"
                              onClick={() => addSceneBeat(sceneIndex)}
                            >
                              新增 beat
                            </button>
                          </div>
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="structured-empty">暂无场景</p>
                  )}
                  <button
                    className="small-ghost-button add-scene-button"
                    data-testid="structured-add-scene-button"
                    type="button"
                    onClick={addSceneEntry}
                  >
                    新增场景
                  </button>
                </div>
              </div>
            ) : (
              <p className={`structured-message ${structuredPreview.status}`}>{structuredPreview.message}</p>
            )}
        </section>

        <section className="editor-panel output-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Preview</p>
              <h2>剧本 YAML</h2>
            </div>
            <span className="schema-badge">schema 0.1.0</span>
          </div>
          <div className="panel-actions yaml-action-bar">
            <button
              className="ghost-button"
              data-testid="toggle-yaml-edit-button"
              type="button"
              onClick={() => setYamlMode(yamlMode === "preview" ? "edit" : "preview")}
            >
              {yamlMode === "preview" ? "在线编辑" : "完成编辑"}
            </button>
            <button
              className="ghost-button"
              data-testid="validate-yaml-button"
              type="button"
              onClick={validateYaml}
              disabled={isValidating}
            >
              {isValidating ? "校验中..." : "校验 YAML"}
            </button>
            <button
              className="ghost-button"
              data-testid="copy-yaml-button"
              type="button"
              onClick={copyYaml}
              disabled={isCopying}
            >
              {isCopying ? "复制中..." : copyButtonLabel}
            </button>
            <button className="ghost-button" type="button" onClick={resetYamlText}>
              重置
            </button>
            <button
              className="ghost-button"
              data-testid="download-yaml-button"
              type="button"
              onClick={downloadYaml}
            >
              下载 YAML
            </button>
          </div>
          {yamlMode === "preview" ? (
            <pre className="yaml-preview" data-testid="yaml-preview" aria-label="剧本 YAML 预览">
              {yamlText}
            </pre>
          ) : (
            <textarea
              className="yaml-editor"
              data-testid="yaml-editor"
              aria-label="剧本 YAML 编辑器"
              value={yamlText}
              onChange={(event) => updateYamlText(event.target.value, "YAML 已手动修改，结构化视图会重新解析。")}
              spellCheck={false}
            />
          )}
          <div className={`validation-panel ${validationStatus}`} aria-live="polite">
            <div className="validation-summary">
              <strong>校验结果</strong>
              <span>{validationMessage}</span>
            </div>
            {validationErrors.length > 0 ? (
              <ul className="validation-errors">
                {validationErrors.map((error, index) => (
                  <li key={`${error.path}-${error.message}-${index}`}>
                    <code>{error.path || "<root>"}</code>
                    <span>{error.message}</span>
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        </section>
      </main>
    </div>
  );
}

export default App;
