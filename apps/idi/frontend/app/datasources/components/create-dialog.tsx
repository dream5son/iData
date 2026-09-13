"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { api, type DialectInfo } from "@/lib/api";

const PARAM_LABELS: Record<string, string> = {
  host: "主机",
  port: "端口",
  database: "数据库",
  username: "用户名",
  password: "密码",
  account: "Account",
  warehouse: "Warehouse",
  project: "项目",
  dataset: "Dataset",
  http_path: "HTTP Path",
  token: "Token",
  path: "文件路径",
};

const SECRET_KEYS = new Set(["password", "token"]);

const EMPTY_FORM = {
  name: "",
  dialect: "postgresql",
  host: "demo.local",
  port: "5432",
  database: "demo",
  username: "ro",
  password: "",
  account: "",
  warehouse: "",
  project: "",
  dataset: "",
  http_path: "/sql",
  token: "",
  path: "",
  readonly_intent: true,
};

type FormState = typeof EMPTY_FORM;

function placeholderFor(key: string, dialect?: DialectInfo) {
  if (key === "port" && dialect?.default_port) return String(dialect.default_port);
  if (key === "host") return "demo.local";
  if (key === "http_path") return "/sql";
  if (key === "account") return "xy12345.us-east-1";
  if (key === "path") return "/tmp/demo-source.db";
  return undefined;
}

function buildParams(form: FormState, keys: string[]) {
  const params: Record<string, unknown> = {};
  for (const key of keys) {
    const value = form[key as keyof FormState];
    if (typeof value === "string") params[key] = value;
  }
  return params;
}

type Props = {
  dialects: DialectInfo[];
  onClose: () => void;
  onCreated: () => Promise<void> | void;
};

export function CreateDatasourceDialog({ dialects, onClose, onCreated }: Props) {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");

  const selectedDialect = useMemo(
    () => dialects.find((d) => d.id === form.dialect) ?? dialects[0],
    [dialects, form.dialect],
  );
  const requiredParams = selectedDialect?.required_params ?? [];

  useEffect(() => {
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, []);

  function requestClose() {
    if (creating) return;
    onClose();
  }

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key !== "Escape" || creating) return;
      onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [creating, onClose]);

  function setField<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setCreating(true);
    setError("");
    try {
      await api.create({
        name: form.name.trim(),
        dialect: form.dialect,
        readonly_intent: form.readonly_intent,
        params: buildParams(form, requiredParams),
      });
      await onCreated();
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setCreating(false);
    }
  }

  return (
    <div
      className="modal-backdrop"
      role="presentation"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) requestClose();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-datasource-title"
        onMouseDown={(e) => e.stopPropagation()}
      >
        <div className="modal-header">
          <div>
            <h2 id="create-datasource-title">新建数据源</h2>
            <p className="muted">保存为草稿后可再测连与抽取元数据。</p>
          </div>
          <button className="modal-close" type="button" aria-label="关闭" onClick={requestClose} disabled={creating}>
            ×
          </button>
        </div>
        <form onSubmit={onSubmit}>
          <div className="modal-body">
            {error ? <p className="error" style={{ margin: 0 }}>{error}</p> : null}

            <section>
              <h3 className="modal-section-title">基本信息</h3>
              <div className="grid-2">
                <div className="field">
                  <label htmlFor="ds-name">显示名称</label>
                  <input
                    id="ds-name"
                    required
                    autoFocus
                    value={form.name}
                    onChange={(e) => setField("name", e.target.value)}
                    placeholder="例如 生产数仓只读"
                  />
                </div>
                <div className="field">
                  <label htmlFor="ds-dialect">数据库类型</label>
                  <select
                    id="ds-dialect"
                    value={form.dialect}
                    onChange={(e) => {
                      const id = e.target.value;
                      const d = dialects.find((x) => x.id === id);
                      setForm((f) => ({
                        ...f,
                        dialect: id,
                        port: d?.default_port ? String(d.default_port) : f.port,
                      }));
                    }}
                  >
                    {dialects.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </section>

            <section>
              <h3 className="modal-section-title">连接参数</h3>
              <div className="grid-2">
                {requiredParams.map((key) => (
                  <div className="field" key={key}>
                    <label htmlFor={`ds-${key}`}>{PARAM_LABELS[key] ?? key}</label>
                    <input
                      id={`ds-${key}`}
                      required
                      type={SECRET_KEYS.has(key) ? "password" : "text"}
                      autoComplete={SECRET_KEYS.has(key) ? "new-password" : "off"}
                      value={String(form[key as keyof FormState] ?? "")}
                      placeholder={placeholderFor(key, selectedDialect)}
                      onChange={(e) => setField(key as keyof FormState, e.target.value)}
                    />
                  </div>
                ))}
              </div>
            </section>

            <section>
              <h3 className="modal-section-title">选项</h3>
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={form.readonly_intent}
                  onChange={(e) => setField("readonly_intent", e.target.checked)}
                />
                只读连接声明（默认开启）
              </label>
            </section>
          </div>
          <div className="modal-footer">
            <button className="btn" type="button" onClick={requestClose} disabled={creating}>
              取消
            </button>
            <button className="btn btn-primary" disabled={creating} type="submit">
              {creating ? "保存中…" : "保存为草稿"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
