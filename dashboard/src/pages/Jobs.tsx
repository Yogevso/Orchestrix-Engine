import { useEffect, useState } from "react";
import { api, Job } from "../api";

export default function JobsPage() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listJobs({ limit: "100" }).then(setJobs).finally(() => setLoading(false));
    const timer = setInterval(() => api.listJobs({ limit: "100" }).then(setJobs), 5000);
    return () => clearInterval(timer);
  }, []);

  const counts = jobs.reduce<Record<string, number>>((acc, j) => {
    acc[j.status] = (acc[j.status] || 0) + 1;
    return acc;
  }, {});

  if (loading) return <p className="empty">Loading…</p>;

  return (
    <>
      <h2>Jobs</h2>
      <div className="stat-grid">
        {["QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "DEAD_LETTER"].map((s) => (
          <div className="stat-card" key={s}>
            <div className="value">{counts[s] ?? 0}</div>
            <div className="label">{s}</div>
          </div>
        ))}
      </div>
      <div className="card">
        {jobs.length === 0 ? (
          <p className="empty">No jobs yet</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Queue</th>
                <th>Status</th>
                <th>Priority</th>
                <th>Attempts</th>
                <th>Worker</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((j) => (
                <tr key={j.id}>
                  <td title={j.id}>{j.id.slice(0, 8)}</td>
                  <td>{j.type}</td>
                  <td>{j.queue_name}</td>
                  <td>
                    <span className={`badge badge-${j.status.toLowerCase()}`}>{j.status}</span>
                  </td>
                  <td>{j.priority}</td>
                  <td>
                    {j.attempts}/{j.max_attempts}
                  </td>
                  <td>{j.worker_id ? j.worker_id.slice(0, 8) : "—"}</td>
                  <td>{new Date(j.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
