import "@/App.css";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import { Sidebar } from "@/components/Sidebar";
import Dashboard from "@/pages/Dashboard";
import Inventory from "@/pages/Inventory";
import DnsRecords from "@/pages/DnsRecords";
import Generator from "@/pages/Generator";

function App() {
  return (
    <div className="App dark">
      <BrowserRouter>
        <Sidebar />
        <main className="ml-60 min-h-screen">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/inventory" element={<Inventory />} />
            <Route path="/dns" element={<DnsRecords />} />
            <Route path="/generator" element={<Generator />} />
          </Routes>
        </main>
      </BrowserRouter>
      <Toaster theme="dark" position="top-right" richColors />
    </div>
  );
}

export default App;
