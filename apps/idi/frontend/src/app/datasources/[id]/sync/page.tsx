"use client";

import { FormEvent, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api, type DataSource } from "@/lib/api";

export default function SyncPage() {
  const { id } = useParams<{ id: string }>();
  const [ds, setDs] = useState<DataSource | null>(null);
  const [cron, setCron] = useState("0 */6 * * *");
  const [enabled, setEnabled] = useState(false);
  const [drifts, setDrifts] = useState<any[]>([]);
  const [kind, setKind] = useState("");
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  async function reload() {
    const [d, driftList] = await Promise.all([api.get(id), api.drifts(id, kind || undefined)]);
    setDs(d);
    setCron(d.sync_cron ?? "0 */6 * * *");
    setEnabled(d.sync_enabled);
    setDrifts(driftList);
  }

  useEffect(() => {
    void reload().catch((err) => setError(String(err)));
  }, [id, kind]);

  async function saveSchedule(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      await api.schedule(id, enabled, cron);
      setMessage("调度已保存");
      await reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  return (
    <section className="panel">
      <form onSubmit={saveSchedule} className="toolbar">
        <label style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
          启用定时同步
        </label>
        <div className="field">
          <label>Cron</label>
          <input value={cron} onChange={(e) => setCron(e.target.value)} />
        </div>
        <button className="btn btn-primary" type="submit">
          保存调度
        </button>
        <button
          className="btn"
          type="button"
          onClick={() => {
            void (async () => {
              setError("");
              try {
                const job = await api.sync(id);
                setMessage(`同步完成：${job.status}${job.version_bumped ? `，升至 v${job.snapshot_version}` : "，未升版"}`);
                await reload();
              } catch (err) {
                setError(err instanceof Error ? err.message : String(err));
              }
            })();
          }}
        >
          立即同步
        </button>
      </form>
      {ds?.next_sync_at ? <p className="muted mono">下次计划：{ds.next_sync_at}</p> : null}
      {message ? <p className="muted">{message}</p> : null}
      {error ? <p className="error">{error}</p> : null}

      <div className="field" style={{ maxWidth: "16rem", marginTop: "1rem" }}>
        <label>漂移类型</label>
        <select value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="">全部</option>
          <option value="table_added">新增表</option>
          <option value="table_removed">删除表</option>
          <option value="column_added">新增列</option>
          <option value="column_removed">删减列</option>
          <option value="type_changed">类型变更</option>
          <option value="column_constraint_changed">约束变更</option>
          <option value="index_or_partition_changed">索引/分区变更</option>
        </select>
      </div>

      {drifts.length === 0 ? (
        <p className="empty">无漂移记录。</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>时间</th>
              <th>类型</th>
              <th>对象</th>
              <th>前</th>
              <th>后</th>
            </tr>
          </thead>
          <tbody>
            {drifts.map((d) => (
              <tr key={d.id}>
                <td className="mono muted">{d.detected_at}</td>
                <td>{d.kind}</td>
                <td className="mono">
                  {d.schema_name}.{d.table_name}.{d.object_name}
                </td>
                <td className="mono muted">{d.before ?? "—"}</td>
                <td className="mono muted">{d.after ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
