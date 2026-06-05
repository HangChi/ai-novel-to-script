import { type ChangeEvent, useState } from "react";

import "./App.css";

type HealthStatus = "idle" | "checking" | "ok" | "error";
type GenerationStatus = "idle" | "generating" | "success" | "error";
type ImportStatus = "idle" | "importing" | "success" | "error";
type ValidationStatus = "idle" | "validating" | "valid" | "invalid" | "error";
type CopyStatus = "idle" | "copying" | "copied" | "error";
type YamlMode = "preview" | "edit";

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

type ApiErrorResponse = {
  detail?: {
    code?: string;
    message?: string;
  };
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

function App() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("idle");
  const [healthMessage, setHealthMessage] = useState("未检测");
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

  const characterCount = sourceText.trim().length;
  const chapterCount = countLikelyChapters(sourceText);
  const isGenerating = generationStatus === "generating";
  const isValidating = validationStatus === "validating";
  const isCopying = copyStatus === "copying";
  const inputMessage = importStatus === "idle" ? generationMessage : importMessage;
  const inputMessageStatus = importStatus === "idle" ? generationStatus : importStatus;
  const copyButtonLabel = copyStatus === "copied" ? "已复制" : copyStatus === "error" ? "复制失败" : "复制 YAML";

  function resetValidationState(message = "待校验") {
    setValidationStatus("idle");
    setValidationMessage(message);
    setValidationErrors([]);
  }

  function updateYamlText(nextYamlText: string) {
    setYamlText(nextYamlText);
    resetValidationState("YAML 已修改，待校验");
    setCopyStatus("idle");
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
    } catch {
      setHealthStatus("error");
      setHealthMessage("未连接");
    }
  }

  async function generateScript() {
    setGenerationStatus("generating");
    setGenerationMessage("生成中");
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

      updateYamlText(result.yaml);
      setYamlMode("preview");
      setGenerationStatus("success");
      setGenerationMessage(`已生成 schema ${result.schema_version}`);
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
    updateYamlText(INITIAL_YAML);
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

      <main className="workspace-shell">
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
              value={scriptTitle}
              onChange={(event) => setScriptTitle(event.target.value)}
              placeholder="未命名剧本"
            />
          </label>
          <textarea
            aria-label="小说文本输入"
            value={sourceText}
            onChange={(event) => setSourceText(event.target.value)}
            placeholder={"第 1 章 ...\n\n第 2 章 ...\n\n第 3 章 ..."}
          />
          <div className="panel-footer">
            <span className={`generation-message ${inputMessageStatus}`}>{inputMessage}</span>
            <button className="generate-button" type="button" onClick={generateScript} disabled={isGenerating}>
              {isGenerating ? "生成中..." : "生成 YAML"}
            </button>
          </div>
        </section>

        <section className="editor-panel output-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Preview</p>
              <h2>剧本 YAML</h2>
            </div>
            <div className="panel-actions">
              <span className="schema-badge">schema 0.1.0</span>
              <button className="ghost-button" type="button" onClick={() => setYamlMode(yamlMode === "preview" ? "edit" : "preview")}>
                {yamlMode === "preview" ? "在线编辑" : "完成编辑"}
              </button>
              <button className="ghost-button" type="button" onClick={validateYaml} disabled={isValidating}>
                {isValidating ? "校验中..." : "校验 YAML"}
              </button>
              <button className="ghost-button" type="button" onClick={copyYaml} disabled={isCopying}>
                {isCopying ? "复制中..." : copyButtonLabel}
              </button>
              <button className="ghost-button" type="button" onClick={resetYamlText}>
                重置
              </button>
              <button className="ghost-button" type="button" onClick={downloadYaml}>
                下载 YAML
              </button>
            </div>
          </div>
          {yamlMode === "preview" ? (
            <pre className="yaml-preview" aria-label="剧本 YAML 预览">
              {yamlText}
            </pre>
          ) : (
            <textarea
              className="yaml-editor"
              aria-label="剧本 YAML 编辑器"
              value={yamlText}
              onChange={(event) => updateYamlText(event.target.value)}
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
