import { createContext, useContext, useState, useEffect, useCallback } from "react";
import { onAuthStateChanged, signInWithEmailAndPassword, signOut } from "firebase/auth";
import { firebaseAuth } from "@/lib/firebase";
import API from "@/lib/api";

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  // user states:
  //   null   — initial (still checking)
  //   false  — signed out
  //   object — signed in profile { id, email, name, role }
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = useCallback(async () => {
    try {
      const { data } = await API.get("/auth/me");
      setUser(data);
    } catch (e) {
      console.error("Failed to fetch profile:", e?.response?.status, e?.response?.data);
      setUser(false);
    }
  }, []);

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(firebaseAuth, async (fbUser) => {
      if (fbUser) {
        await fetchProfile();
      } else {
        setUser(false);
      }
      setLoading(false);
    });
    return unsubscribe;
  }, [fetchProfile]);

  const login = async (email, password) => {
    await signInWithEmailAndPassword(firebaseAuth, email.trim(), password);
    // onAuthStateChanged will fire and populate `user`
  };

  const logout = async () => {
    try { await signOut(firebaseAuth); } catch { /* ignore */ }
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, loading, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be inside AuthProvider");
  return ctx;
}
