import { test, expect } from '@playwright/test';

const organization = { id: 1, name: 'سازمان مشتری آزمایشی' };
const device = { id: 11, serial_number: 'OWN-011', model_name: 'PX-500', software_version: '2.4.1',
  location: 'تهران', last_seen_at: null, is_online: false };

async function customerApi(page) {
  const requests = [];
  let signedIn = true;
  await page.route('**/api/v1/**', async route => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    if (path.endsWith('/auth/csrf/')) return route.fulfill({ json: { csrfToken: 'customer-test-csrf' } });
    if (path.endsWith('/auth/logout/')) { signedIn = false; return route.fulfill({ status: 204 }); }
    if (!signedIn) return route.fulfill({ status: 403, json: { detail: 'Session expired' } });
    if (path.endsWith('/auth/session/')) return route.fulfill({ json: { role: 'customer', email: 'customer@example.test', organization } });
    if (path.endsWith('/customer/summary/')) return route.fulfill({ json: { device_count: 1, online_count: 0, offline_count: 1,
      generated_at: new Date().toISOString(), online_window_minutes: 7 } });
    if (path.endsWith('/customer/devices/')) return route.fulfill({ json: { count: 1, results: [device], next: null, previous: null } });
    if (path.endsWith('/customer/devices/11/')) return route.fulfill({ json: device });
    return route.fulfill({ status: 404, json: { detail: 'Not found.' } });
  });
  return requests;
}

test('customer session enters scoped panel, supports direct details/back and never calls staff APIs', async ({ page }) => {
  const requests = await customerApi(page);
  await page.goto('/staff/users');
  await expect(page.getByRole('heading', { name: 'دستگاه‌های من' })).toBeVisible();
  await expect(page).toHaveURL(/\/customer\/devices$/);
  await expect(page.getByRole('link', { name: 'OWN-011' })).toBeVisible();
  await expect(page.getByText('هنوز ارتباطی ثبت نشده است').first()).toBeVisible();
  await expect(page.locator('.live-footer')).toContainText('۷');
  await expect(page.getByRole('button', { name: 'کاربران', exact: true })).toHaveCount(0);
  await page.getByRole('link', { name: 'OWN-011' }).click();
  await expect(page).toHaveURL(/\/customer\/devices\/11$/);
  await expect(page.getByRole('heading', { name: 'OWN-011' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: 'OWN-011' })).toBeVisible();
  await page.getByRole('button', { name: 'بازگشت به دستگاه‌ها' }).click();
  await expect(page.getByRole('link', { name: 'OWN-011' })).toBeVisible();
  expect(requests.every(path => path.startsWith('/api/v1/auth/') || path.startsWith('/api/v1/customer/'))).toBeTruthy();
});

test('customer mobile drawer, keyboard dismissal and theme persist', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await customerApi(page);
  await page.goto('/customer/devices');
  await expect(page.getByRole('link', { name: 'OWN-011' })).toBeVisible();
  await page.getByRole('button', { name: 'باز کردن منو' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'باز کردن منو' })).toBeFocused();
  await page.getByRole('button', { name: 'تغییر پوسته' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await page.reload();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.locator('.customer-panel')).toHaveAttribute('dir', 'rtl');
});

test('foreign or reassigned detail clears protected data after refresh', async ({ page }) => {
  await customerApi(page);
  await page.goto('/customer/devices/11');
  await expect(page.getByRole('heading', { name: 'OWN-011' })).toBeVisible();
  await page.route('**/customer/devices/11/', route => route.fulfill({ status: 404, json: { detail: 'Not found.' } }));
  await page.getByRole('button', { name: 'بازخوانی' }).click();
  await expect(page.getByRole('alert')).toContainText('دستگاه در دسترس نیست');
  await expect(page.getByRole('heading', { name: 'OWN-011' })).toHaveCount(0);
});

