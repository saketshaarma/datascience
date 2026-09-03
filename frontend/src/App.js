import "@/App.css";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "@/context/AuthContext";
import { Sidebar } from "@/components/Sidebar";
import Login from "@/pages/Login";
import Dashboard from "@/pages/Dashboard";
import DbConfig from "@/pages/DbConfig";
import Kubernetes from "@/pages/Kubernetes";
import Workloads from "@/pages/Workloads";
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
            <Route path="/db-config" element={<Protected><DbConfig /></Protected>} />
            <Route path="/kubernetes" element={<Protected><Kubernetes /></Protected>} />
            <Route path="/workloads" element={<Protected><Workloads /></Protected>} />
            <Route path="/team" element={<Protected><Team /></Protected>} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
      <Toaster theme="dark" position="bottom-right" richColors />
    </div>
  );
}

export default App;
