"use client";

import Link from "next/link";
import { useParams, usePathname } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { STATUS_LABEL, api, type DataSource } from "@/lib/api";

export default function DatasourceLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const pathname = usePathname();
  const [ds, setDs] = useState<DataSource | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void api
      .get(params.id)
      .then(setDs)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [params.id]);

  const tabs = [
    { href: `/datasources/${params.id}`, label: "概览", exact: true },
    { href: `/datasources/${params.id}/metadata`, label: "元数据" },
    { href: `/datasources/${params.id}/sync`, label: "同步与漂移" },
    { href: `/datasources/${params.id}/versions`, label: "快照版本" },
  ];

  return (
    <main className="shell">
      <p className="muted">
        <Link href="/">← 数据源列表</Link>
      </p>
      {error ? <p className="error">{error}</p> : null}
      {ds ? (
        <>
          <h1 className="brand" style={{ fontSize: "2rem" }}>
            {ds.name}
          </h1>
          <p className="lede">
            <span className={`pill ${ds.status}`}>{STATUS_LABEL[ds.status]}</span>{" "}
            <span className="mono muted">{ds.dialect}</span>
            {ds.current_snapshot_version != null ? (
              <>
                {" "}
                · 当前快照 v{ds.current_snapshot_version}
              </>
            ) : null}
          </p>
          <nav className="nav-tabs">
            {tabs.map((tab) => {
              const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
              return (
                <Link key={tab.href} href={tab.href} data-active={active ? "true" : "false"}>
                  {tab.label}
                </Link>
              );
            })}
          </nav>
        </>
      ) : null}
      {children}
    </main>
  );
}
