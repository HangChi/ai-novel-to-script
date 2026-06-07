import { spawn } from "node:child_process";
import { createRequire } from "node:module";
import { readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(scriptDir, "..");
const backendDir = path.join(repoRoot, "backend");
const frontendDir = path.join(repoRoot, "frontend");
const sampleNovelPath = path.join(repoRoot, "docs", "examples", "rain-letter-novel.txt");

const backendPort = Number(process.env.BACKEND_PORT ?? 8000);
const frontendPort = Number(process.env.FRONTEND_PORT ?? 5173);
const backendBaseUrl = `http://127.0.0.1:${backendPort}`;
const frontendBaseUrl = `http://127.0.0.1:${frontendPort}`;
const spawnedProcesses = [];
const screenplayYamlKeys = [
  "script",
  "schema_version",
  "title",
  "logline",
  "source",
  "type",
  "chapters_count",
  "chapter_titles",
  "characters",
  "id",
  "name",
  "role",
  "description",
  "scenes",
  "source_chapter",
  "location",
  "time",
  "beats",
  "text",
  "character",
];

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

function quoteScreenplayYamlKeys(yamlText) {
  const keyPattern = screenplayYamlKeys.join("|");
  const linePattern = new RegExp(`^(\\s*)(${keyPattern})(\\s*:)`, "gm");

  return yamlText.replace(linePattern, '$1"$2"$3');
}

async function ensureBackend() {
  if (await isReachable(`${backendBaseUrl}/api/health`)) {
    log("backend already running");
    return;
  }

  const python = process.env.PYTHON ?? "python";
  spawnProcess(
    python,
    ["main.py", "-p", String(backendPort), "--frontend-port", String(frontendPort)],
    backendDir,
    "backend",
    {
      ...process.env,
      AI_PROVIDER: "local",
    },
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

async function getJson(url) {
  const response = await fetch(url);
  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}: ${JSON.stringify(body)}`);
  }

  return body;
}

async function runApiSmoke() {
  const aiStatus = await getJson(`${backendBaseUrl}/api/ai/status`);
  const aiModels = await getJson(`${backendBaseUrl}/api/ai/models`);

  if (aiStatus.provider !== "local" || aiStatus.mode !== "local" || aiStatus.configured !== true) {
    throw new Error(`unexpected AI provider status: ${JSON.stringify(aiStatus)}`);
  }

  if (JSON.stringify(aiStatus).includes("API_KEY")) {
    throw new Error("local AI provider status should not expose API key fields");
  }

  const modelIds = new Set(aiModels.models?.map((model) => model.id));
  for (const expectedModelId of ["local", "deepseek-v4-pro", "kimi-2.6", "glm-4.7-flashx"]) {
    if (!modelIds.has(expectedModelId)) {
      throw new Error(`AI model list did not include ${expectedModelId}: ${JSON.stringify(aiModels)}`);
    }
  }

  if (JSON.stringify(aiModels).includes("secret") || JSON.stringify(aiModels).includes("API_KEY=")) {
    throw new Error("AI model list should not expose API key values");
  }

  const content = await readFile(sampleNovelPath, "utf-8");
  const generated = await postJson(`${backendBaseUrl}/api/scripts/generate`, {
    title: "rain-letter",
    content,
    output_format: "yaml",
    model_id: "local",
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

function requireProjectPlaywright() {
  const frontendRequire = createRequire(path.join(frontendDir, "package.json"));

  try {
    return frontendRequire("playwright");
  } catch (error) {
    throw new Error(
      [
        "Playwright is required for browser E2E and must be installed under frontend/.",
        "Run `cd frontend && npm install && npm run e2e:install`, then rerun `npm run smoke:e2e`.",
        error instanceof Error ? error.message : String(error),
      ].join("\n"),
    );
  }
}

async function runBrowserSmoke() {
  const playwright = requireProjectPlaywright();
  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({ acceptDownloads: true });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: frontendBaseUrl });
  const page = await context.newPage();

  try {
    const sampleNovelText = await readFile(sampleNovelPath, "utf-8");
    const normalizedSampleNovelText = sampleNovelText.replace(/\r\n/g, "\n");

    await page.goto(frontendBaseUrl, { waitUntil: "networkidle" });
    await page.waitForFunction(
      () => {
        const statusText = document.querySelector('[data-testid="ai-provider-status"]')?.textContent ?? "";
        const backendText = document.querySelector('[data-testid="backend-status"]')?.textContent ?? "";
        return statusText.includes("本地骨架")
          && statusText.includes("本地模式")
          && backendText.includes("已连接");
      },
      null,
      { timeout: 10_000 },
    );
    const schemaBadgeCount = await page.locator(".schema-badge").count();
    if (schemaBadgeCount !== 0) {
      throw new Error("schema badge should not be displayed in the YAML panel header");
    }
    const selectedModelId = await page.getByTestId("ai-model-select").inputValue();
    if (selectedModelId !== "local") {
      throw new Error(`default selected model was ${selectedModelId}`);
    }
    await page.getByTestId("source-file-input").setInputFiles(sampleNovelPath);
    await page.waitForFunction(
      (expectedText) => {
        const input = document.querySelector('[data-testid="source-text-input"]');
        return input instanceof HTMLTextAreaElement && input.value === expectedText;
      },
      normalizedSampleNovelText,
      { timeout: 10_000 },
    );

    const importedTitle = await page.getByTestId("script-title-input").inputValue();
    if (importedTitle !== "rain-letter-novel") {
      throw new Error(`imported file title was ${importedTitle}`);
    }

    await page.getByTestId("generate-yaml-button").click();
    await page.waitForFunction(
      () => document.querySelector('[data-testid="yaml-preview"]')?.textContent?.includes("type: narration"),
      null,
      { timeout: 10_000 },
    );

    const yamlText = await page.getByTestId("yaml-preview").textContent();
    if (!yamlText?.includes("script:") || !yamlText.includes("type: narration")) {
      throw new Error("generated YAML did not include a narration beat");
    }

    await page.waitForFunction(
      () => {
        const input = document.querySelector('[data-testid="structured-title-input"]');
        return input instanceof HTMLInputElement && input.value.includes("rain-letter-novel");
      },
      null,
      { timeout: 10_000 },
    );

    const sceneCount = await page.getByTestId("structured-scene").count();
    const beatCount = await page.getByTestId("structured-beat").count();

    if (sceneCount !== 3) {
      throw new Error(`structured preview rendered ${sceneCount} scenes`);
    }

    if (beatCount < 3) {
      throw new Error(`structured preview rendered ${beatCount} beats`);
    }

    const quotedKeyYamlText = quoteScreenplayYamlKeys(yamlText);
    await page.getByTestId("toggle-yaml-edit-button").click();
    await page.getByTestId("yaml-editor").fill(quotedKeyYamlText);
    await page.getByTestId("toggle-yaml-edit-button").click();
    await page.waitForFunction(
      () => {
        const input = document.querySelector('[data-testid="structured-title-input"]');
        const previewText = document.querySelector('[data-testid="yaml-preview"]')?.textContent ?? "";
        return input instanceof HTMLInputElement
          && input.value.includes("rain-letter-novel")
          && previewText.startsWith("script:")
          && !previewText.includes('"script":');
      },
      null,
      { timeout: 10_000 },
    );

    await page.getByTestId("structured-title-input").fill("Rain Letter Script");
    await page.getByTestId("structured-logline-input").fill("A letter pulls two strangers toward a dawn choice.");
    await page.getByTestId("structured-scene-title-input-0").fill("Opening at the Teahouse");
    await page.getByTestId("structured-scene-location-input-0").fill("Old teahouse entrance");
    await page.getByTestId("structured-scene-time-input-0").fill("Rainy evening");
    await page.getByTestId("structured-beat-type-select-0-0").selectOption("action");
    await page.getByTestId("structured-beat-text-input-0-0").fill("Lin steps through the rain-soaked teahouse door.");
    await page.getByTestId("structured-add-beat-button-0").click();
    await page.getByTestId("structured-beat-type-select-0-1").selectOption("transition");
    await page.getByTestId("structured-beat-text-input-0-1").fill("Cut to the hidden letter.");
    await page.waitForFunction(
      () => {
        const previewText = document.querySelector('[data-testid="yaml-preview"]')?.textContent ?? "";
        return previewText.includes('type: "transition"')
          && previewText.includes('text: "Cut to the hidden letter."');
      },
      null,
      { timeout: 10_000 },
    );
    await page.getByTestId("structured-beat-delete-button-0-1").click();
    await page.waitForFunction(
      () => {
        const previewText = document.querySelector('[data-testid="yaml-preview"]')?.textContent ?? "";
        return previewText.includes('title: "Rain Letter Script"')
          && previewText.includes('logline: "A letter pulls two strangers toward a dawn choice."')
          && previewText.includes('title: "Opening at the Teahouse"')
          && previewText.includes('location: "Old teahouse entrance"')
          && previewText.includes('time: "Rainy evening"')
          && previewText.includes('type: "action"')
          && previewText.includes('text: "Lin steps through the rain-soaked teahouse door."')
          && !previewText.includes("Cut to the hidden letter.");
      },
      null,
      { timeout: 10_000 },
    );
    await page.waitForFunction(
      () => document.querySelector('[data-testid="structured-sync-status"]')?.textContent?.includes("结构化修改已同步到 YAML"),
      null,
      { timeout: 10_000 },
    );

    await page.getByTestId("validate-yaml-button").click();
    await page.locator(".validation-panel.valid").waitFor({ timeout: 10_000 });

    await page.getByTestId("copy-yaml-button").click();
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    if (!clipboardText.includes("script:")
      || !clipboardText.includes('title: "Rain Letter Script"')
      || !clipboardText.includes('location: "Old teahouse entrance"')
      || !clipboardText.includes('type: "action"')
      || !clipboardText.includes('text: "Lin steps through the rain-soaked teahouse door."')
      || clipboardText.includes("Cut to the hidden letter.")) {
      throw new Error("copied YAML did not match the generated script");
    }

    const [download] = await Promise.all([
      page.waitForEvent("download"),
      page.getByTestId("download-yaml-button").click(),
    ]);
    const downloadedPath = await download.path();

    if (download.suggestedFilename() !== "script-draft.yaml") {
      throw new Error(`downloaded file was named ${download.suggestedFilename()}`);
    }

    if (!downloadedPath) {
      throw new Error("downloaded YAML path was unavailable");
    }

    const downloadedYaml = await readFile(downloadedPath, "utf-8");
    if (!downloadedYaml.includes("script:")
      || !downloadedYaml.includes('logline: "A letter pulls two strangers toward a dawn choice."')
      || !downloadedYaml.includes('time: "Rainy evening"')
      || !downloadedYaml.includes('type: "action"')
      || downloadedYaml.includes("Cut to the hidden letter.")) {
      throw new Error("downloaded YAML did not match the generated script");
    }

    log("browser import/generate/validate/copy/download smoke passed");
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
  await runApiSmoke();
  await runBrowserSmoke();
  log("demo smoke completed");
} finally {
  cleanup();
}
