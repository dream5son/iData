"use client";

import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";

type MetaResponse = {
  table_count: number;
  schemas: string[];
  tables: any[];
  extracting: boolean;
  stale_warning: boolean;
  disabled_warning: boolean;
  historical: boolean;
  partial_snapshot: boolean;
  current_snapshot_version: number | null;
  latest_job: any;
};

export default function MetadataPage() {
  const { id } = useParams<{ id: string }>();
  const [meta, setMeta] = useState<MetaResponse | null>(null);
  const [schema, setSchema] = useState("");
  const [tableQ, setTableQ] = useState("");
  const [columnQ, setColumnQ] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [error, setError] = useState("");

  async function load() {
    setError("");
    try {
      const data = await api.metadata(id, {
        schema: schema || undefined,
        table_q: tableQ || undefined,
        column_q: columnQ || undefined,
      });
      setMeta(data);
      if (!selected && data.tables[0]) {
        setSelected(`${data.tables[0].schema_name}.${data.tables[0].name}`);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void load();
  }, [id]);

  const table = useMemo(
    () => meta?.tables.find((t) => `${t.schema_name}.${t.name}` === selected) ?? null,
    [meta, selected],
  );

  return (
    <section className="panel">
      <div className="toolbar">
        <div className="field">
          <label>Schema</label>
          <select value={schema} onChange={(e) => setSchema(e.target.value)}>
            <option value="">全部</option>
            {(meta?.schemas ?? []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>表名</label>
          <input value={tableQ} onChange={(e) => setTableQ(e.target.value)} />
        </div>
        <div className="field">
          <label>列名</label>
          <input value={columnQ} onChange={(e) => setColumnQ(e.target.value)} />
        </div>
        <button className="btn" type="button" onClick={() => void load()}>
          搜索
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}
      {meta?.stale_warning ? <p className="muted">抽取进行中，以下为抽取开始前的数据。</p> : null}
      {meta?.disabled_warning ? <p className="muted">数据源已停用，内容可能过期。</p> : null}
      {meta?.partial_snapshot ? <p className="muted">当前快照标记为部分完整。</p> : null}
      {meta?.historical ? <p className="muted">正在查看历史版本（只读）。</p> : null}

      {!meta || meta.table_count === 0 ? (
        <p className="empty">
          字典为空。请等待自动抽取完成，或在数据源就绪后触发重新抽取。
          {meta?.latest_job ? ` 最近任务：${meta.latest_job.status}` : ""}
        </p>
      ) : (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "minmax(12rem, 18rem) 1fr",
            gap: "1rem",
          }}
          className="meta-split"
        >
          <div>
            <p className="muted">共 {meta.table_count} 张表 · 版本 {meta.current_snapshot_version ?? "—"}</p>
            <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
              {meta.tables.map((t) => {
                const key = `${t.schema_name}.${t.name}`;
                return (
                  <li key={key}>
                    <button
                      type="button"
                      className="btn"
                      style={{
                        width: "100%",
                        textAlign: "left",
                        marginBottom: "0.35rem",
                        borderColor: selected === key ? "var(--accent)" : undefined,
                      }}
                      onClick={() => setSelected(key)}
                    >
                      <span className="mono">{t.schema_name}.</span>
                      {t.name}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
          <div>
            {!table ? (
              <p className="empty">选择一张表。</p>
            ) : (
              <>
                <h2 style={{ fontFamily: "var(--font-display)", marginTop: 0 }}>
                  {table.schema_name}.{table.name}
                </h2>
                <p className="muted">
                  {table.table_type}
                  {table.comment ? ` · ${table.comment}` : ""}
                </p>
                <h3>列</h3>
                <table className="table">
                  <thead>
                    <tr>
                      <th>列名</th>
                      <th>类型</th>
                      <th>可空</th>
                      <th>主键</th>
                      <th>默认值</th>
                    </tr>
                  </thead>
                  <tbody>
                    {table.columns.map((c: any) => (
                      <tr key={c.name}>
                        <td className="mono">{c.name}</td>
                        <td className="mono">{c.data_type}</td>
                        <td>{c.nullable ? "是" : "否"}</td>
                        <td>{c.is_primary_key ? "是" : ""}</td>
                        <td className="mono muted">{c.default ?? "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <h3>索引 / 物理结构</h3>
                {table.indexes.length === 0 && table.partition_keys.length === 0 ? (
                  <p className="empty">无索引 / 无分区</p>
                ) : (
                  <ul>
                    {table.indexes.map((idx: any) => (
                      <li key={idx.name} className="mono">
                        {idx.name} ({idx.columns.join(", ")}) {idx.unique ? "UNIQUE" : ""} {idx.index_type ?? ""}
                      </li>
                    ))}
                    {table.partition_keys.length ? (
                      <li className="mono">partition: {table.partition_keys.join(", ")}</li>
                    ) : null}
                  </ul>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
