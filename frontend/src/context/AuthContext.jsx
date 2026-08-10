import { createContext, useContext, useEffect, useState } from "react";
import * as api from "@/lib/api";

const AuthContext = createContext(null);
export const useAuth = () => useContext(AuthContext);

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null); // null=checking, false=anon, obj=authed

  useEffect(() => {
    const token = localStorage.getItem("if_token");
    if (!token) {
      setUser(false);
      return;
    }
    api.me().then(setUser).catch(() => setUser(false));
  }, []);

  const signIn = async (email, password) => {
    const data = await api.login(email, password);
    localStorage.setItem("if_token", data.access_token);
    setUser(data.user);
    return data.user;
  };

  const signOut = async () => {
    try { await api.logout(); } catch (_) {}
    localStorage.removeItem("if_token");
    setUser(false);
  };

  return (
    <AuthContext.Provider value={{ user, signIn, signOut, setUser }}>
      {children}
    </AuthContext.Provider>
  );
};
