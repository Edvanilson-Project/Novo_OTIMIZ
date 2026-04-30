#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { execFileSync, spawn } = require("child_process");
const WebSocket = require("../backend/node_modules/ws");
const jwt = require("../backend/node_modules/jsonwebtoken");

const ROOT = path.resolve(__dirname, "..");
const OUT_DIR = path.join(ROOT, "artifacts", "operational_quality_e2e");
const BASE_URL = "http://127.0.0.1:3001/api/v1";
const FRONTEND_URL = "http://127.0.0.1:3000/operations/planner";
const CHROME_DEBUG_URL = "http://127.0.0.1:9222";
const JWT_SECRET = "your_jwt_secret_here_min_32_chars";
const COMPANY_ID = 16;
const SKIP_UI = process.env.SKIP_UI === "1";
const USER = {
  id: 15,
  email: "admin@otimiz.com",
  name: "Admin",
  role: "super_admin",
  companyId: COMPANY_ID,
};
const RANDOM_SEED = 42;
const MODES = [
  { mode: "strict", uiLabel: "Sem excecoes criticas", expectedChip: "Plano sem excecoes criticas" },
  { mode: "balanced", uiLabel: "Equilibrado", expectedChip: "Plano mais equilibrado" },
  { mode: "optimized", uiLabel: "Mais barato", expectedChip: "Plano mais barato" },
];

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ensureDir(dir) {
  fs.mkdirSync(dir, { recursive: true });
}

function nowIso() {
  return new Date().toISOString();
}

function token() {
  return jwt.sign(
    {
      sub: USER.id,
      email: USER.email,
      companyId: USER.companyId,
      role: USER.role,
    },
    JWT_SECRET,
    { expiresIn: "1d" },
  );
}

