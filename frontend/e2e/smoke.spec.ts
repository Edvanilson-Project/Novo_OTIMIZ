/**
 * Smoke tests — pages load, core UI elements render, no JS crashes.
 * Requires the dev server running at E2E_BASE_URL (default: localhost:3000)
 * and a seeded backend at localhost:3001 with credentials admin/admin123.
 *
 * Run: npx playwright install chromium && npx playwright test
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
  await page.waitForURL(/dashboard|planner|operations/, { timeout: 10_000 });
}

// ─── Auth ────────────────────────────────────────────────────────────────────

test.describe('Auth', () => {
  test('login page renders and has email + password inputs', async ({ page }) => {
    await page.goto(`${BASE}/auth/login`);
    await expect(page.locator('input[type="email"], input[name="email"]')).toBeVisible();
    await expect(page.locator('input[type="password"]')).toBeVisible();
    await expect(page.locator('button[type="submit"]')).toBeVisible();
  });

  test('wrong credentials shows error', async ({ page }) => {
    await page.goto(`${BASE}/auth/login`);
    await page.locator('input[type="email"], input[name="email"]').fill('wrong@example.com');
    await page.locator('input[type="password"]').fill('wrongpass');
    await page.locator('button[type="submit"]').click();
    // Expect still on login or an error visible
    await expect(page).toHaveURL(/login/, { timeout: 5_000 });
  });
});

// ─── Navigation ──────────────────────────────────────────────────────────────

test.describe('Navigation (authenticated)', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
  });

  test('dashboard loads with a heading', async ({ page }) => {
    await page.goto(`${BASE}/dashboard`);
    await expect(page.locator('h1, h2, h3, h4, h5, h6').first()).toBeVisible({ timeout: 8_000 });
  });

  test('planner page loads', async ({ page }) => {
    await page.goto(`${BASE}/operations/planner`);
    await expect(page.locator('body')).not.toContainText('500');
    // Optimization button or loading indicator should appear
    await expect(
      page.locator('button').filter({ hasText: /Otimiza|Executar|Atualizar/i }).first(),
    ).toBeVisible({ timeout: 10_000 });
  });

  test('map page loads', async ({ page }) => {
    await page.goto(`${BASE}/operations/map`);
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('h1, h2, h3, h4').filter({ hasText: /Mapa/i }).first()).toBeVisible({ timeout: 8_000 });
  });

  test('data page loads', async ({ page }) => {
    await page.goto(`${BASE}/operations/data`);
    await expect(page.locator('body')).not.toContainText('500');
  });

  test('parameters page loads', async ({ page }) => {
    await page.goto(`${BASE}/settings/parameters`);
    await expect(page.locator('body')).not.toContainText('500');
  });

  test('users page loads', async ({ page }) => {
    await page.goto(`${BASE}/settings/users`);
    await expect(page.locator('body')).not.toContainText('500');
  });

  test('fleet page loads', async ({ page }) => {
    await page.goto(`${BASE}/settings/fleet`);
    await expect(page.locator('body')).not.toContainText('500');
  });
});

// ─── Planner controls ────────────────────────────────────────────────────────

test.describe('Planner controls', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/planner`);
    await page.locator('button').filter({ hasText: /Otimiza|Executar|Atualizar/i }).first().waitFor({ timeout: 10_000 });
  });

  test('algorithm selector renders expected options', async ({ page }) => {
    await page.locator('label').filter({ hasText: /Algoritmo/i }).first().click();
    await expect(page.locator('[role="option"]').filter({ hasText: /Guloso/i })).toBeVisible({ timeout: 4_000 });
    await page.keyboard.press('Escape');
  });

  test('quality mode selector renders', async ({ page }) => {
    await expect(page.locator('label').filter({ hasText: /Qualidade Operacional/i })).toBeVisible();
  });

  test('Executar Otimizacao button is present', async ({ page }) => {
    await expect(
      page.locator('button').filter({ hasText: /Executar Otimiza/i }),
    ).toBeVisible();
  });
});

// ─── GTFS import ─────────────────────────────────────────────────────────────

test.describe('GTFS import', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/data`);
  });

  test('Importar GTFS button is visible on trips tab', async ({ page }) => {
    // Navigate to the viagens/trips tab if tabs exist
    const tripsTab = page.locator('[role="tab"]').filter({ hasText: /Viagen|Trip/i });
    if (await tripsTab.count() > 0) await tripsTab.first().click();
    await expect(
      page.locator('button').filter({ hasText: /GTFS/i }),
    ).toBeVisible({ timeout: 6_000 });
  });
});

// ─── Custom reports ──────────────────────────────────────────────────────────

test.describe('Custom reports page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/reporting/custom`);
  });

  test('page loads without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('h1, h2, h3, h4').first()).toBeVisible({ timeout: 8_000 });
  });
});

// ─── Terminals — isDepot ─────────────────────────────────────────────────────

test.describe('Terminals page (isDepot)', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/terminals`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('terminals page loads without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('h1, h2, h3, h4').first()).toBeVisible({ timeout: 8_000 });
  });

  test('Novo Terminal button opens dialog', async ({ page }) => {
    const btn = page.locator('button').filter({ hasText: /Novo Terminal|Adicionar/i }).first();
    if (await btn.count() > 0) {
      await btn.click();
      await expect(page.locator('[role="dialog"]')).toBeVisible({ timeout: 4_000 });
    }
  });

  test('terminal dialog has isDepot toggle', async ({ page }) => {
    const btn = page.locator('button').filter({ hasText: /Novo Terminal|Adicionar/i }).first();
    if (await btn.count() > 0) {
      await btn.click();
      await page.locator('[role="dialog"]').waitFor({ timeout: 4_000 });
      // Switch para "Garagem/Depósito" deve estar presente
      await expect(
        page.locator('[role="checkbox"], input[type="checkbox"]').or(
          page.locator('[role="switch"]'),
        ).first(),
      ).toBeVisible({ timeout: 4_000 });
    }
  });
});

// ─── Fleet management — depot selector ───────────────────────────────────────

test.describe('Fleet management page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/settings/fleet`);
    await page.locator('body').waitFor({ timeout: 8_000 });
  });

  test('fleet page shows vehicle types and vehicles sections', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(
      page.locator('h1, h2, h3, h4, h5, h6').filter({ hasText: /Tipo|Veículo|Frota/i }).first(),
    ).toBeVisible({ timeout: 8_000 });
  });

  test('Novo Veículo dialog has Garagem selector', async ({ page }) => {
    const btn = page.locator('button').filter({ hasText: /Novo Veículo/i }).first();
    if (await btn.count() > 0) {
      await btn.click();
      await page.locator('[role="dialog"]').waitFor({ timeout: 4_000 });
      await expect(
        page.locator('[role="dialog"]').locator('label').filter({ hasText: /Garagem|Depot/i }),
      ).toBeVisible({ timeout: 4_000 });
    }
  });
});

// ─── Advanced optimization — 4 abas ──────────────────────────────────────────

test.describe('Advanced optimization page', () => {
  test.beforeEach(async ({ page }) => {
    await login(page);
    await page.goto(`${BASE}/operations/advanced-optimization`);
    await page.locator('body').waitFor({ timeout: 10_000 });
  });

  test('page loads without crash', async ({ page }) => {
    await expect(page.locator('body')).not.toContainText('500');
    await expect(page.locator('h1, h2, h3, h4').filter({ hasText: /Otimiza/i }).first()).toBeVisible({ timeout: 8_000 });
  });

  test('tabs Cenários, What-If, Explicador, Monitor são visíveis', async ({ page }) => {
    await expect(page.locator('[role="tab"]').filter({ hasText: /Cenário/i })).toBeVisible({ timeout: 6_000 });
    await expect(page.locator('[role="tab"]').filter({ hasText: /What-If/i })).toBeVisible({ timeout: 4_000 });
    await expect(page.locator('[role="tab"]').filter({ hasText: /Explicador/i })).toBeVisible({ timeout: 4_000 });
    await expect(page.locator('[role="tab"]').filter({ hasText: /Monitor/i })).toBeVisible({ timeout: 4_000 });
  });

  test('What-If tab renderiza painel', async ({ page }) => {
    await page.locator('[role="tab"]').filter({ hasText: /What-If/i }).click();
    // Deve aparecer conteúdo do painel ou mensagem de nenhuma otimização
    await expect(page.locator('body')).not.toContainText('500');
    await page.waitForTimeout(1_000);
    const hasPanel = await page.locator('body').textContent();
    expect(hasPanel).not.toContain('Unhandled');
  });

  test('Executar Otimização button is present', async ({ page }) => {
    await expect(
      page.locator('button').filter({ hasText: /Executar Otimiza|Otimizando/i }),
    ).toBeVisible({ timeout: 6_000 });
  });
});
