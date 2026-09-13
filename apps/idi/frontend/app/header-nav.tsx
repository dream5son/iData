"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const ITEMS = [
  { href: "/datasources", label: "数据源" },
  { href: "/roles", label: "角色设置" },
] as const;

export function HeaderNav() {
  const pathname = usePathname();

  return (
    <nav className="header-nav" aria-label="菜单区">
      {ITEMS.map((item) => {
        const active = pathname === item.href || pathname.startsWith(`${item.href}/`);
        return (
          <Link key={item.href} href={item.href} data-active={active ? "true" : "false"}>
            {item.label}
          </Link>
        );
      })}
    </nav>
  );
}
