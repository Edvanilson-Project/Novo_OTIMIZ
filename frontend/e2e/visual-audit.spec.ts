import fs from 'node:fs';
import path from 'node:path';
import { test, expect, request as playwrightRequest } from '@playwright/test';

const BASE = process.env.E2E_BASE_URL ?? 'https://localhost';
const API_BASE = process.env.E2E_API_URL ?? 'http://localhost:3001/api/v1/';
const AUTH_FILE = path.join(__dirname, '.auth/user.json');
const SCREENSHOT_DIR = '/home/edvanilson/.gemini/antigravity/brain/2ed1a431-d321-4511-9f8c-1d75d7a44922/browser_recordings';

// Create recordings directory if not exists
if (!fs.existsSync(SCREENSHOT_DIR)) {
  fs.mkdirSync(SCREENSHOT_DIR, { recursive: true });
}

async function capture(page: any, filename: string) {
  const filePath = path.join(SCREENSHOT_DIR, filename);
  await page.screenshot({ path: filePath, fullPage: true });
  console.log(`[AUDIT-CAPTURE] Saved screenshot to ${filePath}`);
}

test.describe('E2E Full System Visual Audit', () => {
  test('navigates all screens, tests parameters, runs optimization, and captures E2E evidence', async ({ page }, testInfo) => {
    test.setTimeout(300_000); // 5 minutes

    const runDigits = `${Date.now()}`.slice(-6);

    // 1. Auth Page
    console.log('--- Step 1: Login Page ---');
    await page.goto(`${BASE}/auth/login`, { waitUntil: 'networkidle' });
    await expect(page.locator('input[type="email"], input[name="email"]')).toBeVisible();
    await capture(page, '01_login_page.png');

    // Login using admin credentials
    await page.locator('input[type="email"], input[name="email"]').fill('admin@otimiz.com');
    await page.locator('input[type="password"]').fill('Otimiz@123');
    await page.locator('button[type="submit"]').click();
    await page.waitForURL(`${BASE}/dashboard`, { timeout: 15_000 });

    // 2. Dashboard
    console.log('--- Step 2: Dashboard ---');
    await page.waitForLoadState('networkidle');
    await expect(page.locator('h1, h2, h3, h4, h5, h6').first()).toBeVisible();
    await page.waitForTimeout(2000); // Let metrics load
    await capture(page, '02_dashboard.png');

    // 3. Operations Data (Gestão de Dados)
    console.log('--- Step 3: Operations Data ---');
    await page.goto(`${BASE}/operations/data`, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toContainText('Gestão de Dados Operacionais');
    await capture(page, '03_operations_data_trips.png');

    // Tabs under Operations Data (Viagens, Motoristas)
    const driversTab = page.locator('[role="tab"]').filter({ hasText: 'Motoristas' }).first();
    if (await driversTab.isVisible()) {
      await driversTab.click();
      await page.waitForTimeout(1000);
      await capture(page, '03_operations_data_drivers.png');
    }

    // 4. Terminals
    console.log('--- Step 4: Terminals ---');
    await page.goto(`${BASE}/operations/terminals`, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toContainText('Novo Terminal');
    await capture(page, '04_terminals_list.png');

    // Add Terminal dialog test
    const newTerminalBtn = page.locator('button').filter({ hasText: /Novo Terminal|Adicionar/i }).first();
    if (await newTerminalBtn.isVisible()) {
      await newTerminalBtn.click();
      await page.locator('[role="dialog"]').waitFor({ timeout: 5000 });
      await capture(page, '04_terminals_dialog.png');
      await page.keyboard.press('Escape'); // close dialog
      await page.waitForTimeout(500);
    }

    // 5. Fleet Settings
    console.log('--- Step 5: Fleet Settings ---');
    await page.goto(`${BASE}/settings/fleet`, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toContainText('Tipos de Veículos');
    await capture(page, '05_fleet_settings.png');

    // Add Vehicle dialog test
    const newVehicleBtn = page.locator('button').filter({ hasText: /Novo Veículo/i }).first();
    if (await newVehicleBtn.isVisible()) {
      await newVehicleBtn.click();
      await page.locator('[role="dialog"]').waitFor({ timeout: 5000 });
      await capture(page, '05_fleet_vehicle_dialog.png');
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }

    // 6. Parameters (Configuração de Parâmetros CCT e VSP)
    console.log('--- Step 6: Parameters ---');
    await page.goto(`${BASE}/settings/parameters`, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toContainText('Parâmetros');
    await capture(page, '06_parameters_cct.png');

    // Let's modify a VSP parameter to verify it works
    const layoverInput = page.locator('input[name="min_layover_minutes"], input[id="min_layover_minutes"]').first();
    if (await layoverInput.isVisible()) {
      await layoverInput.click({ clickCount: 3 });
      await layoverInput.fill('10'); // setting layover to 10 mins (highly stable baseline value)
      await capture(page, '06_parameters_modifying.png');
      // Save parameters if button exists
      const saveParamsBtn = page.locator('button').filter({ hasText: /Salvar|Guardar|Gravar/i }).first();
      if (await saveParamsBtn.isVisible()) {
        await saveParamsBtn.click();
        await page.waitForTimeout(1000); // Toast should appear
        await capture(page, '06_parameters_saved.png');
      }
    }

    // 7. Users and Permissions (RBAC)
    console.log('--- Step 7: Users & RBAC ---');
    await page.goto(`${BASE}/settings/users`, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toContainText('Usuários');
    await capture(page, '07_users_rbac.png');

    // 8. Map page
    console.log('--- Step 8: Operational Map ---');
    await page.goto(`${BASE}/operations/map`, { waitUntil: 'networkidle' });
    await page.waitForTimeout(3000); // Let map tiles render
    await capture(page, '08_operational_map.png');

    // 9. Reporting and Analytics
    console.log('--- Step 9: Reporting ---');
    await page.goto(`${BASE}/operations/reporting`, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toContainText('Analytics');
    await capture(page, '09_reporting_analytics.png');

    // Custom Reports
    await page.goto(`${BASE}/operations/reporting/custom`, { waitUntil: 'networkidle' });
    await capture(page, '09_custom_reports.png');

    // 10. Planner and E2E Optimization Run
    console.log('--- Step 10: Planner Page & Optimization ---');
    await page.goto(`${BASE}/operations/planner`, { waitUntil: 'networkidle' });
    const optimizeBtn = page.getByRole('button', { name: /Executar Otimização/i }).first();
    await expect(optimizeBtn).toBeVisible({ timeout: 15_000 });
    await capture(page, '10_planner_before_optimization.png');

    // Setup an API request context to trigger optimization
    const api = await playwrightRequest.newContext({
      baseURL: API_BASE,
      storageState: AUTH_FILE,
    });

    console.log('[AUDIT] Dispatching optimization run...');
    const optimizeRes = await api.post('operations/optimize', {
      data: {
        algorithm: 'hybrid_pipeline', // production default, mathematically superior at resolving crew duties
        operational_quality_mode: 'strict',
      },
    });
    expect(optimizeRes.ok()).toBeTruthy();

    // Poll for status
    console.log('[AUDIT] Polling optimization run status...');
    let statusText = 'processing';
    for (let i = 0; i < 60; i++) {
      await page.waitForTimeout(4000);
      const statusRes = await api.get('operations/optimize/status');
      const data = await statusRes.json();
      statusText = data.status;
      console.log(`[AUDIT] Polling iteration ${i + 1}: status = ${statusText}`);
      if (statusText === 'completed' || statusText === 'failed') {
        break;
      }
    }
    expect(statusText).toBe('completed');

    // Reload planner page to render Gantt and schedule details
    await page.reload({ waitUntil: 'networkidle' });
    await page.waitForTimeout(4000);
    await capture(page, '10_planner_optimization_completed.png');

    // Click "Validar Escala" button
    const validateEscalaBtn = page.getByRole('button', { name: /Validar Escala/i }).first();
    if (await validateEscalaBtn.isVisible()) {
      await validateEscalaBtn.click();
      await page.locator('[role="dialog"]').waitFor({ timeout: 5000 });
      await capture(page, '10_planner_validacao_escala.png');
      await page.keyboard.press('Escape');
      await page.waitForTimeout(500);
    }

    // 11. Advanced Optimization & What-If Scenarios
    console.log('--- Step 11: Advanced Optimization ---');
    await page.goto(`${BASE}/operations/advanced-optimization`, { waitUntil: 'networkidle' });
    await expect(page.locator('body')).toContainText('Cenários');
    await capture(page, '11_advanced_optimization_cenarios.png');

    // What-If Tab
    const whatIfTab = page.locator('[role="tab"]').filter({ hasText: /What-If/i }).first();
    if (await whatIfTab.isVisible()) {
      await whatIfTab.click();
      await page.waitForTimeout(2000);
      await capture(page, '11_advanced_optimization_whatif.png');
    }

    // Explicador Tab
    const explicadorTab = page.locator('[role="tab"]').filter({ hasText: /Explicador/i }).first();
    if (await explicadorTab.isVisible()) {
      await explicadorTab.click();
      await page.waitForTimeout(2000);
      await capture(page, '11_advanced_optimization_explicador.png');
    }

    // Monitor Tab
    const monitorTab = page.locator('[role="tab"]').filter({ hasText: /Monitor/i }).first();
    if (await monitorTab.isVisible()) {
      await monitorTab.click();
      await page.waitForTimeout(2000);
      await capture(page, '11_advanced_optimization_monitor.png');
    }

    console.log('[AUDIT] E2E Full System Visual Audit completed successfully.');
    await api.dispose();
  });
});
