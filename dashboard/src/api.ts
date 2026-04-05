const API_BASE = "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

export interface Job {
  id: string;
  type: string;
  queue_name: string;
  status: string;
  priority: number;
  payload: Record<string, unknown>;
  attempts: number;
  max_attempts: number;
  last_error: string | null;
  tenant_id: string | null;
  worker_id: string | null;
  created_at: string;
  updated_at: string;
}

interface JobListResponse {
  jobs: Job[];
  total: number;
}

export interface Worker {
  id: string;
  name: string;
  status: string;
  queues: string[];
  capabilities: string[];
  max_concurrency: number;
  last_heartbeat_at: string | null;
  running_count: number;
  created_at: string;
}

export interface WorkflowRun {
  id: string;
  workflow_id: string;
  status: string;
  tenant_id: string | null;
  started_at: string;
  finished_at: string | null;
  output: Record<string, unknown> | null;
  steps: WorkflowStep[];
}

export interface WorkflowStep {
  id: string;
  step_name: string;
  job_type: string;
  status: string;
  attempts: number;
  max_attempts: number;
  depends_on: string[];
  result: Record<string, unknown> | null;
}

export interface Workflow {
  id: string;
  name: string;
  description: string | null;
  tenant_id: string | null;
  created_at: string;
}

export const api = {
  // Jobs
  listJobs: async (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    const resp = await request<JobListResponse>(`/jobs${qs}`);
    return resp.jobs;
  },

  // Workers
  listWorkers: () => request<Worker[]>("/workers"),

  // Workflows
  listWorkflows: () => request<Workflow[]>("/workflows"),
  listRuns: (params?: Record<string, string>) => {
    const qs = params ? "?" + new URLSearchParams(params).toString() : "";
    return request<WorkflowRun[]>(`/workflows/runs${qs}`);
  },
  getRun: (id: string) => request<WorkflowRun>(`/workflows/runs/${id}`),
  cancelRun: (id: string) => request<WorkflowRun>(`/workflows/runs/${id}/cancel`, { method: "POST" }),
  retryStep: (id: string) => request<WorkflowStep>(`/workflows/steps/${id}/retry`, { method: "POST" }),
};