test('customer outage differs from empty fleet and never falls back to demo records', async ({ page }) => {
  await customerApi(page);
  await page.route('**/customer/devices/?*', route => route.fulfill({ status: 503, json: { detail: 'Unavailable' } }));
  await page.goto('/customer/devices');
  await expect(page.getByRole('alert')).toContainText('دریافت اطلاعات انجام نشد');
  await expect(page.getByText('هنوز دستگاهی به سازمان شما اختصاص داده نشده است.')).toHaveCount(0);
  await expect(page.getByRole('link', { name: 'OWN-011' })).toHaveCount(0);
});

test('customer expiry and logout clear identity data and browser back cannot restore a panel', async ({ page }) => {
  await customerApi(page);
  await page.goto('/customer/devices');
  await expect(page.getByRole('link', { name: 'OWN-011' })).toBeVisible();
  await page.getByRole('button', { name: 'خروج', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await expect(page.getByText(organization.name)).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'OWN-011' })).toHaveCount(0);
});

test('an expired customer session on refresh returns to shared login', async ({ page }) => {
  await customerApi(page);
  await page.goto('/customer/devices');
  await expect(page.getByRole('link', { name: 'OWN-011' })).toBeVisible();
  await page.route('**/auth/session/', route => route.fulfill({ status: 403, json: { detail: 'Session expired' } }));
  await page.getByRole('button', { name: 'بازخوانی' }).click();
  await expect(page.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('نشست شما پایان یافته');
  await expect(page.getByRole('link', { name: 'OWN-011' })).toHaveCount(0);
});

test('changed organization cannot reuse the previous customer view', async ({ page }) => {
  await customerApi(page);
  await page.goto('/customer/devices');
  await expect(page.getByRole('link', { name: 'OWN-011' })).toBeVisible();
  await page.route('**/auth/session/', route => route.fulfill({ json: { role: 'customer', email: 'customer@example.test',
    organization: { id: 2, name: 'Different organization' } } }));
  await page.getByRole('button', { name: 'بازخوانی' }).click();
  await expect(page.getByRole('heading', { name: 'ورود به سامانه' })).toBeVisible();
  await expect(page.getByRole('link', { name: 'OWN-011' })).toHaveCount(0);
});

test('administrator creates and deactivates a customer account through the application', async ({ page }) => {
  let account;
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), path = new URL(request.url()).pathname;
    if (path.endsWith('/auth/session/')) return route.fulfill({ json: { role: 'super_admin', email: 'admin@example.test' } });
    if (path.endsWith('/auth/csrf/')) return route.fulfill({ json: { csrfToken: 'test-csrf' } });
    if (path.endsWith('/customers/')) return route.fulfill({ json: { count: 1, results: [{ id: 1, organization_name: organization.name }] } });
    if (path.includes('/customer-users/')) {
      if (request.method() === 'POST') {
        const submitted = request.postDataJSON();
        expect(submitted.customer).toBe(1);
        expect(submitted.role).toBeUndefined();
        account = { id: 5, email: submitted.email, organization, is_active: true };
        return route.fulfill({ status: 201, json: account });
      }
      if (request.method() === 'PATCH') { account.is_active = request.postDataJSON().is_active; return route.fulfill({ json: account }); }
      return route.fulfill({ json: { count: account ? 1 : 0, results: account ? [account] : [], next: null, previous: null } });
    }
    return route.fulfill({ json: { count: 0, results: [], next: null, previous: null } });
  });
  await page.goto('/');
  await page.getByRole('navigation').getByRole('button', { name: 'حساب‌های مشتریان' }).click();
  await page.getByRole('button', { name: 'افزودن حساب مشتری', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('ایمیل', { exact: true }).fill('new@example.test');
  await dialog.getByLabel('گذرواژهٔ اولیه').fill('Correct-Horse-42!');
  await dialog.getByLabel('سازمان مشتری', { exact: true }).selectOption('1');
  await dialog.getByRole('button', { name: 'افزودن حساب مشتری', exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole('cell', { name: 'new@example.test', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'غیرفعال‌کردن new@example.test', exact: true }).click();
  await expect(page.getByRole('cell', { name: 'غیرفعال', exact: true })).toBeVisible();
});
