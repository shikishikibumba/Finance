// Firebase Web SDK initialization.
// API keys here are public — they identify the project, not authenticate it.
// Security is enforced by Firebase Auth + Firestore rules.

import { initializeApp, getApps, getApp } from "firebase/app";
import { getAuth, setPersistence, browserLocalPersistence } from "firebase/auth";

const firebaseConfig = {
  apiKey: process.env.REACT_APP_FIREBASE_API_KEY,
  authDomain: process.env.REACT_APP_FIREBASE_AUTH_DOMAIN,
  projectId: process.env.REACT_APP_FIREBASE_PROJECT_ID,
  storageBucket: process.env.REACT_APP_FIREBASE_STORAGE_BUCKET,
  messagingSenderId: process.env.REACT_APP_FIREBASE_MESSAGING_SENDER_ID,
  appId: process.env.REACT_APP_FIREBASE_APP_ID,
};

export const firebaseApp = getApps().length ? getApp() : initializeApp(firebaseConfig);
export const firebaseAuth = getAuth(firebaseApp);

// Persist auth state in localStorage so users stay logged in across reloads
// and across tabs. Works on every browser including iOS Safari.
setPersistence(firebaseAuth, browserLocalPersistence).catch((e) =>
  console.warn("Firebase auth persistence setup failed:", e)
);
