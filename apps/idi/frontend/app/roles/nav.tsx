"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

export function RolesNav() {
  const pathname = usePathname();
  const active = pathname === "/roles" || pathname.startsWith("/roles/");

  return (
    <nav className="side-nav" aria-label="角色设置">
      <Link href="/roles" data-active={active ? "true" : "false"}>
        角色设置
      </Link>
    </nav>
  );
}
