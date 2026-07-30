import axios from "axios";
import { firebaseAuth } from "@/lib/firebase";

const API = axios.create({
  baseURL: `${process.env.REACT_APP_BACKEND_URL}/api`,
  headers: { "Content-Type": "application/json" },
});

// Attach a fresh Firebase ID token on every request.
// getIdToken() returns a cached token until it's near expiry, then auto-refreshes.
API.interceptors.request.use(async (config) => {
  const user = firebaseAuth.currentUser;
  if (user) {
    try {
      const token = await user.getIdToken();
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    } catch (e) {
      console.warn("Failed to attach Firebase ID token:", e);
    }
  }
  return config;
});

API.interceptors.response.use(
  (res) => res,
  async (err) => {
    if (err.response?.status === 401) {
      // Token rejected — sign out client-side so AuthProvider redirects to login.
      try { await firebaseAuth.signOut(); } catch { /* ignore */ }
      const path = window.location.pathname;
      if (path !== "/login") window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export default API;
