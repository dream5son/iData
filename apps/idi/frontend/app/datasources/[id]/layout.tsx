"use client";

import { useParams } from "next/navigation";
import { ReactNode, useEffect, useState } from "react";
import { STATUS_LABEL, api, type DataSource } from "@/lib/api";

export default function DatasourceLayout({ children }: { children: ReactNode }) {
  const params = useParams<{ id: string }>();
  const [ds, setDs] = useState<DataSource | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    void api
      .get(params.id)
      .then(setDs)
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [params.id]);

  return (
    <main className="shell">
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
        </>
      ) : null}
      {children}
    </main>
  );
}
