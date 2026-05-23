import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { test as setup, expect } from '@playwright/test';

const authFile = path.join(__dirname, '.auth/user.json');
const BASE = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3005';
const USER = process.env.E2E_USER ?? 'admin@empresa.com';
const PASS = process.env.E2E_PASS ?? 'admin123';

setup('authenticate once for E2E suite', async ({ page }) => {
  mkdirSync(path.dirname(authFile), { recursive: true });

  await page.goto(`${BASE}/auth/login`);
  await page.getByRole('textbox', { name: /e-mail/i }).fill(USER);
  await page.getByRole('textbox', { name: /senha/i }).fill(PASS);
  await Promise.all([
    page.waitForResponse(
      (response) =>
        response.url().includes('/api/v1/auth/login') && response.status() === 200,
      { timeout: 15_000 },
    ),
    page.getByRole('button', { name: /^Entrar$/i }).click(),
  ]);
  await page.goto(`${BASE}/dashboard`, { waitUntil: 'networkidle' });
  await expect(page.locator('body')).not.toContainText('Credenciais inválidas');

  await page.context().storageState({ path: authFile });
});