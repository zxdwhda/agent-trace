import { Activity } from "lucide-react"
import { useMonitorStats } from "@/hooks/useMonitorStats"

export function Header() {
  const { data: stats } = useMonitorStats()
  return (
    <header className="h-14 border-b flex items-center justify-between px-6 bg-card">
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Activity className="h-4 w-4 text-green-500" />
        <span>监控中</span>
      </div>
      <div className="flex items-center gap-6 text-sm text-muted-foreground">
        <span>活跃会话: <strong className="text-foreground">{stats?.active_sessions ?? 0}</strong></span>
        <span>监控文件: <strong className="text-foreground">{stats?.monitored_files ?? 0}</strong></span>
        <span>运行时长: <strong className="text-foreground">{formatUptime(stats?.uptime_seconds ?? 0)}</strong></span>
      </div>
    </header>
  )
}

function formatUptime(s: number) {
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}
