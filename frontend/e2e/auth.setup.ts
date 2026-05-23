import { mkdirSync } from 'node:fs';
import path from 'node:path';
import { test as setup, expect } from '@playwright/test';

const authFile = path.join(__dirname, '.auth/user.json');
const BASE = process.env.E2E_BASE_URL ?? 'http://127.0.0.1:3005';
const USER = process.env.E2E_USER ?? 'admin@empresa.com';
const PASS = process.env.E2E_PASS ?? 'admin123';

setup('authenticate once for E2E suite', async ({ page }) => {
  mkdirSync(path.dirname(authFile), { recursive: true });

  await page.goto(`${BASE}/auth/login`, { waitUntil: 'networkidle' });
  await page.getByRole('textbox', { name: /e-mail/i }).fill(USER);
  await page.getByRole('textbox', { name: /senha/i }).fill(PASS);

  await page.getByRole('button', { name: /^Entrar$/i }).click();

  try {
    await page.waitForURL(/\/dashboard(?:[/?#].*)?$/, { timeout: 20_000 });
  } catch {
    const bodyText = (await page.locator('body').textContent())
      ?.replace(/\s+/g, ' ')
      .trim();
    throw new Error(`Auth failed or navigation timeout. Page text: ${bodyText}`);
  }

  await expect(page.locator('body')).not.toContainText('Credenciais inválidas');

  await page.context().storageState({ path: authFile });
});