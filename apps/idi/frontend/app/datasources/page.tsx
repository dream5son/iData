"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { STATUS_LABEL, api, type DataSource, type DialectInfo } from "@/lib/api";
import { CreateDatasourceDialog } from "./components/create-dialog";

const STATUS_OPTIONS = ["", "draft", "test_failed", "ready", "disabled"] as const;

export default function HomePage() {
  const [items, setItems] = useState<DataSource[]>([]);
  const [dialects, setDialects] = useState<DialectInfo[]>([]);
  const [q, setQ] = useState("");
  const [dialect, setDialect] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);

  async function refresh() {
    setError("");
    try {
      const [list, d] = await Promise.all([
        api.list({ q: q || undefined, dialect: dialect || undefined, status: status || undefined }),
        api.dialects(),
      ]);
      setItems(list);
      setDialects(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <main className="shell">
      <header>
        <p className="muted" style={{ margin: 0, letterSpacing: "0.08em", textTransform: "uppercase", fontSize: "0.75rem" }}>
          iData · IDI
        </p>
        <h1 className="brand">
          数据源<span>治理台</span>
        </h1>
        <p className="lede">
          接入异构库、深度测连、抽取与同步元数据。面向实施工程师的第一批能力（US-001～US-006）。
        </p>
      </header>

      <div className="toolbar">
        <div className="field">
          <label>名称搜索</label>
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="关键字" />
        </div>
        <div className="field">
          <label>类型</label>
          <select value={dialect} onChange={(e) => setDialect(e.target.value)}>
            <option value="">全部</option>
            {dialects.map((d) => (
              <option key={d.id} value={d.id}>
                {d.label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <label>状态</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUS_OPTIONS.map((s) => (
              <option key={s || "all"} value={s}>
                {s ? STATUS_LABEL[s as DataSource["status"]] : "全部"}
              </option>
            ))}
          </select>
        </div>
        <button className="btn" type="button" onClick={() => void refresh()}>
          筛选
        </button>
        <button className="btn btn-primary" type="button" onClick={() => setShowCreate(true)}>
          新建数据源
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}

      {items.length === 0 ? (
        <div className="empty-actions">
          <span>暂无匹配的数据源。</span>
          <button className="btn btn-primary" type="button" onClick={() => setShowCreate(true)}>
            新建数据源
          </button>
        </div>
      ) : (
        <table className="table">
          <thead>
            <tr>
              <th>名称</th>
              <th>类型</th>
              <th>状态</th>
              <th>最近测试</th>
              <th>更新时间</th>
              <th>当前版本</th>
            </tr>
          </thead>
          <tbody>
            {items.map((item) => (
              <tr key={item.id}>
                <td>
                  <Link href={`/datasources/${item.id}`}>{item.name}</Link>
                </td>
                <td className="mono">{item.dialect}</td>
                <td>
                  <span className={`pill ${item.status}`}>{STATUS_LABEL[item.status]}</span>
                </td>
                <td className="mono muted">{item.last_tested_at ?? "—"}</td>
                <td className="mono muted">{item.updated_at}</td>
                <td className="mono">{item.current_snapshot_version ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {showCreate ? (
        <CreateDatasourceDialog
          dialects={dialects}
          onClose={() => setShowCreate(false)}
          onCreated={() => refresh()}
        />
      ) : null}
    </main>
  );
}