async function httpJson(url, options = {}) {
  const startedAt = Date.now();
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token()}`,
    ...(options.headers || {}),
  };
  const response = await fetch(url, { ...options, headers });
  const text = await response.text();
  let body;
  try {
    body = text ? JSON.parse(text) : null;
  } catch {
    body = text;
  }
  return {
    ok: response.ok,
    status: response.status,
    body,
    elapsedMs: Date.now() - startedAt,
  };
}

function shell(command, args, opts = {}) {
  return execFileSync(command, args, {
    cwd: ROOT,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
    ...opts,
  }).trim();
}

function psql(query) {
  return shell("docker", [
    "exec",
    "otimiz-v2-postgres",
    "psql",
    "-U",
    "otimiz_admin",
    "-d",
    "otimiz_db",
    "-t",
    "-A",
    "-F",
    "\t",
    "-c",
    query,
  ]);
}

function redisCli(args) {
  return shell("docker", ["exec", "otimiz-v2-redis", "redis-cli", "-p", "6379", ...args]);
}

function redisMemoryUsage(key) {
  try {
    const raw = redisCli(["memory", "usage", key]);
    const value = Number(raw);
    return Number.isFinite(value) ? value : null;
  } catch {
    return null;
  }
}

function getRedisKeys() {
  const raw = redisCli(["--raw", "keys", "celery-task-meta-*"]);
  return raw ? raw.split("\n").map((line) => line.trim()).filter(Boolean) : [];
}

function getWorkerMemorySnapshot() {
  const raw = shell("bash", [
    "-lc",
    "ps -eo pid,rss,%mem,cmd | rg 'celery.*worker|uvicorn main:app|next dev' || true",
  ]);
  const rows = raw
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const parts = line.split(/\s+/, 4);
      return {
        pid: Number(parts[0]),
        rssKb: Number(parts[1]),
        memPct: Number(parts[2]),
        cmd: parts[3] || "",
      };
    });
  return rows;
}

function getScheduleDbSummary(scheduleId) {
  const sql = `
    select
      id,
      status,
      round(extract(epoch from ("updatedAt" - "createdAt"))::numeric, 3)::text as elapsed_s,
      coalesce(metadata->>'chosen_scenario', '') as chosen_scenario,
      coalesce(jsonb_array_length(coalesce(metadata->'rejected_scenarios', '[]'::jsonb)), 0)::text as rejected_count,
      coalesce(jsonb_array_length(coalesce(metadata->'justification', '[]'::jsonb)), 0)::text as justification_count,
      coalesce(jsonb_array_length(coalesce(metadata->'trade_offs', '[]'::jsonb)), 0)::text as trade_offs_count
    from schedules
    where id = ${Number(scheduleId)};
  `;
  const raw = psql(sql).trim();
  if (!raw) return null;
  const [id, status, elapsedS, chosenScenario, rejectedCount, justificationCount, tradeOffsCount] = raw.split("\t");
  return {
    id: Number(id),
    status,
    elapsedS: Number(elapsedS),
    chosenScenario: chosenScenario || null,
    rejectedCount: Number(rejectedCount),
    justificationCount: Number(justificationCount),
    tradeOffsCount: Number(tradeOffsCount),
  };
}

function getParametersSchemaStatus() {
  const count = Number(
    psql(`
      select count(*)
      from information_schema.columns
      where table_name = 'company_parameters'
        and column_name = 'operational_quality_mode';
    `).trim(),
  );
  return { hasOperationalQualityModeColumn: count > 0 };
}

function setRandomSeed(seed) {
  psql(`update company_parameters set random_seed = ${Number(seed)} where "companyId" = ${COMPANY_ID};`);
}

async function getLatestSchedule() {
  const res = await httpJson(`${BASE_URL}/operations/latest-schedule`, { method: "GET" });
  if (!res.ok) {
    throw new Error(`latest-schedule failed with ${res.status}: ${JSON.stringify(res.body)}`);
  }
  return res;
}

async function waitForCompletedSchedule(targetScheduleId, timeoutMs = 240000) {
  const startedAt = Date.now();
  let latestSeen = null;
  while (Date.now() - startedAt < timeoutMs) {
    const latest = await getLatestSchedule();
    latestSeen = latest.body;
    if (latest.body.id === targetScheduleId && latest.body.status !== "processing") {
      return {
        schedule: latest.body,
        latestScheduleGetMs: latest.elapsedMs,
        totalWaitMs: Date.now() - startedAt,
      };
    }
    await sleep(2500);
  }
  return {
    schedule: latestSeen,
    latestScheduleGetMs: null,
    totalWaitMs: Date.now() - startedAt,
    timedOut: true,
  };
}

async function startChromium() {
  let proc = null;
  try {
    const version = await fetch(`${CHROME_DEBUG_URL}/json/version`);
    if (version.ok) {
      return { proc: null };
    }
  } catch {
    // ignored
  }

  proc = spawn(
    "/usr/bin/chromium",
    [
      "--headless=new",
      "--disable-gpu",
      "--no-sandbox",
      "--remote-debugging-port=9222",
      "--user-data-dir=/tmp/otimiz-chromium-e2e",
      "about:blank",
    ],
    { stdio: "ignore" },
  );

  for (let i = 0; i < 40; i += 1) {
    try {
      const version = await fetch(`${CHROME_DEBUG_URL}/json/version`);
      if (version.ok) {
        return { proc };
      }
    } catch {
      // ignored
    }
    await sleep(500);
  }

  throw new Error("Chromium DevTools did not start on port 9222.");
}

class CdpPage {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.seq = 0;
    this.pending = new Map();
    this.loadResolvers = [];
  }

  async connect() {
    await new Promise((resolve, reject) => {
      this.ws.once("open", resolve);
      this.ws.once("error", reject);
    });
    this.ws.on("message", (buf) => {
      const msg = JSON.parse(String(buf));
      if (msg.id && this.pending.has(msg.id)) {
        const { resolve, reject } = this.pending.get(msg.id);
        this.pending.delete(msg.id);
        if (msg.error) reject(new Error(msg.error.message || JSON.stringify(msg.error)));
        else resolve(msg.result);
        return;
      }
      if (msg.method === "Page.loadEventFired") {
        const resolvers = [...this.loadResolvers];
        this.loadResolvers = [];
        resolvers.forEach((resolve) => resolve());
      }
    });
    await this.send("Page.enable");
    await this.send("Runtime.enable");
  }

  send(method, params = {}) {
    const id = ++this.seq;
    const payload = { id, method, params };
    this.ws.send(JSON.stringify(payload));
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
    });
  }

  async evaluate(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    return result.result ? result.result.value : null;
  }

  waitForLoad(timeoutMs = 30000) {
    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => reject(new Error("Page load timeout")), timeoutMs);
      this.loadResolvers.push(() => {
        clearTimeout(timer);
        resolve();
      });
    });
  }

  async close() {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.close();
    }
  }
}

async function newPage() {
  const res = await fetch(`${CHROME_DEBUG_URL}/json/new?about:blank`, { method: "PUT" });
  if (!res.ok) throw new Error(`Failed to create Chromium page: ${res.status}`);
  const data = await res.json();
  const page = new CdpPage(data.webSocketDebuggerUrl);
  await page.connect();
  return page;
}

async function waitFor(page, expression, timeoutMs = 30000, intervalMs = 500) {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    const value = await page.evaluate(expression);
    if (value) return value;
    await sleep(intervalMs);
  }
  throw new Error(`Timeout waiting for: ${expression}`);
}

async function openPlannerWithSession(page) {
  const preload = `
    (() => {
      try {
        localStorage.setItem('otimiz_token', ${JSON.stringify(token())});
        localStorage.setItem('otimiz_user', ${JSON.stringify(JSON.stringify(USER))});
      } catch (err) {}
    })();
  `;
  await page.send("Page.addScriptToEvaluateOnNewDocument", { source: preload });
  await page.send("Page.navigate", { url: FRONTEND_URL });
  await sleep(2500);
  await waitFor(
    page,
    `(() => document.body && /Executar Otimiza[cç][aã]o/.test(document.body.innerText))()`,
    60000,
  );
}

async function selectMode(page, uiLabel) {
  await page.evaluate(`
    (() => {
      const combos = [...document.querySelectorAll('[role="combobox"]')];
      const target = combos[1];
      if (!target) return false;
      target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
      target.click();
      return true;
    })()
  `);
  await waitFor(page, `(() => !![...document.querySelectorAll('[role="option"]')].find((el) => (el.innerText || '').trim() === ${JSON.stringify(uiLabel)}))()`, 15000);
  const picked = await page.evaluate(`
    (() => {
      const option = [...document.querySelectorAll('[role="option"]')]
        .find((el) => (el.innerText || '').trim() === ${JSON.stringify(uiLabel)});
      if (!option) return false;
      option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true, view: window }));
      option.click();
      return true;
    })()
  `);
  if (!picked) throw new Error(`Could not choose UI option ${uiLabel}`);
  await waitFor(page, `(() => {
    const combos = [...document.querySelectorAll('[role="combobox"]')];
    return (combos[1]?.innerText || '').includes(${JSON.stringify(uiLabel)});
  })()`, 15000);
}

async function clickOptimize(page) {
  const clicked = await page.evaluate(`
    (() => {
      const button = [...document.querySelectorAll('button')]
        .find((el) => /Executar Otimiza[cç][aã]o/.test(el.innerText || ''));
      if (!button) return false;
      button.click();
      return true;
    })()
  `);
  if (!clicked) throw new Error("Optimize button not found.");
}

async function triggerOptimizeByApi(mode) {
  return httpJson(`${BASE_URL}/operations/optimize`, {
    method: "POST",
    body: JSON.stringify({
      algorithm: "hybrid_pipeline",
      operational_quality_mode: mode,
    }),
  });
}

async function reloadPlanner(page) {
  await page.send("Page.navigate", { url: FRONTEND_URL });
  await sleep(2500);
  await waitFor(
    page,
    `(() => document.body && /Executar Otimiza[cç][aã]o/.test(document.body.innerText))()`,
    60000,
  );
}

async function getUiSnapshot(page) {
  return page.evaluate(`
    (() => {
      const combos = [...document.querySelectorAll('[role="combobox"]')];
      const chips = [...document.querySelectorAll('.MuiChip-label')]
        .map((el) => (el.textContent || '').trim())
        .filter(Boolean);
      const chosenLine = [...document.querySelectorAll('*')]
        .map((el) => (el.innerText || '').trim())
        .find((text) => text.startsWith('Cenario escolhido:')) || null;
      return {
        modeText: (combos[1]?.innerText || '').trim() || null,
        chosenLine,
        chips,
        bodyExcerpt: (document.body?.innerText || '').slice(0, 4000),
      };
    })()
  `);
}

function parseDecision(schedule) {
  const summary = schedule?.resultSummary || {};
  return {
    chosenScenarioRoot: summary.chosen_scenario ?? null,
    rejectedScenariosRoot: summary.rejected_scenarios ?? [],
    justification: summary.justification ?? [],
    tradeOffs: summary.trade_offs ?? [],
    decision: summary.operational_quality_decision ?? null,
  };
}

function validateScenario(modeConfig, schedule, uiSnapshotBefore, uiSnapshot, dbSummary, payloadKey, latestScheduleGetMs, totalWaitMs, beforeId, afterId) {
  const decision = parseDecision(schedule);
  const selected = decision.decision || {};
  const labels =
    (selected.available_scenarios || [])
      .find((item) => item.scenario_id === selected.chosen_scenario)
      ?.labels || [];

  const validations = {
    executionCompleted: schedule?.status === "completed",
    noInfinitePolling: totalWaitMs < 240000,
    statusCorrect: schedule?.status === "completed",
    chosenScenarioPersisted: Boolean(dbSummary?.chosenScenario),
    rejectedScenariosPersisted: (dbSummary?.rejectedCount || 0) > 0,
    justificationPresent: (dbSummary?.justificationCount || 0) > 0 && decision.justification.length > 0,
    tradeOffsPresent: (dbSummary?.tradeOffsCount || 0) > 0 && decision.tradeOffs.length > 0,
    apiDecisionPresent: Boolean(selected && selected.chosen_scenario),
    apiConsistentWithRoot: decision.chosenScenarioRoot === selected.chosen_scenario,
    uiModeSelected: (uiSnapshotBefore?.modeText || "").includes(modeConfig.uiLabel),
    uiChosenScenarioShown: Boolean(uiSnapshot?.chosenLine && uiSnapshot.chosenLine.includes(selected.chosen_title || selected.chosen_scenario || "")),
    uiExpectedLabelShown: labels.includes(modeConfig.expectedChip) || ((uiSnapshot?.chips || []).includes(modeConfig.expectedChip)),
    redisPayloadCaptured: Boolean(payloadKey),
    latestScheduleChanged: afterId > beforeId,
    latestScheduleResponseTimeOk: typeof latestScheduleGetMs === "number" && latestScheduleGetMs < 5000,
  };

  return { validations, labels };
}

function buildMarkdown(report) {
  const lines = [];
  lines.push("# Operational Quality E2E");
  lines.push("");
  lines.push(`Gerado em: ${report.generatedAt}`);
  lines.push(`Seed fixa usada: ${report.randomSeed}`);
  lines.push("");
  lines.push(`Veredito: **${report.verdict}**`);
  lines.push("");
  lines.push("## Ambiente");
  lines.push("");
  lines.push(`- Coluna \`operational_quality_mode\` em \`company_parameters\`: ${report.schema.hasOperationalQualityModeColumn ? "presente" : "ausente"}`);
  lines.push("");
  for (const scenario of report.scenarios) {
    lines.push(`## ${scenario.mode}`);
    lines.push("");
    lines.push("| Item | Run 1 | Run 2 |");
    lines.push("| --- | --- | --- |");
    const v1 = scenario.runs[0].validations;
    const v2 = scenario.runs[1].validations;
    const rows = [
      ["execucao completa", v1.executionCompleted, v2.executionCompleted],
      ["status correto", v1.statusCorrect, v2.statusCorrect],
      ["sem polling infinito", v1.noInfinitePolling, v2.noInfinitePolling],
      ["chosen_scenario persistido", v1.chosenScenarioPersisted, v2.chosenScenarioPersisted],
      ["rejected_scenarios persistido", v1.rejectedScenariosPersisted, v2.rejectedScenariosPersisted],
      ["justification presente", v1.justificationPresent, v2.justificationPresent],
      ["trade_offs presente", v1.tradeOffsPresent, v2.tradeOffsPresent],
      ["API operational_quality_decision", v1.apiDecisionPresent, v2.apiDecisionPresent],
      ["API consistente", v1.apiConsistentWithRoot, v2.apiConsistentWithRoot],
      ["UI modo selecionado", v1.uiModeSelected, v2.uiModeSelected],
      ["UI cenario exibido", v1.uiChosenScenarioShown, v2.uiChosenScenarioShown],
      ["UI label esperada", v1.uiExpectedLabelShown, v2.uiExpectedLabelShown],
      ["payload Redis capturado", v1.redisPayloadCaptured, v2.redisPayloadCaptured],
      ["latest-schedule mudou", v1.latestScheduleChanged, v2.latestScheduleChanged],
      ["latest-schedule < 5s", v1.latestScheduleResponseTimeOk, v2.latestScheduleResponseTimeOk],
    ];
    for (const [label, a, b] of rows) {
      lines.push(`| ${label} | ${a ? "passou" : "falhou"} | ${b ? "passou" : "falhou"} |`);
    }
    lines.push("");
    lines.push(`Consistencia com mesma seed: **${scenario.consistent ? "idêntica" : "divergente"}**`);
    lines.push("");
    lines.push("Principais logs:");
    lines.push("");
    for (const run of scenario.runs) {
      lines.push(`- run ${run.run}: schedule ${run.scheduleId}, chosen=${run.chosenScenario}, elapsed=${run.elapsedS}s, latestScheduleGet=${run.latestScheduleGetMs}ms, redisPayload=${run.redisPayloadBytes ?? "N/D"}B, workerMaxRss=${run.workerMaxRssKb ?? "N/D"}KB`);
    }
    lines.push("");
  }
  return lines.join("\n");
}

