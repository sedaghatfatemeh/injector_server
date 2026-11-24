import { test, expect } from '@playwright/test';

async function catalogApi(page, role = 'super_admin') {
  // External font availability must not hold local form/navigation tests open.
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/, route => route.abort());
  const models = [{ id: 1, code: 'AD-UNIT-B', display_name: 'یونیت باکس', kind: 'unit', kind_label: 'یونیت', edition: 'b', edition_label: 'باکس کنار دستگاه', is_active: true }];
  const devices = [];
  await page.route('**/api/v1/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let json = { count: 0, results: [], next: null, previous: null };
    if (path.endsWith('/auth/csrf/')) json = { csrfToken: 'test-csrf' };
    if (path.endsWith('/auth/session/')) json = { role, email: 'staff@example.test' };
    if (path.endsWith('/dashboard/summary/')) json = { device_count: devices.length, online_count: 0, offline_count: devices.length, online_window_minutes: 15 };
    if (path.endsWith('/customers/')) json.results = [{ id: 8, organization_name: 'کارگاه نمونه', is_archived: false }];
    if (path.endsWith('/device-models/')) {
      if (request.method() === 'POST') {
        json = { ...request.postDataJSON(), id: 2, kind_label: 'تست پمپ', edition_label: 'اقتصادی' };
        models.push(json);
      } else json = { ...json, results: models, count: models.length };
    }
    if (path.endsWith('/devices/')) {
      if (request.method() === 'POST') {
        json = { ...request.postDataJSON(), id: devices.length + 1, model_name: 'AD-PUMP-X', is_online: false };
        devices.push(json);
      } else json = { ...json, results: devices, count: devices.length };
    }
    await route.fulfill({ status: request.method() === 'POST' && !path.includes('/auth/') ? 201 : 200, json });
  });
}

test('administrator defines a model and selects it for multiple devices of one customer', async ({ page }) => {
  await catalogApi(page);
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('navigation').getByRole('button', { name: 'مدل‌های دستگاه', exact: true }).click();
  await page.getByRole('button', { name: 'تعریف مدل', exact: true }).click();
  const modelForm = page.getByRole('dialog', { name: 'تعریف مدل دستگاه' });
  await modelForm.getByRole('radio', { name: 'تست پمپ', exact: true }).check();
  await modelForm.getByRole('radio', { name: 'اقتصادی', exact: true }).check();
  await modelForm.getByLabel('کد مدل', { exact: true }).fill('ad-pump-x');
  await modelForm.getByLabel('نام نمایشی', { exact: true }).fill('پمپ اقتصادی ویژه');
  await modelForm.getByRole('button', { name: 'ذخیره مدل', exact: true }).click();
  await expect(modelForm).toHaveCount(0);
  await expect(page.getByRole('cell', { name: 'AD-PUMP-X', exact: true })).toBeVisible();
  await page.getByRole('navigation').getByRole('button', { name: 'دستگاه‌ها', exact: true }).click();
  for (const serial of ['MODEL-1', 'MODEL-2']) {
    await page.getByRole('button', { name: 'ثبت دستگاه', exact: true }).click();
    const form = page.getByRole('dialog');
    await form.getByLabel('شماره سریال', { exact: true }).fill(serial);
    await form.getByRole('combobox', { name: 'مدل دستگاه', exact: true }).selectOption('2');
    await form.getByRole('combobox', { name: 'مشتری', exact: true }).selectOption('8');
    const pending = page.waitForRequest(request => request.method() === 'POST' && new URL(request.url()).pathname === '/api/v1/devices/');
    await form.getByRole('button', { name: 'ذخیره', exact: true }).click();
    const data = (await pending).postDataJSON();
    expect(data.device_model).toBe(2);
    expect(data.customer).toBe(8);
    expect(data.model_name).toBeUndefined();
    await expect(form).toHaveCount(0);
  }
  await expect(page.getByRole('button', { name: 'MODEL-1', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'MODEL-2', exact: true })).toBeVisible();
});

test('support can inspect models without provisioning controls on mobile', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await catalogApi(page, 'support');
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  await page.getByRole('button', { name: 'باز کردن منو' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'مدل‌های دستگاه', exact: true }).click();
  await expect(page.getByRole('cell', { name: 'AD-UNIT-B', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'تعریف مدل', exact: true })).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
