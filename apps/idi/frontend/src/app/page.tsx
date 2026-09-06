"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import { STATUS_LABEL, api, type DataSource, type DialectInfo } from "@/lib/api";

const STATUS_OPTIONS = ["", "draft", "test_failed", "ready", "disabled"] as const;

export default function HomePage() {
  const [items, setItems] = useState<DataSource[]>([]);
  const [dialects, setDialects] = useState<DialectInfo[]>([]);
  const [q, setQ] = useState("");
  const [dialect, setDialect] = useState("");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({
    name: "",
    dialect: "postgresql",
    host: "demo.local",
    port: "5432",
    database: "demo",
    username: "ro",
    password: "",
    readonly_intent: true,
    sqlitePath: "",
  });

  const selectedDialect = useMemo(
    () => dialects.find((d) => d.id === form.dialect),
    [dialects, form.dialect],
  );

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

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      const params: Record<string, unknown> = {
        host: form.host,
        port: form.port,
        database: form.database,
        username: form.username,
        password: form.password,
      };
      if (form.sqlitePath.trim()) {
        params.__sqlite_path = form.sqlitePath.trim();
        params.__skip_tcp = true;
      }
      if (form.dialect === "snowflake") {
        Object.assign(params, {
          account: form.host,
          warehouse: form.database,
        });
      }
      if (form.dialect === "bigquery") {
        Object.assign(params, { project: form.database, dataset: form.database });
      }
      if (form.dialect === "databricks") {
        Object.assign(params, { http_path: "/sql", token: form.password });
      }
      await api.create({
        name: form.name,
        dialect: form.dialect,
        readonly_intent: form.readonly_intent,
        params,
      });
      setShowCreate(false);
      setForm((f) => ({ ...f, name: "", password: "" }));
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

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
        <button className="btn btn-primary" type="button" onClick={() => setShowCreate((v) => !v)}>
          {showCreate ? "收起新建" : "新建数据源"}
        </button>
      </div>

      {error ? <p className="error">{error}</p> : null}

      {showCreate ? (
        <form className="panel" onSubmit={onCreate}>
          <h2 style={{ fontFamily: "var(--font-display)", marginTop: 0 }}>新建连接</h2>
          <div className="grid-2">
            <div className="field">
              <label>显示名称</label>
              <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </div>
            <div className="field">
              <label>数据库类型</label>
              <select
                value={form.dialect}
                onChange={(e) => {
                  const id = e.target.value;
                  const d = dialects.find((x) => x.id === id);
                  setForm({
                    ...form,
                    dialect: id,
                    port: d?.default_port ? String(d.default_port) : form.port,
                  });
                }}
              >
                {dialects.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="field">
              <label>主机 / Account / Endpoint</label>
              <input value={form.host} onChange={(e) => setForm({ ...form, host: e.target.value })} />
            </div>
            <div className="field">
              <label>端口</label>
              <input value={form.port} onChange={(e) => setForm({ ...form, port: e.target.value })} />
            </div>
            <div className="field">
              <label>数据库 / 项目</label>
              <input value={form.database} onChange={(e) => setForm({ ...form, database: e.target.value })} />
            </div>
            <div className="field">
              <label>用户名</label>
              <input value={form.username} onChange={(e) => setForm({ ...form, username: e.target.value })} />
            </div>
            <div className="field">
              <label>密码 / Token</label>
              <input
                type="password"
                value={form.password}
                onChange={(e) => setForm({ ...form, password: e.target.value })}
              />
            </div>
            <div className="field">
              <label>本地 SQLite 桥接路径（可选，用于本地验证）</label>
              <input
                value={form.sqlitePath}
                onChange={(e) => setForm({ ...form, sqlitePath: e.target.value })}
                placeholder="/tmp/demo-source.db"
              />
            </div>
          </div>
          <label style={{ display: "flex", gap: "0.5rem", alignItems: "center", marginTop: "0.9rem" }}>
            <input
              type="checkbox"
              checked={form.readonly_intent}
              onChange={(e) => setForm({ ...form, readonly_intent: e.target.checked })}
            />
            只读连接声明（默认开启）
          </label>
          {selectedDialect ? (
            <p className="muted mono">必填：{selectedDialect.required_params.join(", ")}</p>
          ) : null}
          <div style={{ marginTop: "1rem" }}>
            <button className="btn btn-primary" disabled={creating} type="submit">
              {creating ? "保存中…" : "保存为草稿"}
            </button>
          </div>
        </form>
      ) : null}

      {items.length === 0 ? (
        <p className="empty">暂无匹配的数据源。</p>
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
    </main>
  );
}
