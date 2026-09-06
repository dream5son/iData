const API_BASE = process.env.NEXT_PUBLIC_IDI_API_BASE ?? "http://127.0.0.1:8000";

export type DataSource = {
  id: string;
  name: string;
  dialect: string;
  params: Record<string, unknown>;
  readonly_intent: boolean;
  status: "draft" | "test_failed" | "ready" | "disabled";
  created_at: string;
  updated_at: string;
  last_tested_at: string | null;
  last_test: {
    overall_passed: boolean;
    tested_at: string;
    steps: { name: string; outcome: string; message: string }[];
  } | null;
  current_snapshot_version: number | null;
  sync_enabled: boolean;
  sync_cron: string | null;
  next_sync_at: string | null;
};

export type DialectInfo = {
  id: string;
  label: string;
  default_port: number | null;
  required_params: string[];
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = body?.detail ?? body;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return body as T;
}

export const api = {
  dialects: () => request<DialectInfo[]>("/api/dialects"),
  list: (params?: { q?: string; dialect?: string; status?: string }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set("q", params.q);
    if (params?.dialect) qs.set("dialect", params.dialect);
    if (params?.status) qs.set("status", params.status);
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<DataSource[]>(`/api/datasources${suffix}`);
  },
  get: (id: string) => request<DataSource>(`/api/datasources/${id}`),
  create: (payload: unknown) =>
    request<DataSource>("/api/datasources", { method: "POST", body: JSON.stringify(payload) }),
  update: (id: string, payload: unknown) =>
    request<DataSource>(`/api/datasources/${id}`, { method: "PATCH", body: JSON.stringify(payload) }),
  disable: (id: string) =>
    request<DataSource>(`/api/datasources/${id}/disable`, { method: "POST" }),
  enable: (id: string) =>
    request<DataSource>(`/api/datasources/${id}/enable`, { method: "POST" }),
  remove: (id: string, cascade: boolean) =>
    request(`/api/datasources/${id}`, {
      method: "DELETE",
      body: JSON.stringify({ confirm: true, cascade }),
    }),
  test: (id: string) =>
    request<DataSource>(`/api/datasources/${id}/test`, { method: "POST" }),
  testForm: (payload: unknown) =>
    request("/api/datasources/test", { method: "POST", body: JSON.stringify(payload) }),
  extract: (id: string) =>
    request(`/api/datasources/${id}/extract`, { method: "POST" }),
  jobs: (id: string) => request<any[]>(`/api/datasources/${id}/jobs`),
  metadata: (id: string, query: Record<string, string | undefined> = {}) => {
    const qs = new URLSearchParams();
    Object.entries(query).forEach(([k, v]) => {
      if (v) qs.set(k, v);
    });
    const suffix = qs.toString() ? `?${qs}` : "";
    return request<any>(`/api/datasources/${id}/metadata${suffix}`);
  },
  schedule: (id: string, enabled: boolean, cron: string | null) =>
    request<DataSource>(`/api/datasources/${id}/sync-schedule`, {
      method: "PUT",
      body: JSON.stringify({ enabled, cron }),
    }),
  sync: (id: string) =>
    request<{ status: string; version_bumped?: boolean; snapshot_version?: number }>(
      `/api/datasources/${id}/sync`,
      { method: "POST" },
    ),
  drifts: (id: string, kind?: string) => {
    const suffix = kind ? `?kind=${encodeURIComponent(kind)}` : "";
    return request<any[]>(`/api/datasources/${id}/drifts${suffix}`);
  },
  snapshots: (id: string) => request<any[]>(`/api/datasources/${id}/snapshots`),
};

export const STATUS_LABEL: Record<DataSource["status"], string> = {
  draft: "草稿",
  test_failed: "测试失败",
  ready: "已就绪",
  disabled: "已停用",
};
