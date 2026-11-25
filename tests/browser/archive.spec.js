import { test, expect } from '@playwright/test';

async function inventoryApi(page) {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/, route => route.abort());
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let json = { count: 0, results: [], next: null, previous: null };
    if (path.endsWith('/auth/csrf/')) json = { csrfToken: 'test-csrf' };
    if (path.endsWith('/auth/session/')) json = { role: 'super_admin', email: 'admin@example.test' };
    if (path.endsWith('/dashboard/summary/')) json = { device_count: 2, online_window_minutes: 15 };
    const archived = url.searchParams.get('archive_status') === 'archived';
    if (path.endsWith('/devices/')) {
      const second = url.searchParams.get('page') === '2';
      json = { count: archived ? 51 : 1, results: [{ id: second ? 52 : 1, serial_number: archived ? (second ? 'OLD-052' : 'OLD-001') : 'ACTIVE-001', model_name: 'M1', is_archived: archived, is_online: false, customer_is_archived: archived }], next: archived && !second ? '?page=2' : null, previous: second ? '?page=1' : null };
    }
    if (path.endsWith('/customers/')) json = { ...json, count: 1, results: [{ id: 8, organization_name: archived ? 'سازمان بایگانی' : 'سازمان فعال', is_archived: archived }] };
    return route.fulfill({ json });
  });
}

test('archive selection keeps search and pagination and archived details are read-only', async ({ page }) => {
  test.setTimeout(60000);
  await inventoryApi(page);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('navigation', { name: 'منوی اصلی' }).getByRole('button', { name: 'دستگاه‌ها', exact: true }).click();
  await expect(page.getByRole('button', { name: 'ACTIVE-001', exact: true })).toBeVisible();
  await page.getByRole('combobox', { name: 'وضعیت بایگانی' }).selectOption('archived');
  await expect(page.getByRole('button', { name: 'OLD-001', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'بایگانی', exact: true })).toHaveCount(0);
  await page.getByPlaceholder('جست‌وجوی سریال، مشتری یا مدل').fill('OLD');
  await expect(page.getByRole('button', { name: 'OLD-001', exact: true })).toBeVisible();
  const nextRequest = page.waitForRequest(request => new URL(request.url()).pathname === '/api/v1/devices/' && new URL(request.url()).searchParams.get('page') === '2');
  await page.getByRole('navigation', { name: 'صفحه‌بندی فهرست' }).getByRole('button', { name: 'بعدی', exact: true }).click();
  const url = new URL((await nextRequest).url());
  expect(url.searchParams.get('archive_status')).toBe('archived');
  expect(url.searchParams.get('search')).toBe('OLD');
  const history = page.waitForRequest(request => new URL(request.url()).pathname === '/api/v1/devices/52/events/');
  await page.getByRole('button', { name: 'OLD-052', exact: true }).click();
  const historyUrl = new URL((await history).url());
  expect(historyUrl.searchParams.get('is_archived')).toBe('true');
  expect(historyUrl.searchParams.get('device__customer__is_archived')).toBe('true');
  await expect(page.getByRole('dialog')).toBeVisible();
  await expect(page.getByRole('button', { name: 'صدور/چرخش شناسهٔ دستگاه', exact: true })).toHaveCount(0);
  await page.keyboard.press('Escape');
  await page.getByRole('combobox', { name: 'وضعیت بایگانی' }).selectOption('all');
  await expect(page.getByRole('navigation', { name: 'صفحه‌بندی فهرست' })).toContainText('صفحهٔ ۱');
});

test('other lists filter by inactive or withdrawn status without calling it archive', async ({ page }) => {
  test.setTimeout(60000);
  await inventoryApi(page);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  for (const [menu, label, path, parameter, value] of [
    ['مدل‌های دستگاه', 'وضعیت مدل', '/api/v1/device-models/', 'is_active', 'false'],
    ['کاربران', 'وضعیت حساب', '/api/v1/staff-users/', 'is_active', 'false'],
    ['حساب‌های مشتریان', 'وضعیت حساب', '/api/v1/customer-users/', 'is_active', 'false'],
    ['به‌روزرسانی‌ها', 'وضعیت نسخه', '/api/v1/releases/', 'status', 'withdrawn'],
  ]) {
    await page.getByRole('navigation', { name: 'منوی اصلی' }).getByRole('button', { name: menu, exact: true }).click();
    const request = page.waitForRequest(req => new URL(req.url()).pathname === path && new URL(req.url()).searchParams.get(parameter) === value);
    await page.getByRole('combobox', { name: label }).selectOption(value);
    await request;
  }
});

test('customer archive filter is usable in the mobile staff drawer', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await inventoryApi(page);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'باز کردن منو' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'مشتریان', exact: true }).click();
  await page.getByRole('combobox', { name: 'وضعیت بایگانی' }).selectOption('archived');
  await expect(page.getByRole('cell', { name: 'سازمان بایگانی', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'ویرایش', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
