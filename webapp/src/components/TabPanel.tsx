import type { ReactNode } from "react";

interface TabPanelProps {
  active: boolean; // currently visible
  mounted: boolean; // has been visited at least once
  children: ReactNode;
}

export function TabPanel({ active, mounted, children }: TabPanelProps) {
  if (!mounted) return null; // never-visited → not in DOM at all
  return (
    <div
      aria-hidden={!active}
      className={"tab-panel " + (active ? "tab-panel-active" : "tab-panel-hidden")}
    >
      {children}
    </div>
  );
}
