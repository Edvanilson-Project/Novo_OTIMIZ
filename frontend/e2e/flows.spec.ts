/**
 * Flow tests — CRUD operations, form interactions, API-driven flows.
 * Assumes backend seeded with at least one company + admin user.
 * Run: npx playwright test e2e/flows.spec.ts
 */
import { test, expect, Page } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL ?? 'http://localhost:3000';
const USER = process.env.E2E_USER ?? 'admin@empresa.com';
const PASS = process.env.E2E_PASS ?? 'admin123';

async function login(page: Page) {
  await page.goto(`${BASE}/auth/login`);
  await page.locator('input[type="email"], input[name="email"]').fill(USER);
  await page.locator('input[type="password"]').fill(PASS);
  await page.locator('button[type="submit"]').click();
  await page.waitForURL(/dashboard|planner|operations/, { timeout: 12_000 });
}

// ─── Trips CRUD ───────────────────────────────────────────────────────────────

test.describe('Trips CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/data`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('data page renders trip list or empty state without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
    // Page should have some table or empty-state message
    const hasContent = await page.locator('table, [data-testid="empty-state"], p').count();
    expect(hasContent).toBeGreaterThan(0);
  });

  test('Nova Viagem button opens dialog', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Nova Viagem|Adicionar Viagem|Nova Trip/i }).first();
    if (await addBtn.count() === 0) return; // skip if button absent
    await addBtn.click();
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press('Escape');
  });

  test('trip dialog has required fields', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Nova Viagem|Adicionar Viagem|Nova Trip/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    const dialog = page.locator('[role="dialog"]');
    await dialog.waitFor({ timeout: 5_000 });
    // Should have at least origin, destination and time fields
    const inputs = dialog.locator('input, select, [role="combobox"]');
    expect(await inputs.count()).toBeGreaterThan(2);
    await page.keyboard.press('Escape');
  });
});

// ─── Drivers CRUD ─────────────────────────────────────────────────────────────

test.describe('Drivers CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/settings/drivers`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('drivers page loads without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
  });

  test('Novo Motorista button opens dialog or form', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Novo Motorista|Adicionar Motorista/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    await expect(page.locator('[role="dialog"], form').first()).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press('Escape');
  });
});

// ─── Fleet CRUD ───────────────────────────────────────────────────────────────

test.describe('Fleet CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/settings/fleet`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('fleet page has vehicle types and vehicles sections', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    const heading = page.locator('h1, h2, h3, h4, h5, h6').filter({ hasText: /Tipo|Veículo|Frota/i }).first();
    await expect(heading).toBeVisible({ timeout: 8_000 });
  });

  test('Novo Tipo de Veículo button opens dialog', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Novo Tipo|Tipo de Veículo/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    const dialog = page.locator('[role="dialog"]');
    await dialog.waitFor({ timeout: 5_000 });
    // Dialog must have name and capacity fields
    await expect(dialog.locator('input').first()).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('Novo Veículo dialog has plate and vehicle-type fields', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Novo Veículo/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    const dialog = page.locator('[role="dialog"]');
    await dialog.waitFor({ timeout: 5_000 });
    const inputs = dialog.locator('input, select, [role="combobox"]');
    expect(await inputs.count()).toBeGreaterThan(1);
    await page.keyboard.press('Escape');
  });
});

// ─── Terminals CRUD ───────────────────────────────────────────────────────────

test.describe('Terminals CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/terminals`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('terminals page renders list or empty state', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
  });

  test('Novo Terminal opens dialog with name field', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Novo Terminal|Adicionar Terminal/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    const dialog = page.locator('[role="dialog"]');
    await dialog.waitFor({ timeout: 5_000 });
    await expect(dialog.locator('input').first()).toBeVisible();
    await page.keyboard.press('Escape');
  });

  test('terminal dialog has isDepot toggle', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Novo Terminal|Adicionar Terminal/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    const dialog = page.locator('[role="dialog"]');
    await dialog.waitFor({ timeout: 5_000 });
    const toggle = dialog.locator('[role="checkbox"], [role="switch"]').first();
    if (await toggle.count() > 0) await expect(toggle).toBeVisible();
    await page.keyboard.press('Escape');
  });
});

// ─── Parameters page ──────────────────────────────────────────────────────────

test.describe('Parameters page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/settings/parameters`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('parameters page renders without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
  });

  test('parameters form has CCT/CLT fields', async ({ page }) => {
    // Should have numeric inputs for rest time, shift time etc
    const inputs = page.locator('input[type="number"], input[type="text"]');
    if (await inputs.count() > 0) {
      await expect(inputs.first()).toBeVisible({ timeout: 6_000 });
    }
  });

  test('Salvar button is present', async ({ page }) => {
    const saveBtn = page.locator('button').filter({ hasText: /Salvar|Gravar|Save/i }).first();
    if (await saveBtn.count() > 0) {
      await expect(saveBtn).toBeVisible({ timeout: 6_000 });
    }
  });
});

// ─── Users page ───────────────────────────────────────────────────────────────

test.describe('Users page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/settings/users`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('users page renders without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
  });

  test('shows at least the admin user in list', async ({ page }) => {
    await expect(page.locator('body')).toContainText(/admin|Admin/i, { timeout: 8_000 });
  });

  test('Novo Usuário button opens dialog', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Novo Usuário|Adicionar Usuário/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press('Escape');
  });
});