async function run() {
  ensureDir(OUT_DIR);
  const report = {
    generatedAt: nowIso(),
    randomSeed: RANDOM_SEED,
    schema: getParametersSchemaStatus(),
    skipUi: SKIP_UI,
    scenarios: [],
    verdict: "nao pronto",
  };

  setRandomSeed(RANDOM_SEED);
  const { proc: chromeProc } = SKIP_UI ? { proc: null } : await startChromium();

  try {
    for (const modeConfig of MODES) {
      const scenarioResult = {
        mode: modeConfig.mode,
        expectedChip: modeConfig.expectedChip,
        runs: [],
        consistent: false,
      };

      for (let runIndex = 0; runIndex < 2; runIndex += 1) {
        console.log(`[${nowIso()}] mode=${modeConfig.mode} run=${runIndex + 1} starting`);
        setRandomSeed(RANDOM_SEED);
        const beforeLatest = await getLatestSchedule();
        const beforeKeys = new Set(getRedisKeys());
        const workerBefore = getWorkerMemorySnapshot();
        const submit = await triggerOptimizeByApi(modeConfig.mode);
        if (!submit.ok || !submit.body?.scheduleId) {
          throw new Error(`API optimize failed: ${JSON.stringify(submit)}`);
        }

        console.log(`[${nowIso()}] mode=${modeConfig.mode} run=${runIndex + 1} schedule=${submit.body.scheduleId} queued`);
        const completed = await waitForCompletedSchedule(submit.body.scheduleId);
        const redisKey = submit.body?.taskId ? `celery-task-meta-${submit.body.taskId}` : null;
        const redisPayloadBytes = redisKey ? redisMemoryUsage(redisKey) : null;
        const dbSummary = completed.schedule ? getScheduleDbSummary(completed.schedule.id) : null;
        const workerAfter = getWorkerMemorySnapshot();
        const workerMaxRssKb = [...workerBefore, ...workerAfter].reduce((max, item) => Math.max(max, item.rssKb || 0), 0);
        let uiSnapshotBefore = null;
        let uiSnapshot = null;

        if (!SKIP_UI) {
          try {
            const page = await newPage();
            try {
              await openPlannerWithSession(page);
              await selectMode(page, modeConfig.uiLabel);
              uiSnapshotBefore = await getUiSnapshot(page);
              await reloadPlanner(page);
              uiSnapshot = await getUiSnapshot(page);
            } finally {
              await page.close();
            }
          } catch (uiError) {
            uiSnapshot = { uiError: String(uiError) };
          }
        }

        const { validations, labels } = validateScenario(
          modeConfig,
          completed.schedule,
          uiSnapshotBefore,
          uiSnapshot,
          dbSummary,
          redisKey,
          completed.latestScheduleGetMs,
          completed.totalWaitMs,
          beforeLatest.body.id,
          submit.body.scheduleId,
        );
        const decision = parseDecision(completed.schedule);

        const runResult = {
          run: runIndex + 1,
          mode: modeConfig.mode,
          scheduleId: completed.schedule?.id || null,
          status: completed.schedule?.status || null,
          chosenScenario: decision.decision?.chosen_scenario || decision.chosenScenarioRoot || null,
          chosenTitle: decision.decision?.chosen_title || null,
          labels,
          latestScheduleGetMs: completed.latestScheduleGetMs,
          totalWaitMs: completed.totalWaitMs,
          elapsedS: dbSummary?.elapsedS ?? null,
          redisKey,
          redisPayloadBytes,
          workerMaxRssKb,
          uiSnapshotBefore,
          uiSnapshot,
          dbSummary,
          validations,
          latestSchedulePayload: completed.schedule,
        };

        scenarioResult.runs.push(runResult);
        console.log(`[${nowIso()}] mode=${modeConfig.mode} run=${runIndex + 1} completed schedule=${runResult.scheduleId} chosen=${runResult.chosenScenario}`);
        fs.writeFileSync(
          path.join(OUT_DIR, `${modeConfig.mode}_run${runIndex + 1}_latest_schedule.json`),
          JSON.stringify(completed.schedule, null, 2),
        );
      }

      if (scenarioResult.runs.length === 2) {
        const [a, b] = scenarioResult.runs;
        scenarioResult.consistent =
          a.chosenScenario === b.chosenScenario &&
          JSON.stringify(a.latestSchedulePayload?.resultSummary?.operational_quality_decision || null)
            === JSON.stringify(b.latestSchedulePayload?.resultSummary?.operational_quality_decision || null);
      }

      report.scenarios.push(scenarioResult);
    }

    const allPass = report.scenarios.every((scenario) => {
      const scenarioPass = scenario.runs.every((run) =>
        Object.values(run.validations).every(Boolean),
      );
      return scenarioPass && scenario.consistent;
    });
    report.verdict = allPass && report.schema.hasOperationalQualityModeColumn ? "pronto" : "nao pronto";
  } finally {
    if (chromeProc && !chromeProc.killed) {
      chromeProc.kill("SIGTERM");
    }
  }

  const md = buildMarkdown(report);
  fs.writeFileSync(path.join(OUT_DIR, "report.json"), JSON.stringify(report, null, 2));
  fs.writeFileSync(path.join(OUT_DIR, "report.md"), md);
  console.log(JSON.stringify({
    verdict: report.verdict,
    schema: report.schema,
    reportDir: OUT_DIR,
  }, null, 2));
}

run().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
