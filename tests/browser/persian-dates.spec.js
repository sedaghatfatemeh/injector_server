import { test, expect } from '@playwright/test';

test.use({ timezoneId: 'America/Los_Angeles' });

async function calendarApi(page) {
  await page.route(/https:\/\/fonts\.(googleapis|gstatic)\.com\/.*/, route => route.abort());
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url());
    let json = { count: 0, results: [], next: null, previous: null };
    if (url.pathname.endsWith('/auth/csrf/')) json = { csrfToken: 'test-csrf' };
    if (url.pathname.endsWith('/auth/session/')) json = { role: 'super_admin', email: 'admin@example.test' };
    if (url.pathname.endsWith('/dashboard/summary/')) json = { generated_at: '2025-03-20T20:30:00Z', device_count: 0 };
    if (url.pathname.endsWith('/events/')) json = { count: 51, next: '?page=2', previous: null, results: [{ id: 1, code: 'LOG', state: 'info', occurred_at: '2025-03-20T20:30:00Z', received_at: '2025-03-20T21:35:00Z' }] };
    return route.fulfill({ json });
  });
  await page.goto('/', { waitUntil: 'domcontentloaded' });
  if (page.viewportSize().width <= 700) await page.getByRole('button', { name: 'باز کردن منو' }).click();
  await page.getByRole('navigation', { name: 'منوی اصلی' }).getByRole('button', { name: 'رویدادها و خطاها', exact: true }).click();
}

test('Persian bounds convert to UTC Tehran instants and survive pagination with archive flags', async ({ page }) => {
  test.setTimeout(60000);
  await calendarApi(page);
  const region = page.getByRole('region', { name: 'تاریخچه رویدادها' });
  await expect(region.getByRole('cell', { name: /۱۴۰۴\/۰۱\/۰۱.*۰۰:۰۰/ })).toBeVisible();
  await expect(region.getByRole('cell', { name: /۱۴۰۴\/۰۱\/۰۱.*۰۱:۰۵/ })).toBeVisible();
  await page.getByLabel('زمان وقوع از', { exact: true }).fill('۱۴۰۴/۰۱/۰۱ ۰۰:۰۰:۰۰');
  await page.getByLabel('زمان وقوع تا', { exact: true }).fill('1404/01/02 12:00:00');
  await page.getByRole('checkbox', { name: 'شامل دستگاه‌های بایگانی‌شده' }).check();
  const pending = page.waitForRequest(request => new URL(request.url()).searchParams.has('occurred_after'));
  await page.getByRole('button', { name: 'اعمال فیلترها' }).click();
  const url = new URL((await pending).url());
  expect(url.searchParams.get('occurred_after')).toBe('2025-03-20T20:30:00.000Z');
  expect(url.searchParams.get('occurred_before')).toBe('2025-03-22T08:30:00.000Z');
  expect(url.searchParams.get('device__is_archived')).toBe('true');
  const next = page.waitForRequest(request => new URL(request.url()).searchParams.get('page') === '2');
  await region.getByRole('button', { name: 'صفحه بعد' }).click();
  expect(new URL((await next).url()).searchParams.get('occurred_after')).toBe('2025-03-20T20:30:00.000Z');
});

test('invalid leap dates and reversed ranges remain visible validation errors', async ({ page }) => {
  await calendarApi(page);
  await page.getByLabel('زمان وقوع از', { exact: true }).fill('1404/12/30');
  await page.getByRole('button', { name: 'اعمال فیلترها' }).click();
  await expect(page.getByRole('alert')).toContainText('معتبر نیست');
  await page.getByLabel('زمان وقوع از', { exact: true }).fill('1404/01/02');
  await page.getByLabel('زمان وقوع تا', { exact: true }).fill('1404/01/01');
  await page.getByRole('button', { name: 'اعمال فیلترها' }).click();
  await expect(page.getByRole('alert')).toContainText('زمان شروع');
  await page.getByRole('button', { name: 'پاک کردن فیلترها' }).click();
  await expect(page.getByLabel('زمان وقوع از', { exact: true })).toHaveValue('');
});

test('mobile Persian month grid supports keyboard selection, leap day and Escape', async ({ page }) => {
  test.setTimeout(60000);
  await page.setViewportSize({ width: 390, height: 844 });
  await calendarApi(page);
  const field = page.getByLabel('زمان وقوع از', { exact: true });
  await field.fill('1403/12/29 12:30:00');
  const toggle = page.getByRole('button', { name: 'انتخاب تاریخ زمان وقوع از', exact: true });
  await toggle.click();
  const calendar = page.getByRole('region', { name: 'تقویم شمسی زمان وقوع از' });
  await expect(calendar).toBeVisible();
  await expect(calendar.getByRole('button', { name: '۲۹ اسفند ۱۴۰۳', exact: true })).toBeFocused();
  await page.keyboard.press('ArrowLeft');
  await expect(calendar.getByRole('button', { name: '۳۰ اسفند ۱۴۰۳', exact: true })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(field).toHaveValue('۱۴۰۳/۱۲/۳۰ ۱۲:۳۰:۰۰');
  await expect(toggle).toBeFocused();
  await toggle.click();
  await page.keyboard.press('Escape');
  await expect(calendar).toHaveCount(0);
  await expect(toggle).toBeFocused();
  await page.getByLabel('زمان وقوع تا', { exact: true }).fill('1404/01/01');
  await page.getByRole('button', { name: 'انتخاب تاریخ زمان وقوع تا', exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 320, height: 700 });
  await page.getByRole('button', { name: 'انتخاب تاریخ زمان وقوع تا', exact: true }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

for (const viewport of [{ width: 1366, height: 608 }, { width: 1366, height: 768 }, { width: 390, height: 700 }, { width: 320, height: 568 }]) {
  test(`calendar stays fully inside ${viewport.width}x${viewport.height} viewport`, async ({ page }) => {
    test.setTimeout(60000);
    await page.setViewportSize(viewport);
    await calendarApi(page);
    await page.getByLabel('زمان وقوع از', { exact: true }).fill('1405/01/06 12:30:00');
    await page.getByRole('button', { name: 'انتخاب تاریخ زمان وقوع از', exact: true }).click();
    const calendar = page.getByRole('region', { name: 'تقویم شمسی زمان وقوع از' });
    await expect(calendar).toBeVisible();
    const box = await calendar.boundingBox();
    expect(box.width).toBeLessThanOrEqual(305);
    expect(box.x).toBeGreaterThanOrEqual(7);
    expect(box.y).toBeGreaterThanOrEqual(7);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width - 7);
    expect(box.y + box.height).toBeLessThanOrEqual(viewport.height - 7);
    await expect(calendar.getByRole('button', { name: 'بستن تقویم', exact: true })).toBeInViewport();
    const day = await calendar.locator('[data-day="1"]').boundingBox();
    expect(day.height).toBeGreaterThanOrEqual(40);
    expect(day.height).toBeLessThan(42);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    if (viewport.width === 1366 && viewport.height === 608) await page.screenshot({ path: '.local/calendar-1366x608.png', fullPage: false });
  });
}
