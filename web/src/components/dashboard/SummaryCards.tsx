import { useMonitorStats } from "@/hooks/useMonitorStats"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Activity, FileText, Zap, Clock } from "lucide-react"

export function SummaryCards() {
  const { data } = useMonitorStats()
  const stats = data ?? {
    active_sessions: 0,
    monitored_files: 0,
    total_turns_today: 0,
    total_tokens_today: 0,
    uptime_seconds: 0,
  }

  const cards = [
    { label: "活跃会话", value: stats.active_sessions, icon: Activity },
    { label: "监控文件", value: stats.monitored_files, icon: FileText },
    { label: "今日轮次", value: stats.total_turns_today, icon: Zap },
    { label: "今日 Token", value: stats.total_tokens_today, icon: Clock },
  ]

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cards.map((card) => {
        const Icon = card.icon
        return (
          <Card key={card.label}>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm font-medium">{card.label}</CardTitle>
              <Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{card.value}</div>
            </CardContent>
          </Card>
        )
      })}
    </div>
  )
}
