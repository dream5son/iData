"use client";

import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api, type DataSource } from "@/lib/api";

export default function DatasourceOverviewPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const [ds, setDs] = useState<DataSource | null>(null);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function reload() {
    setDs(await api.get(id));
  }

  useEffect(() => {
    void reload().catch((err) => setError(String(err)));
  }, [id]);

  async function run(action: () => Promise<unknown>, ok = "完成") {
    setBusy(true);
    setError("");
    setMessage("");
    try {
      await action();
      await reload();
      setMessage(ok);
      router.refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  if (!ds) return <p className="muted">加载中…</p>;

  return (
    <section className="panel">
      <div className="toolbar">
        <button className="btn btn-primary" disabled={busy} onClick={() => void run(() => api.test(id), "测试完成")}>
          测试连接
        </button>
        <button className="btn" disabled={busy || ds.status !== "ready"} onClick={() => void run(() => api.extract(id), "抽取已触发")}>
          重新抽取
        </button>
        {ds.status === "disabled" ? (
          <button className="btn" disabled={busy} onClick={() => void run(() => api.enable(id), "已启用，需重新测通")}>
            启用
          </button>
        ) : (
          <button className="btn" disabled={busy} onClick={() => void run(() => api.disable(id), "已停用")}>
            停用
          </button>
        )}
        <button
          className="btn btn-danger"
          disabled={busy}
          onClick={() => {
            const cascade = window.confirm("若存在元数据，将级联删除。确认删除该数据源？");
            if (!cascade) return;
            void run(async () => {
              await api.remove(id, true);
              router.push("/");
            }, "已删除");
          }}
        >
          删除
        </button>
      </div>

      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <h2 style={{ fontFamily: "var(--font-display)" }}>最近测试</h2>
      {!ds.last_test ? (
        <p className="empty">尚未测试。</p>
      ) : (
        <div>
          {ds.last_test.steps.map((step) => (
            <div className="step-row" key={step.name}>
              <span className="mono">{step.name}</span>
              <span className={`pill ${step.outcome}`}>{step.outcome}</span>
              <span className="muted">{step.message}</span>
            </div>
          ))}
        </div>
      )}

      <h2 style={{ fontFamily: "var(--font-display)" }}>连接参数（凭证已掩码）</h2>
      <pre className="mono" style={{ background: "var(--bg2)", padding: "1rem", overflow: "auto" }}>
        {JSON.stringify(ds.params, null, 2)}
      </pre>
      <p className="muted">只读声明：{ds.readonly_intent ? "开启" : "关闭"}</p>
    </section>
  );
}
