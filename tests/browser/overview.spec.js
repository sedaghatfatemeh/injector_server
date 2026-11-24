import { test, expect } from '@playwright/test';

async function fleet(page, role = 'super_admin', total = 37) {
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname;
    let json = { count: 0, results: [], next: null, previous: null };
    if (path.endsWith('/auth/csrf/')) json = { csrfToken: 'test-csrf' };
    if (path.endsWith('/auth/session/')) json = { role, email: 'staff@example.test' };
    if (path.endsWith('/dashboard/summary/')) json = {
      device_count: total, online_count: total ? 32 : 0, offline_count: total ? 5 : 0,
      active_fault_count: total ? 2 : 0, event_count_24h: total ? 128 : 0,
      generated_at: '2026-11-24T10:00:00Z', online_window_minutes: 15,
    };
    if (path.endsWith('/devices/') && total) json.results = Array.from({ length: 5 }, (_, i) => ({
      id: i + 1, serial_number: `INJ-00123${i + 5}`, model_name: 'PX-500',
      is_online: i < 4, last_seen_at: i < 4 ? '2026-11-24T09:55:00Z' : null,
      installation_location: ['مشهد', 'تهران', 'اصفهان', 'تبریز', 'شیراز'][i],
    }));
    return route.fulfill({ json });
  });
}

test('reference overview uses server aggregates and functional shortcuts', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await fleet(page);
  await page.goto('/');
  await expect(page.getByRole('region', { name: 'آمار ناوگان' })).toContainText('۳۷');
  await expect(page.getByRole('img', { name: /۳۲ متصل و ۵/ })).toBeVisible();
  await expect(page.getByRole('button', { name: 'INJ-001235' })).toBeVisible();
  await page.screenshot({ path: '.local/dashboard-reference-desktop.png', fullPage: true });
  await page.getByRole('button', { name: /مدیریت کاربران تعریف/ }).click();
  await expect(page.getByRole('button', { name: 'افزودن کاربر', exact: true })).toBeVisible();
});

test('empty support overview fits mobile without admin shortcuts or invented data', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await fleet(page, 'support', 0);
  await page.goto('/');
  await expect(page.getByText('هنوز دستگاهی ثبت نشده است.', { exact: true })).toBeVisible();
  await expect(page.getByRole('img', { name: /۰ متصل و ۰/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /مدیریت کاربران/ })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '.local/dashboard-reference-mobile.png', fullPage: true });
});
