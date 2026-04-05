import { Routes, Route, NavLink } from "react-router-dom";
import JobsPage from "./pages/Jobs";
import WorkersPage from "./pages/Workers";
import WorkflowsPage from "./pages/Workflows";
import RunDetailPage from "./pages/RunDetail";

function App() {
  return (
    <div className="layout">
      <nav className="sidebar">
        <h1>Orchestrix</h1>
        <NavLink to="/" end>
          Jobs
        </NavLink>
        <NavLink to="/workers">Workers</NavLink>
        <NavLink to="/workflows">Workflows</NavLink>
      </nav>
      <main className="content">
        <Routes>
          <Route path="/" element={<JobsPage />} />
          <Route path="/workers" element={<WorkersPage />} />
          <Route path="/workflows" element={<WorkflowsPage />} />
          <Route path="/workflows/runs/:runId" element={<RunDetailPage />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
