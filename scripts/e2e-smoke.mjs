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
  const content = await readFile(sampleNovelPath, "utf-8");
  const generated = await postJson(`${backendBaseUrl}/api/scripts/generate`, {
    title: "rain-letter",
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

    await page.getByTestId("validate-yaml-button").click();
    await page.locator(".validation-panel.valid").waitFor({ timeout: 10_000 });

    await page.getByTestId("copy-yaml-button").click();
    const clipboardText = await page.evaluate(() => navigator.clipboard.readText());
    if (!clipboardText.includes("script:") || !clipboardText.includes("type: narration")) {
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
    if (!downloadedYaml.includes("script:") || !downloadedYaml.includes("type: narration")) {
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
