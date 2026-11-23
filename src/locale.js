// Keep shell copy and formatting behind one locale boundary for future languages.
export const locale = 'fa-IR';
export const shellText = {
  close: 'بستن',
  navigation: 'منوی اصلی',
  openNavigation: 'باز کردن منو',
  skipNavigation: 'رفتن به محتوای اصلی',
  overview: 'نمای کلی',
  devices: 'دستگاه‌ها',
  customers: 'مشتریان',
  events: 'رویدادها و خطاها',
  releases: 'به‌روزرسانی‌ها',
  users: 'کاربران',
  customerUsers: 'حساب‌های مشتریان',
  restoringSession: 'در حال بررسی نشست…',
  loading: 'در حال دریافت اطلاعات…',
  connectionError: 'ارتباط با سامانه برقرار نشد. اتصال را بررسی و دوباره تلاش کنید.',
};

export const customerAccountText = {
  title: 'حساب‌های مشتریان', description: 'فقط مدیر کل حساب مشتری را ایجاد و به یک سازمان متصل می‌کند.',
  add: 'افزودن حساب مشتری', email: 'ایمیل', first_name: 'نام', last_name: 'نام خانوادگی',
  password: 'گذرواژهٔ اولیه', customer: 'سازمان مشتری', organizationSearch: 'جست‌وجوی سازمان',
  choose: 'انتخاب سازمان', status: 'وضعیت', active: 'فعال', inactive: 'غیرفعال',
  deactivate: 'غیرفعال‌کردن', activate: 'فعال‌کردن', cancel: 'انصراف', refresh: 'بازخوانی',
  loading: 'در حال دریافت حساب‌ها…', saving: 'در حال ذخیره…', empty: 'حساب مشتری ثبت نشده است.',
  noOrganizations: 'سازمانی یافت نشد؛ ابتدا مشتری را ثبت کنید یا عبارت جست‌وجو را تغییر دهید.',
  created: 'حساب مشتری ایجاد شد؛ گذرواژهٔ اولیه را از مسیر امن به مشتری تحویل دهید.',
  changed: 'وضعیت حساب تغییر کرد.', error: 'عملیات انجام نشد. دوباره تلاش کنید.',
  passwordHint: 'حداقل ۸ نویسه؛ از گذرواژهٔ رایج یا مشابه نام و ایمیل استفاده نکنید. گذرواژه در فهرست نمایش داده نمی‌شود.',
  archived: 'سازمان بایگانی شده است', previous: 'قبلی', next: 'بعدی', accountSearch: 'جست‌وجوی حساب یا سازمان',
};

export const customerText = {
  title: 'دستگاه‌های من', detail: 'جزئیات دستگاه', panel: 'پنل مشتری', organization: 'سازمان',
  serial: 'شماره سریال', model: 'مدل', version: 'نسخهٔ برنامه', location: 'محل نصب',
  connection: 'وضعیت تخمینی اتصال', lastSeen: 'آخرین ارتباط موفق', never: 'هنوز ارتباطی ثبت نشده است',
  online: 'ارتباط اخیر', offline: 'ارتباط اخیر ثبت نشده', total: 'دستگاه‌های سازمان',
  search: 'جست‌وجوی سریال یا مدل', filter: 'وضعیت اتصال', all: 'همه',
  empty: 'هنوز دستگاهی به سازمان شما اختصاص داده نشده است.', noMatches: 'دستگاهی با این جست‌وجو یا فیلتر یافت نشد.',
  clear: 'پاک‌کردن جست‌وجو و فیلتر', unavailable: 'دستگاه در دسترس نیست یا دیگر به سازمان شما اختصاص ندارد.',
  error: 'دریافت اطلاعات انجام نشد. برای تلاش دوباره بازخوانی کنید.',
  refresh: 'بازخوانی', logout: 'خروج', theme: 'تغییر پوسته', back: 'بازگشت به دستگاه‌ها',
  previous: 'قبلی', next: 'بعدی', loading: 'در حال دریافت دستگاه‌ها…', updated: 'آخرین بازخوانی',
  stale: 'اطلاعات تازه نیست؛ برای دریافت وضعیت فعلی بازخوانی کنید.',
  estimate: 'وضعیت اتصال تخمینی است و بر اساس آخرین ارتباط موفق و آستانهٔ', minutes: 'دقیقه محاسبه می‌شود.',
  safety: 'این صفحه امکان برقراری اتصال یا کنترل دستگاه و آزمون را ندارد.',
  page: 'صفحهٔ', detailsLink: 'مشاهدهٔ دستگاه',
};

export function readTheme() {
  try { return localStorage.getItem('injector-theme') === 'dark' ? 'dark' : 'light'; }
  catch { return 'light'; }
}

export function rememberTheme(theme) {
  document.documentElement.dataset.theme = theme;
  try { localStorage.setItem('injector-theme', theme); }
  catch { /* A disabled browser store must not prevent staff access. */ }
}
