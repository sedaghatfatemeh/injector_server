import { shellText } from './locale.js';

const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

let csrfToken = '';

function cookie(name) {
  return document.cookie.split('; ').find((part) => part.startsWith(`${name}=`))?.slice(name.length + 1) || '';
}

async function request(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const headers = new Headers(options.headers || {});
  if (options.body) headers.set('Content-Type', 'application/json');
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    csrfToken = decodeURIComponent(cookie('csrftoken')) || csrfToken;
    if (csrfToken) headers.set('X-CSRFToken', csrfToken);
  }
  const response = await fetch(`${API_BASE}${path}`, { ...options, method, headers, credentials: 'include' });
  if (response.status === 204) return null;
  const payload = await response.json().catch(() => null);
  if (response.ok && (!response.headers.get('Content-Type')?.includes('application/json') || payload === null)) {
    throw new Error(shellText.connectionError);
  }
  if (!response.ok) {
    const detail = payload?.detail || Object.values(payload || {}).flat().join(' ') || shellText.connectionError;
    const error = new Error(detail);
    error.status = response.status;
    error.data = payload;
    throw error;
  }
  return payload;
}

export const api = {
  request,
  deviceModels: async (params = {}) => {
    const all = [];
    let url = `/api/v1/device-models/?${new URLSearchParams(params)}`;
    while (url) {
      const data = await request(url);
      all.push(...(Array.isArray(data) ? data : data.results || []));
      const next = data.next ? new URL(data.next, window.location.origin) : null;
      url = next ? next.pathname + next.search : null;
    }
    return all;
  },
  createDeviceModel: data => request('/api/v1/device-models/', { method: 'POST', body: JSON.stringify(data) }),
  updateDeviceModel: (id, data) => request(`/api/v1/device-models/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  csrf: async () => { const result = await request('/api/v1/auth/csrf/'); csrfToken = result.csrfToken; return result; },
  login: (email, password) => request('/api/v1/auth/login/', { method: 'POST', body: JSON.stringify({ email, password }) }),
  logout: () => request('/api/v1/auth/logout/', { method: 'POST', body: '{}' }),
  session: (options = {}) => request('/api/v1/auth/session/', options),
  staffUsers: (params = {}, options = {}) => request(`/api/v1/staff-users/?${new URLSearchParams(params)}`, options),
  createStaffUser: (data) => request('/api/v1/staff-users/', { method: 'POST', body: JSON.stringify(data) }),
  summary: () => request('/api/v1/dashboard/summary/'),
  devices: (params = {}) => request(`/api/v1/devices/?${new URLSearchParams(params)}`),
  events: (params = {}, options = {}) => request(`/api/v1/events/?${new URLSearchParams(params)}`, options),
  customers: (params = {}, options = {}) => request(`/api/v1/customers/?${new URLSearchParams(params)}`, options),
  customerUsers: (params = {}, options = {}) => request(`/api/v1/customer-users/?${new URLSearchParams(params)}`, options),
  createCustomerUser: (data) => request('/api/v1/customer-users/', { method: 'POST', body: JSON.stringify(data) }),
  setCustomerUserActive: (id, is_active) => request(`/api/v1/customer-users/${id}/`, { method: 'PATCH', body: JSON.stringify({ is_active }) }),
  customerDevices: (params = {}, options = {}) => request(`/api/v1/customer/devices/?${new URLSearchParams(params)}`, options),
  customerDevice: (id, options = {}) => request(`/api/v1/customer/devices/${encodeURIComponent(id)}/`, options),
  customerSummary: (options = {}) => request('/api/v1/customer/summary/', options),
  releases: (params = {}) => request(`/api/v1/releases/?${new URLSearchParams(params)}`),
  createCustomer: (data) => request('/api/v1/customers/', { method: 'POST', body: JSON.stringify(data) }),
  updateCustomer: (id, data) => request(`/api/v1/customers/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  archiveCustomer: (id) => request(`/api/v1/customers/${id}/`, { method: 'DELETE' }),
  createDevice: (data) => request('/api/v1/devices/', { method: 'POST', body: JSON.stringify(data) }),
  updateDevice: (id, data) => request(`/api/v1/devices/${id}/`, { method: 'PATCH', body: JSON.stringify(data) }),
  archiveDevice: (id) => request(`/api/v1/devices/${id}/`, { method: 'DELETE' }),
  provisionDevice: (id) => request(`/api/v1/devices/${id}/provision_credential/`, { method: 'POST', body: '{}' }),
  createRelease: (data) => request('/api/v1/releases/', { method: 'POST', body: JSON.stringify(data) }),
  assignments: (params = {}) => request(`/api/v1/releases/assignments/?${new URLSearchParams(params)}`),
  withdrawRelease: (id) => request(`/api/v1/releases/${id}/withdraw/`, { method: 'POST', body: '{}' }),
  rollbackRelease: (id, data) => request(`/api/v1/releases/${id}/rollback/`, { method: 'POST', body: JSON.stringify(data) }),
};
