import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, Workflow, WorkflowRun } from "../api";

export default function WorkflowsPage() {
  const [workflows, setWorkflows] = useState<Workflow[]>([]);
  const [runs, setRuns] = useState<WorkflowRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([api.listWorkflows(), api.listRuns({ limit: "50" })])
      .then(([wfs, rs]) => {
        setWorkflows(wfs);
        setRuns(rs);
      })
      .finally(() => setLoading(false));

    const timer = setInterval(() => {
      api.listRuns({ limit: "50" }).then(setRuns);
    }, 5000);
    return () => clearInterval(timer);
  }, []);

  if (loading) return <p className="empty">Loading…</p>;

  return (
    <>
      <h2>Workflow Definitions</h2>
      <div className="card">
        {workflows.length === 0 ? (
          <p className="empty">No workflows defined</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Description</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {workflows.map((w) => (
                <tr key={w.id}>
                  <td>{w.name}</td>
                  <td>{w.description ?? "—"}</td>
                  <td>{new Date(w.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      <h2>Workflow Runs</h2>
      <div className="card">
        {runs.length === 0 ? (
          <p className="empty">No workflow runs</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Status</th>
                <th>Steps</th>
                <th>Started</th>
                <th>Finished</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => {
                const done = r.steps.filter(
                  (s) => s.status === "SUCCEEDED" || s.status === "FAILED" || s.status === "SKIPPED"
                ).length;
                return (
                  <tr key={r.id}>
                    <td>
                      <Link to={`/workflows/runs/${r.id}`}>{r.id.slice(0, 8)}</Link>
                    </td>
                    <td>
                      <span
                        className={`badge badge-${r.status.toLowerCase()}`}
                      >
                        {r.status}
                      </span>
                    </td>
                    <td>
                      {done}/{r.steps.length}
                    </td>
                    <td>{new Date(r.started_at).toLocaleString()}</td>
                    <td>{r.finished_at ? new Date(r.finished_at).toLocaleString() : "—"}</td>
                    <td>
                      <Link to={`/workflows/runs/${r.id}`}>View</Link>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
