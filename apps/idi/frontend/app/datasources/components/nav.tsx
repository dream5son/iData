"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function DatasourcesNav() {
  const pathname = usePathname();
  const id = pathname.match(/^\/datasources\/([^/]+)/)?.[1];
  const tabs = id
    ? [
        { href: `/datasources/${id}`, label: "概览", exact: true },
        { href: `/datasources/${id}/metadata`, label: "元数据" },
        { href: `/datasources/${id}/sync`, label: "同步与漂移" },
        { href: `/datasources/${id}/versions`, label: "快照版本" },
      ]
    : [];

  return (
    <nav className="side-nav" aria-label="数据源">
      <Link href="/datasources" data-active={pathname === "/datasources" ? "true" : "false"}>
        数据源列表
      </Link>
      {tabs.length > 0 ? (
        <div className="side-nav-sub">
          {tabs.map((tab) => {
            const active = tab.exact ? pathname === tab.href : pathname.startsWith(tab.href);
            return (
              <Link key={tab.href} href={tab.href} data-active={active ? "true" : "false"}>
                {tab.label}
              </Link>
            );
          })}
        </div>
      ) : null}
    </nav>
  );
}
