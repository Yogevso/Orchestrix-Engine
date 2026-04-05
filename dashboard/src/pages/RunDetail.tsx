import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { api, WorkflowRun } from "../api";

export default function RunDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchRun = () => {
    if (!runId) return;
    api.getRun(runId).then(setRun).finally(() => setLoading(false));
  };

  useEffect(() => {
    fetchRun();
    const timer = setInterval(fetchRun, 3000);
    return () => clearInterval(timer);
  }, [runId]);

  if (loading || !run) return <p className="empty">Loading…</p>;

  const handleCancel = async () => {
    await api.cancelRun(run.id);
    fetchRun();
  };

  const handleRetry = async (stepId: string) => {
    await api.retryStep(stepId);
    fetchRun();
  };

  return (
    <>
      <h2>Run {run.id.slice(0, 8)}</h2>
      <div className="stat-grid">
        <div className="stat-card">
          <div className="value">
            <span className={`badge badge-${run.status.toLowerCase()}`}>{run.status}</span>
          </div>
          <div className="label">Status</div>
        </div>
        <div className="stat-card">
          <div className="value">{run.steps.length}</div>
          <div className="label">Total Steps</div>
        </div>
        <div className="stat-card">
          <div className="value">{run.steps.filter((s) => s.status === "SUCCEEDED").length}</div>
          <div className="label">Succeeded</div>
        </div>
        <div className="stat-card">
          <div className="value">{run.steps.filter((s) => s.status === "FAILED").length}</div>
          <div className="label">Failed</div>
        </div>
      </div>

      {(run.status === "RUNNING" || run.status === "PENDING") && (
        <button onClick={handleCancel} style={{ marginBottom: "1rem", padding: "0.4rem 1rem", cursor: "pointer" }}>
          Cancel Run
        </button>
      )}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>Step</th>
              <th>Job Type</th>
              <th>Status</th>
              <th>Depends On</th>
              <th>Attempts</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {run.steps.map((s) => (
              <tr key={s.id}>
                <td>{s.step_name}</td>
                <td>{s.job_type}</td>
                <td>
                  <span className={`badge badge-${s.status.toLowerCase()}`}>{s.status}</span>
                </td>
                <td>{s.depends_on.length ? s.depends_on.join(", ") : "—"}</td>
                <td>
                  {s.attempts}/{s.max_attempts}
                </td>
                <td>
                  {s.status === "FAILED" && (
                    <button onClick={() => handleRetry(s.id)} style={{ cursor: "pointer" }}>
                      Retry
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {run.output && (
        <>
          <h2 style={{ marginTop: "1.5rem" }}>Output</h2>
          <div className="card">
            <pre style={{ whiteSpace: "pre-wrap", fontSize: "0.85rem" }}>
              {JSON.stringify(run.output, null, 2)}
            </pre>
          </div>
        </>
      )}
    </>
  );
}
