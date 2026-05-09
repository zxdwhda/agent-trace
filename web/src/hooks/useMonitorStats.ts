import { useQuery } from "@tanstack/react-query"
import type { MonitorStats } from "@/types"

async function fetchStats(): Promise<MonitorStats> {
  const res = await fetch("/api/status")
  if (!res.ok) throw new Error("Failed to fetch stats")
  return res.json()
}

export function useMonitorStats() {
  return useQuery<MonitorStats>({
    queryKey: ["monitor-stats"],
    queryFn: fetchStats,
  })
}
