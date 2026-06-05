import { useState } from "react";

import "./App.css";

type HealthStatus = "idle" | "checking" | "ok" | "error";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const SAMPLE_TEXT = "第 1 章 初遇\n林澈推门而入，雨水顺着衣角滴落。\n\n第 2 章 暗线\n苏晚在旧信封里发现陌生地址。\n\n第 3 章 选择\n两人在清晨的站台前做出决定。";
const INITIAL_YAML = 'script:\n  schema_version: "0.1.0"\n  title: ""\n  scenes: []\n';

function countLikelyChapters(text: string) {
  const matches = text.match(/^\s*(?:#{1,6}\s+)?(?:第\s*(?:\d+|[零〇一二两三四五六七八九十百千万]+)\s*[章节回话]|chapter\s+\d+|\d+\s*[.．、]\s*\S)/gim);

  return matches?.length ?? 0;
}

function App() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("idle");
  const [healthMessage, setHealthMessage] = useState("未检测");
  const [sourceText, setSourceText] = useState(SAMPLE_TEXT);
  const [yamlText, setYamlText] = useState(INITIAL_YAML);

  const characterCount = sourceText.trim().length;
  const chapterCount = countLikelyChapters(sourceText);

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
            <strong>{chapterCount >= 3 ? "可解析" : "待补全"}</strong>
          </div>
        </aside>

        <section className="editor-panel input-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Source</p>
              <h2>小说文本</h2>
            </div>
            <div className="panel-actions">
              <button className="ghost-button" type="button" onClick={() => setSourceText(SAMPLE_TEXT)}>
                示例
              </button>
              <button className="ghost-button" type="button" onClick={() => setSourceText("")}>
                清空
              </button>
            </div>
          </div>
          <textarea
            aria-label="小说文本输入"
            value={sourceText}
            onChange={(event) => setSourceText(event.target.value)}
            placeholder={"第 1 章 ...\n\n第 2 章 ...\n\n第 3 章 ..."}
          />
        </section>

        <section className="editor-panel output-panel">
          <div className="panel-heading">
            <div>
              <p className="panel-kicker">Preview</p>
              <h2>剧本 YAML</h2>
            </div>
            <div className="panel-actions">
              <span className="schema-badge">schema 0.1.0</span>
              <button className="ghost-button" type="button" onClick={() => setYamlText(INITIAL_YAML)}>
                重置
              </button>
              <button className="ghost-button" type="button" onClick={downloadYaml}>
                下载 YAML
              </button>
            </div>
          </div>
          <textarea
            aria-label="剧本 YAML 编辑器"
            value={yamlText}
            onChange={(event) => setYamlText(event.target.value)}
            spellCheck={false}
          />
        </section>
      </main>
    </div>
  );
}

export default App;
