import { BrowserRouter, Routes, Route } from "react-router-dom";
import AgentList from "./components/AgentList";
import AgentDetail from "./components/AgentDetail";

export default function App() {
  return (
    <BrowserRouter>
      <div className="min-h-screen">
        <header className="border-b border-gray-800 bg-gray-900/60 backdrop-blur sticky top-0 z-10">
          <div className="max-w-6xl mx-auto px-6 py-4 flex items-center gap-3">
            <div className="h-8 w-8 rounded-lg bg-indigo-600 flex items-center justify-center text-sm font-bold">
              AD
            </div>
            <h1 className="text-lg font-semibold tracking-tight">
              Agent Discovery
            </h1>
          </div>
        </header>
        <main className="max-w-6xl mx-auto px-6 py-8">
          <Routes>
            <Route path="/" element={<AgentList />} />
            <Route path="/agents/:id" element={<AgentDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}
