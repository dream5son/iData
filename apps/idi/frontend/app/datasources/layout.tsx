import { DatasourcesNav } from "./components/nav";

export default function DatasourcesLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <aside className="overflow-auto border-b border-line bg-bg0 px-4 py-3 text-sm md:border-b-0 md:border-r">
        <DatasourcesNav />
      </aside>
      <div className="min-h-0 overflow-auto bg-bg0">{children}</div>
    </>
  );
}
