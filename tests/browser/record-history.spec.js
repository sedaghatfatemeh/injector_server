import { test, expect } from '@playwright/test';

const history = {
  created: { at: '2025-03-20T20:30:00Z', by: 'مدیر ثبت' },
  edited: { at: '2025-03-21T09:10:11Z', by: 'کارشناس ویرایش' },
  archived: { at: '2025-03-21T10:11:12Z', by: 'کارشناس بایگانی' },
  withdrawn: { at: '2025-03-21T10:11:12Z', by: 'کارشناس پس‌گرفتن' },
};

async function historyApi(page, legacy = false, published = false) {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/, route => route.abort());
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    const base = { id: 1, created_at: '2025-03-20T20:30:00Z', record_history: legacy ? { created: { at: '2025-03-20T20:30:00Z', by: null }, edited: null, archived: null } : history };
    let json = { count: 0, results: [], next: null, previous: null };
    if (path.endsWith('/auth/csrf/')) json = { csrfToken: 'test-csrf' };
    if (path.endsWith('/auth/session/')) json = { role: 'super_admin', email: 'admin@example.test' };
    if (path.endsWith('/dashboard/summary/')) json = { device_count: 0 };
    if (path.endsWith('/devices/')) json.results = [{ ...base, serial_number: 'HISTORY-001', model_name: 'M1', is_archived: url.searchParams.get('archive_status') === 'archived', updated_at: '2099-01-01T00:00:00Z' }];
    if (path.endsWith('/customers/')) json.results = [{ ...base, organization_name: 'سازمان نمونه' }];
    if (path.endsWith('/device-models/')) json.results = [{ ...base, code: 'AD-UNIT-PC', display_name: 'یونیت', is_active: true }];
    if (path.endsWith('/staff-users/')) json.results = [{ ...base, email: 'staff@example.test', role: 'support', is_active: true }];
    if (path.endsWith('/customer-users/')) json.results = [{ ...base, email: 'customer@example.test', is_active: true, organization: { id: 8, name: 'سازمان نمونه' } }];
    if (path.endsWith('/releases/')) json.results = [{ ...base, version: '1.0.0', status: published ? 'published' : 'withdrawn', compatible_models: [] }];
    return route.fulfill({ json });
  });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
}

test('device archive metadata is visible in list and details with second precision', async ({ page }) => {
  test.setTimeout(60000);
  await historyApi(page);
  await page.getByRole('navigation', { name: 'منوی اصلی' }).getByRole('button', { name: 'دستگاه‌ها', exact: true }).click();
  await page.getByRole('combobox', { name: 'وضعیت بایگانی' }).selectOption('archived');
  await expect(page.getByRole('columnheader', { name: 'آخرین بایگانی و انجام‌دهنده', exact: true })).toBeVisible();
  await expect(page.getByText('کارشناس بایگانی', { exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: /۱۳:۴۱:۱۲.*کارشناس بایگانی/ })).toBeVisible();
  await page.getByRole('button', { name: 'HISTORY-001', exact: true }).click();
  const details = page.getByRole('region', { name: 'سوابق ثبت رکورد' });
  await expect(details.getByText('مدیر ثبت', { exact: true })).toBeVisible();
  await expect(details.getByText('کارشناس ویرایش', { exact: true })).toBeVisible();
  await expect(details.getByText('کارشناس بایگانی', { exact: true })).toBeVisible();
});

