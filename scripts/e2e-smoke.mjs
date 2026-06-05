import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { existsSync } from "node:fs";
import { readFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const backendDir = path.join(repoRoot, "backend");
const frontendDir = path.join(repoRoot, "frontend");

const backendPort = Number(process.env.BACKEND_PORT ?? 8000);
const frontendPort = Number(process.env.FRONTEND_PORT ?? 5173);
const backendBaseUrl = `http://127.0.0.1:${backendPort}`;
const frontendBaseUrl = `http://127.0.0.1:${frontendPort}`;
const spawnedProcesses = [];

function log(message) {
  console.log(`[smoke] ${message}`);
}

async function isReachable(url) {
  try {
    const response = await fetch(url);
    return response.ok;
  } catch {
    return false;
  }
}

async function waitFor(url, label) {
  const deadline = Date.now() + 30_000;

  while (Date.now() < deadline) {
    if (await isReachable(url)) {
      return;
    }

    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  throw new Error(`${label} did not become reachable at ${url}`);
}

function spawnProcess(command, args, cwd, label, env = process.env) {
  const child = spawn(command, args, {
    cwd,
    env,
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true,
  });

  child.stdout.on("data", (chunk) => {
    process.stdout.write(`[${label}] ${chunk}`);
  });
  child.stderr.on("data", (chunk) => {
    process.stderr.write(`[${label}] ${chunk}`);
  });
  spawnedProcesses.push(child);
  return child;
}

async function ensureBackend() {
  if (await isReachable(`${backendBaseUrl}/api/health`)) {
    log("backend already running");
    return;
  }

  const python = process.env.PYTHON ?? "python";
  spawnProcess(
    python,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", String(backendPort)],
    backendDir,
    "backend",
  );
  await waitFor(`${backendBaseUrl}/api/health`, "backend");
}

async function ensureFrontend() {
  if (await isReachable(frontendBaseUrl)) {
    log("frontend already running");
    return;
  }

  const viteBin = path.join(frontendDir, "node_modules", "vite", "bin", "vite.js");
  spawnProcess(
    process.execPath,
    [viteBin, "--host", "127.0.0.1", "--port", String(frontendPort)],
    frontendDir,
    "frontend",
    {
      ...process.env,
      VITE_API_BASE_URL: backendBaseUrl,
    },
  );
  await waitFor(frontendBaseUrl, "frontend");
}

async function postJson(url, payload) {
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}: ${JSON.stringify(body)}`);
  }

  return body;
}

async function runApiSmoke() {
  const content = await readFile(path.join(repoRoot, "docs", "examples", "rain-letter-novel.txt"), "utf-8");
  const generated = await postJson(`${backendBaseUrl}/api/scripts/generate`, {
    title: "雨夜来信",
    content,
    output_format: "yaml",
  });

  if (!generated.yaml?.includes("script:")) {
    throw new Error("generated response did not contain YAML");
  }

  const validResult = await postJson(`${backendBaseUrl}/api/scripts/validate`, {
    schema_version: "0.1.0",
    yaml: generated.yaml,
  });

  if (!validResult.valid) {
    throw new Error(`generated YAML did not validate: ${JSON.stringify(validResult.errors)}`);
  }

  const invalidResult = await postJson(`${backendBaseUrl}/api/scripts/validate`, {
    schema_version: "0.1.0",
    yaml: generated.yaml.replace("type: narration", "type: invalid_beat"),
  });

  if (invalidResult.valid) {
    throw new Error("invalid beat type unexpectedly passed validation");
  }

  log("API generate/validate smoke passed");
}

async function runFrontendHttpSmoke() {
  const html = await fetch(frontendBaseUrl).then((response) => response.text());

  if (!html.includes('id="root"')) {
    throw new Error("frontend HTML did not include the React root element");
  }

  const appSource = await fetch(`${frontendBaseUrl}/src/App.tsx`).then((response) => response.text());
  for (const label of ["生成 YAML", "校验 YAML", "复制 YAML", "导入文件"]) {
    if (!appSource.includes(label)) {
      throw new Error(`frontend source did not include ${label}`);
    }
  }

  log("frontend HTTP smoke passed");
}

function requirePlaywright() {
  const localRequire = createRequire(import.meta.url);

  try {
    return localRequire("playwright");
  } catch {
    // Continue to optional fallback paths below.
  }

  const candidates = [
    process.env.PLAYWRIGHT_NODE_MODULES,
    path.join(os.homedir(), ".cache", "codex-runtimes", "codex-primary-runtime", "dependencies", "node", "node_modules"),
  ].filter(Boolean);

  for (const candidate of candidates) {
    if (!existsSync(path.join(candidate, "playwright"))) {
      continue;
    }

    try {
      return createRequire(pathToFileURL(path.join(candidate, "..", "playwright-loader.js")))("playwright");
    } catch {
      // Try the next candidate.
    }
  }

  return null;
}

async function runBrowserSmoke() {
  const playwright = requirePlaywright();

  if (!playwright) {
    log("playwright not found; skipped browser click smoke after HTTP smoke");
    return;
  }

  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage();

  try {
    await page.goto(frontendBaseUrl, { waitUntil: "networkidle" });
    await page.getByRole("button", { name: "生成 YAML" }).click();
    await page.getByText("已生成 schema 0.1.0").waitFor({ timeout: 10_000 });

    await page.getByRole("button", { name: "校验 YAML" }).click();
    await page.getByText("YAML 结构有效").waitFor({ timeout: 10_000 });

    await page.getByRole("button", { name: "在线编辑" }).click();
    const editor = page.getByLabel("剧本 YAML 编辑器");
    const yamlText = await editor.inputValue();

    if (!yamlText.includes("type: narration")) {
      throw new Error("generated YAML did not include a narration beat");
    }

    await editor.fill(yamlText.replace("type: narration", "type: invalid_beat"));
    await page.getByRole("button", { name: "校验 YAML" }).click();
    await page.getByText("发现 1 个结构问题").waitFor({ timeout: 10_000 });
    await page.getByText("script.scenes[0].beats[0].type").waitFor({ timeout: 10_000 });

    log("browser click smoke passed");
  } finally {
    await browser.close();
  }
}

function cleanup() {
  for (const child of spawnedProcesses.reverse()) {
    if (!child.killed) {
      child.kill();
    }
  }
}

try {
  await ensureBackend();
  await ensureFrontend();
  await runFrontendHttpSmoke();
  await runApiSmoke();
  await runBrowserSmoke();
  log("demo smoke completed");
} finally {
  cleanup();
}
