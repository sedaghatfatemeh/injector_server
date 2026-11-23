import { test, expect } from '@playwright/test';

async function mockApi(page, role = 'super_admin') {
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    let body = { count: 0, results: [], next: null, previous: null };
    if (path.endsWith('/auth/csrf/')) body = { csrfToken: 'browser-test-csrf' };
    if (path.endsWith('/auth/session/')) body = { role, email: 'staff@example.test' };
    if (path.endsWith('/dashboard/summary/')) body = {
      device_count: 0, online_count: 0, offline_count: 0, active_fault_count: 0,
      event_count_24h: 0, generated_at: '2026-11-16T10:00:00Z', online_window_minutes: 15,
    };
    await route.fulfill({ json: body });
  });
}

test('session restoration waits before displaying login or fleet data', async ({ page }) => {
  await mockApi(page);
  let releaseSession;
  const pending = new Promise(resolve => { releaseSession = resolve; });
  await page.route('**/auth/session/', async route => {
    await pending;
    await route.fulfill({ json: { role: 'support', email: 'support@example.test' } });
  });
  await page.goto('/');
  await expect(page.getByRole('status')).toHaveText('در حال بررسی نشست…');
  await expect(page.getByRole('textbox', { name: 'ایمیل' })).toHaveCount(0);
  releaseSession();
  await expect(page.getByRole('heading', { name: 'نمای کلی' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'کاربران', exact: true })).toHaveCount(0);
});

test('form dialog traps keyboard focus and restores the invoking control', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'مشتریان', exact: true }).click();
  const add = page.getByRole('button', { name: 'ثبت مشتری', exact: true });
  await add.click();
  const dialog = page.getByRole('dialog', { name: 'ثبت مشتری' });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('button', { name: 'بستن' })).toBeFocused();
  await page.keyboard.press('Shift+Tab');
  await expect(dialog.getByRole('button', { name: 'ذخیره', exact: true })).toBeFocused();
  await page.keyboard.press('Tab');
  await expect(dialog.getByRole('button', { name: 'بستن' })).toBeFocused();
  await page.keyboard.press('Escape');
  await expect(dialog).toHaveCount(0);
  await expect(add).toBeFocused();
  await expect(page.locator('body')).not.toHaveCSS('overflow', 'hidden');
});

test('staff account dialog uses the same dismissal and focus behavior', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'کاربران', exact: true }).click();
  const add = page.getByRole('button', { name: 'افزودن کاربر', exact: true });
  await add.click();
  await expect(page.getByRole('dialog', { name: 'افزودن کاربر' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(add).toBeFocused();
});

test('mobile navigation is an RTL drawer that closes after selection', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await mockApi(page);
  await page.goto('/');
  const toggle = page.getByRole('button', { name: 'باز کردن منو' });
  await toggle.click();
  const drawer = page.getByRole('dialog', { name: 'منوی اصلی' });
  await expect(drawer).toHaveAttribute('dir', 'rtl');
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await drawer.getByRole('button', { name: 'رویدادها و خطاها' }).click();
  await expect(drawer).toHaveCount(0);
  await expect(page.getByRole('heading', { name: 'رویدادها و خطاها' })).toBeVisible();
  await expect(toggle).toBeFocused();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test('theme survives reload and unavailable storage does not prevent access', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'تغییر پوسته' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.addInitScript(() => {
    Storage.prototype.getItem = () => { throw new DOMException('Unavailable', 'SecurityError'); };
    Storage.prototype.setItem = () => { throw new DOMException('Unavailable', 'SecurityError'); };
  });
  await page.reload();
  await expect(page.getByRole('heading', { name: 'نمای کلی' })).toBeVisible();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
});

test('an HTML gateway response is a visible connection error, not an empty fleet', async ({ page }) => {
  await mockApi(page);
  await page.route('**/auth/session/', route => route.fulfill({ contentType: 'text/html', body: '<html>Gateway failure</html>' }));
  await page.goto('/');
  await expect(page.getByRole('alert')).toContainText('ارتباط با سامانه برقرار نشد');
  await expect(page.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'نمای کلی' })).toHaveCount(0);
});

test('an expired session on event history returns to staff login', async ({ page }) => {
  await mockApi(page);
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'رویدادها و خطاها' }).click();
  await expect(page.getByRole('heading', { name: 'رویدادها و خطاها' })).toBeVisible();
  await page.route('**/api/v1/events/**', route => route.fulfill({ status: 403, json: { detail: 'Session expired' } }));
  await page.getByRole('region', { name: 'تاریخچه رویدادها' }).getByRole('button', { name: 'بازخوانی' }).click();
  await expect(page.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('نشست شما پایان یافته');
  await expect(page.getByRole('button', { name: 'ورود', exact: true })).toBeEnabled();
});