test('mobile lists keep metadata inside the horizontally scrollable table', async ({ page }) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 390, height: 844 });
  await historyApi(page);
  await page.getByRole('button', { name: 'باز کردن منو' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'دستگاه‌ها', exact: true }).click();
  await expect(page.getByRole('button', { name: 'HISTORY-001', exact: true })).toBeVisible();
  await page.locator('.live-table-wrap').evaluate(element => { element.scrollLeft = -element.scrollWidth; });
  await expect(page.getByText('کارشناس بایگانی', { exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('creation and administrative editing columns exist across managed menus', async ({ page }) => {
  test.setTimeout(60000);
  await historyApi(page);
  for (const name of ['مشتریان', 'مدل‌های دستگاه', 'کاربران', 'حساب‌های مشتریان', 'به‌روزرسانی‌ها']) {
    await page.getByRole('navigation', { name: 'منوی اصلی' }).getByRole('button', { name, exact: true }).click();
    await expect(page.getByRole('columnheader', { name: 'تاریخ ایجاد', exact: true })).toBeVisible();
    await expect(page.getByRole('columnheader', { name: 'آخرین ویرایش مدیریتی', exact: true })).toBeVisible();
    await expect(page.getByText('مدیر ثبت', { exact: true })).toBeVisible();
  }
  await expect(page.getByRole('columnheader', { name: 'پس‌گرفتن و انجام‌دهنده', exact: true })).toBeVisible();
  await expect(page.getByText('کارشناس پس‌گرفتن', { exact: true })).toBeVisible();
});

test('legacy archive metadata remains unknown instead of reusing the latest device update', async ({ page }) => {
  await historyApi(page, true);
  await page.getByRole('navigation', { name: 'منوی اصلی' }).getByRole('button', { name: 'دستگاه‌ها', exact: true }).click();
  await page.getByRole('combobox', { name: 'وضعیت بایگانی' }).selectOption('archived');
  await expect(page.getByRole('cell', { name: 'نامشخص', exact: true })).toBeVisible();
  await expect(page.getByRole('cell', { name: 'ثبت نشده', exact: true })).toBeVisible();
  await expect(page.getByText('عامل نامشخص', { exact: true })).toBeVisible();
});

test('operations are the final RTL column and use accessible icons across editable lists', async ({ page }) => {
  test.setTimeout(60000);
  await historyApi(page, false, true);
  for (const [menu, labels] of [
    ['دستگاه‌ها', ['ویرایش', 'شناسه', 'بایگانی']],
    ['مشتریان', ['ویرایش', 'بایگانی']],
    ['مدل‌های دستگاه', ['ویرایش مدل AD-UNIT-PC']],
    ['حساب‌های مشتریان', []],
    ['به‌روزرسانی‌ها', ['پس‌گرفتن', 'تخصیص بازگشت']],
  ]) {
    await page.getByRole('navigation', { name: 'منوی اصلی' }).getByRole('button', { name: menu, exact: true }).click();
    const table = page.locator('.live-table');
    await expect(table.locator('thead th').last()).toHaveText('عملیات');
    const actions = table.locator('tbody tr').first().locator('td').last();
    await expect(actions.locator('button').first()).toBeVisible();
    for (const label of labels) await expect(actions.getByRole('button', { name: label, exact: true })).toHaveCount(1);
    for (const button of await actions.locator('button').all()) {
      await expect(button).toHaveText('');
      await expect(button.locator('svg')).toHaveCount(1);
      const name = await button.getAttribute('aria-label');
      expect(name).toBeTruthy();
      await expect(button).toHaveAttribute('title', name);
      const box = await button.boundingBox();
      expect(box.width).toBeGreaterThanOrEqual(40);
      expect(box.height).toBeGreaterThanOrEqual(40);
      await button.focus();
      await expect(button).toBeFocused();
    }
    const geometry = await table.evaluate(element => {
      const headers = element.querySelectorAll('th');
      return { direction: getComputedStyle(element).direction, first: headers[0].getBoundingClientRect().x, last: headers[headers.length - 1].getBoundingClientRect().x };
    });
    expect(geometry.direction).toBe('rtl');
    expect(geometry.last).toBeLessThan(geometry.first);
    await expect(table.locator('time').first()).toHaveText('\u2066۱۴۰۴/۰۱/۰۱ ۰۰:۰۰:۰۰\u2069');
  }
});

test('icon actions remain reachable on mobile without widening the page', async ({ page }) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 390, height: 844 });
  await historyApi(page);
  await page.getByRole('button', { name: 'باز کردن منو' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'دستگاه‌ها', exact: true }).click();
  await expect(page.getByRole('button', { name: 'HISTORY-001', exact: true })).toBeVisible();
  await page.locator('.live-table-wrap').evaluate(element => { element.scrollLeft = -element.scrollWidth; });
  const edit = page.getByRole('button', { name: 'ویرایش', exact: true });
  await expect(edit).toBeInViewport();
  await expect(page.getByRole('button', { name: 'شناسه', exact: true })).toBeInViewport();
  await expect(page.getByRole('button', { name: 'بایگانی', exact: true })).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: '.local/list-ui-mobile.png' });
  await edit.click();
  await expect(page.getByRole('dialog')).toBeVisible();
});
