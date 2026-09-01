import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Sidebar } from "@/components/Sidebar";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import Inventory from "@/pages/Inventory";
import DnsRecords from "@/pages/DnsRecords";
import Generator from "@/pages/Generator";
import Kubernetes from "@/pages/Kubernetes";
import DbConfig from "@/pages/DbConfig";
import Team from "@/pages/Team";
import { Loader2 } from "lucide-react";

const Shell = ({ children }) => (
  <>
    <Sidebar />
    <main className="ml-60 min-h-screen">{children}</main>
  </>
);

const Protected = ({ children }) => {
  const { user } = useAuth();
  if (user === null)
    return (
      <div className="min-h-screen flex items-center justify-center bg-[#09090B]">
        <Loader2 className="h-6 w-6 text-orange-500 animate-spin" />
      </div>
    );
  if (user === false) return <Navigate to="/login" replace />;
  return <Shell>{children}</Shell>;
};

const PublicOnly = ({ children }) => {
  const { user } = useAuth();
  if (user && user !== false) return <Navigate to="/" replace />;
  return children;
};

function App() {
  return (
    <div className="App dark">
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<PublicOnly><Login /></PublicOnly>} />
            <Route path="/" element={<Protected><Dashboard /></Protected>} />
            <Route path="/inventory" element={<Protected><Inventory /></Protected>} />
            <Route path="/dns" element={<Protected><DnsRecords /></Protected>} />
            <Route path="/generator" element={<Protected><Generator /></Protected>} />
            <Route path="/kubernetes" element={<Protected><Kubernetes /></Protected>} />
            <Route path="/db-config" element={<Protected><DbConfig /></Protected>} />
            <Route path="/team" element={<Protected><Team /></Protected>} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
      <Toaster theme="dark" position="bottom-right" richColors />
    </div>
  );
}

export default App;