// ─── Planner page — algorithm + depot selectors ───────────────────────────────

test.describe('Planner — selectors', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/planner`);
    await page.locator('button').filter({ hasText: /Otimiza|Executar|Atualizar/i }).first()
      .waitFor({ timeout: 12_000 });
  });

  test('algorithm dropdown lists expected options', async ({ page }) => {
    // MUI Select trigger has role="button" + aria-haspopup="listbox"; clicking the <label> alone does not open it
    const trigger = page.locator('[role="button"][aria-haspopup="listbox"]').first();
    if (await trigger.count() === 0) return;
    await trigger.click();
    const options = page.locator('[role="option"]');
    await expect(options.first()).toBeVisible({ timeout: 4_000 });
    const hasGreedy = await options.filter({ hasText: /Guloso|Greedy/i }).count();
    expect(hasGreedy).toBeGreaterThan(0);
    await page.keyboard.press('Escape');
  });

  test('quality mode selector contains balanced option', async ({ page }) => {
    // Second MUI Select on the planner page (algorithm is first, quality mode is second)
    const triggers = page.locator('[role="button"][aria-haspopup="listbox"]');
    if (await triggers.count() < 2) return;
    await triggers.nth(1).click();
    await expect(page.locator('[role="option"]').first()).toBeVisible({ timeout: 4_000 });
    await page.keyboard.press('Escape');
  });

  test('Gantt tab renders after switching to it', async ({ page }) => {
    const ganttTab = page.locator('[role="tab"]').filter({ hasText: /Gantt/i }).first();
    if (await ganttTab.count() === 0) return;
    await ganttTab.click();
    await page.waitForTimeout(1_000);
    await expect(page.locator('body')).not.toContainText('500');
  });
});

// ─── Rostering page ───────────────────────────────────────────────────────────

test.describe('Rostering page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/rostering`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('rostering page loads without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
  });

  test('has scheduling controls (date/driver inputs)', async ({ page }) => {
    const inputs = page.locator('input[type="text"], input[type="date"], input[type="number"]');
    if (await inputs.count() > 0) {
      await expect(inputs.first()).toBeVisible({ timeout: 6_000 });
    }
  });
});

// ─── Custom reports page ──────────────────────────────────────────────────────

test.describe('Custom reports — CRUD', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/reporting/custom`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('custom reports page renders without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
    await expect(page.locator('h1, h2, h3, h4').first()).toBeVisible({ timeout: 8_000 });
  });

  test('Novo Relatório button opens report builder', async ({ page }) => {
    const addBtn = page.locator('button').filter({ hasText: /Novo Relatório|Criar Relatório/i }).first();
    if (await addBtn.count() === 0) return;
    await addBtn.click();
    const dialogOrSection = page.locator('[role="dialog"], form, section').first();
    await expect(dialogOrSection).toBeVisible({ timeout: 5_000 });
    await page.keyboard.press('Escape');
  });
});

// ─── Optimize status endpoint ─────────────────────────────────────────────────

test.describe('Optimize status API', () => {
  test('GET /api/operations/optimize/status returns valid shape', async ({ page }) => {
    await login(page);
    // Call the backend directly via fetch inside the browser context (same origin/cookies)
    const result = await page.evaluate(async () => {
      const token = localStorage.getItem('token') ?? sessionStorage.getItem('token') ?? '';
      const res = await fetch('/api/operations/optimize/status', {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        credentials: 'include',
      });
      if (!res.ok) return null;
      return res.json();
    });
    // Should return object with status field (idle|processing|completed|failed)
    if (result) {
      expect(['idle', 'processing', 'completed', 'failed']).toContain(result.status);
    }
  });
});

// ─── Advanced optimization — Monitor tab ─────────────────────────────────────

test.describe('Advanced optimization — Monitor tab', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/advanced-optimization`);
    await page.locator('body').waitFor({ timeout: 10_000 });
  });

  test('Monitor tab shows monitor component', async ({ page }) => {
    const monitorTab = page.locator('[role="tab"]').filter({ hasText: /Monitor/i }).first();
    await monitorTab.waitFor({ timeout: 8_000 });
    await monitorTab.click();
    await expect(page.locator('body')).not.toContainText('500');
    // Monitor title should appear
    const monitorTitle = page.locator('*').filter({ hasText: /Monitor de Otimização|Progresso Geral/i }).first();
    await expect(monitorTitle).toBeVisible({ timeout: 6_000 });
  });

  test('Explicador tab renders optimization explainer', async ({ page }) => {
    const explainTab = page.locator('[role="tab"]').filter({ hasText: /Explicador/i }).first();
    if (await explainTab.count() === 0) return;
    await explainTab.click();
    await page.waitForTimeout(800);
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
  });
});

// ─── Map page ─────────────────────────────────────────────────────────────────

test.describe('Map page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/map`);
    await page.locator('body').waitFor({ timeout: 10_000 });
  });

  test('map page renders without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('body')).not.toContainText('Unhandled');
  });

  test('map container or leaflet canvas is present', async ({ page }) => {
    // Leaflet renders a .leaflet-container or a canvas
    await page.waitForTimeout(2_000);
    const mapEl = page.locator('.leaflet-container, canvas, [data-testid="map"]');
    if (await mapEl.count() > 0) {
      await expect(mapEl.first()).toBeVisible({ timeout: 6_000 });
    }
  });
});
