import { useState } from "react";

import "./App.css";

type HealthStatus = "idle" | "checking" | "ok" | "error";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function App() {
  const [healthStatus, setHealthStatus] = useState<HealthStatus>("idle");
  const [healthMessage, setHealthMessage] = useState("未检测");

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

  return (
    <div className="app-shell">
      <header className="topbar">
        <div>
          <p className="eyebrow">AI Novel to Script</p>
          <h1>小说转剧本工作台</h1>
        </div>
        <button
          className="status-button"
          type="button"
          onClick={checkBackend}
          disabled={healthStatus === "checking"}
        >
          {healthStatus === "checking" ? "检测中..." : "检测后端"}
        </button>
      </header>

      <main className="workspace-grid">
        <section className="editor-panel">
          <div className="panel-heading">
            <h2>小说文本</h2>
            <span>至少 3 章</span>
          </div>
          <textarea
            aria-label="小说文本输入"
            placeholder={"第 1 章 ...\n\n第 2 章 ...\n\n第 3 章 ..."}
          />
        </section>

        <section className="editor-panel output-panel">
          <div className="panel-heading">
            <h2>剧本 YAML</h2>
            <span className={`status-pill ${healthStatus}`}>{healthMessage}</span>
          </div>
          <pre>{'script:\n  schema_version: "0.1.0"\n  title: ""\n  scenes: []'}</pre>
        </section>
      </main>
    </div>
  );
}

export default App;
