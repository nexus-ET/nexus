import axios from 'axios';
import { getStoredToken } from './utils/api';

const api = axios.create({
  // Clean pipeline mapping: Relies exclusively on your Vite environment configuration
  baseURL: import.meta.env.VITE_API_URL,
  headers: {
    'Content-Type': 'application/json',
    // ⚡ CRITICAL: Put this in common defaults so it's visible across all request footprints
    'ngrok-skip-browser-warning': 'true'
  }
});

// Automatically add JWT token and Ngrok bypass configurations to headers
api.interceptors.request.use((config) => {
  const token = getStoredToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  
  // Reinforce Ngrok bypass on the outgoing configuration context
  config.headers['ngrok-skip-browser-warning'] = 'true';
  
  return config;
}, (error) => {
  return Promise.reject(error);
});

// Debugging interceptor for 502/Proxy errors.
// Do not redirect to /login on 401/429 — telemetry and rate limits must not clear the session.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 502) {
      console.error("[NEXUS API] 502 Bad Gateway: Vite cannot reach the FastAPI data pipeline.");
      console.warn("Action Required: Verify that your configuration agent tunnel and Uvicorn server are active.");
    }
    if (!error.response) {
      console.error("[NEXUS API] Network Error: Backend might be down, tunnel expired, or blocked by CORS.");
    }
    return Promise.reject(error);
  }
);

// --- OAUTH2 AUTHENTICATION METHOD ---
export const login = (email, password) => {
  const formData = new URLSearchParams();
  formData.append('username', email); // OAuth2 expects 'username'
  formData.append('password', password);
  
  // Clean up content-type override specifically for urlencoded OAuth forms
  return api.post('/login', formData, {
    headers: {
      'Content-Type': 'application/x-www-form-urlencoded'
    }
  });
};

export const getClients = () => api.get('/clients/');
export const createClient = (data) => api.post('/clients/', data);

// --- 💡 THE MISSING CATCH: CENTRALIZED apiFetch ADAPTER WRAPPER ---
/**
 * Global dynamic fetch utility wrapper for Axios.
 * Matches standard fetch style requests while capitalizing on Axios request middleware interceptors.
 * * @param {string} url - The target endpoint context (e.g., 'analytics/summary')
 * @param {object} options - Configuration overrides (e.g., { method: 'POST', signal, body })
 */
export const apiFetch = async (url, options = {}) => {
  const { method = 'GET', signal, body, headers } = options;

  // Adapt native properties directly to standard Axios configurations
  const response = await api({
    url: url.startsWith('/') ? url : `/${url}`,
    method,
    signal, // 🎯 Safely catches and forwards the dashboard's AbortController signaling
    data: body,
    headers
  });

  // Extract Axios payload data directly to preserve Dashboard variable mappings
  return response.data;
};

export default api;