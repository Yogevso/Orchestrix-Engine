import { useEffect, useState } from "react";
import { api, Worker } from "../api";

export default function WorkersPage() {
  const [workers, setWorkers] = useState<Worker[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.listWorkers().then(setWorkers).finally(() => setLoading(false));
    const timer = setInterval(() => api.listWorkers().then(setWorkers), 5000);
    return () => clearInterval(timer);
  }, []);

  if (loading) return <p className="empty">Loading…</p>;

  return (
    <>
      <h2>Workers</h2>
      <div className="card">
        {workers.length === 0 ? (
          <p className="empty">No workers registered</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Status</th>
                <th>Queues</th>
                <th>Capabilities</th>
                <th>Concurrency</th>
                <th>Last Heartbeat</th>
              </tr>
            </thead>
            <tbody>
              {workers.map((w) => (
                <tr key={w.id}>
                  <td>{w.name}</td>
                  <td>
                    <span className={`badge badge-${w.status === "ACTIVE" ? "succeeded" : "failed"}`}>
                      {w.status}
                    </span>
                  </td>
                  <td>{w.queues.join(", ")}</td>
                  <td>{w.capabilities.length ? w.capabilities.join(", ") : "—"}</td>
                  <td>{w.max_concurrency}</td>
                  <td>{w.last_heartbeat_at ? new Date(w.last_heartbeat_at).toLocaleString() : "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </>
  );
}
