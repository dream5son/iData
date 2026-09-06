"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";

export default function VersionsPage() {
  const { id } = useParams<{ id: string }>();
  const [snaps, setSnaps] = useState<any[]>([]);
  const [error, setError] = useState("");
  const [preview, setPreview] = useState<any | null>(null);

  useEffect(() => {
    void api
      .snapshots(id)
      .then(setSnaps)
      .catch((err) => setError(String(err)));
  }, [id]);

  return (
    <section className="panel">
      {error ? <p className="error">{error}</p> : null}
      {snaps.length === 0 ? (
        <p className="empty">尚无快照。首次抽取成功后会生成 v1。</p>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>版本</th>
              <th>时间</th>
              <th>来源任务</th>
              <th>漂移数</th>
              <th>标记</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {snaps.map((s) => (
              <tr key={s.version}>
                <td className="mono">v{s.version}</td>
                <td className="mono muted">{s.created_at}</td>
                <td className="mono">{s.source_job_id}</td>
                <td>{s.drift_count}</td>
                <td>
                  {s.is_current ? <span className="pill ready">当前</span> : <span className="pill">历史</span>}
                  {s.partial ? <span className="pill test_failed">部分完整</span> : null}
                </td>
                <td>
                  <button
                    className="btn"
                    type="button"
                    onClick={() => {
                      void api
                        .metadata(id, { version: String(s.version) })
                        .then(setPreview)
                        .catch((err) => setError(String(err)));
                    }}
                  >
                    只读浏览
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {preview ? (
        <div className="panel">
          <h2 style={{ fontFamily: "var(--font-display)" }}>
            只读历史版本 v{preview.current_snapshot_version}，非当前生效
          </h2>
          <p className="muted">表数量 {preview.table_count}</p>
          <ul>
            {preview.tables.slice(0, 50).map((t: any) => (
              <li key={`${t.schema_name}.${t.name}`} className="mono">
                {t.schema_name}.{t.name} ({t.columns.length} cols)
              </li>
            ))}
          </ul>
          <p>
            <Link href={`/datasources/${id}/metadata`}>回到当前元数据视图</Link>
          </p>
        </div>
      ) : null}
    </section>
  );
}
