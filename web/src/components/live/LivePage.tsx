import { useWebSocket } from "@/hooks/useWebSocket"
import { Badge } from "@/components/ui/badge"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { ScrollArea } from "@/components/ui/scroll-area"
import { getRecentActivities, getLiveMetrics } from "@/lib/api"
import type { ActivityLog, LiveMetrics } from "@/types"
import { useQuery } from "@tanstack/react-query"
import { useMemo } from "react"

const ACTIVITY_ICONS: Record<string, string> = {
  import_completed: "📥",
  session_deleted: "🗑️",
  session_archived: "📦",
  session_restored: "📂",
}

function ActivityIcon({ type }: { type: string }) {
  return <span className="text-lg">{ACTIVITY_ICONS[type] || "📋"}</span>
}

function ActivityItem({ activity }: { activity: ActivityLog }) {
  const timeStr = new Date(activity.timestamp * 1000).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  })

  return (
    <div className="flex items-start gap-3 p-3 rounded-md hover:bg-muted/50 transition-colors">
      <div className="mt-0.5 shrink-0">
        <ActivityIcon type={activity.activity_type} />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className="text-sm font-medium truncate">
            {activity.description || activity.activity_type}
          </span>
          <span className="text-xs text-muted-foreground shrink-0">{timeStr}</span>
        </div>
        {Object.keys(activity.metadata).length > 0 && (
          <div className="mt-1 text-xs text-muted-foreground font-mono truncate">
            {JSON.stringify(activity.metadata)}
          </div>
        )}
      </div>
    </div>
  )
}

function ActiveSessionCard({ session }: { session: LiveMetrics["active_sessions"][0] }) {
  const elapsedMin = Math.floor(session.elapsed_seconds / 60)
  const elapsedSec = session.elapsed_seconds % 60
  const elapsedStr = session.elapsed_seconds > 60
    ? `${elapsedMin}分${elapsedSec}秒`
    : `${session.elapsed_seconds}秒`

  return (
    <div className="p-3 rounded-lg border bg-card hover:bg-muted/30 transition-colors">
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-mono text-muted-foreground truncate max-w-[120px]">
          {session.session_id.slice(0, 8)}…
        </span>
        <Badge variant="outline" className="text-[10px] h-5">
          Turn #{session.turn_index}
        </Badge>
      </div>
      <div className="text-sm font-medium truncate mb-1" title={session.user_input}>
        {session.user_input || "(无输入)"}
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{session.model_name}</span>
        <span className="flex items-center gap-2">
          {session.pending_tools > 0 && (
            <span className="text-amber-500">🔧 {session.pending_tools}</span>
          )}
          <span>⏱ {elapsedStr}</span>
        </span>
      </div>
    </div>
  )
}

function TokenSparkline({ data }: { data: LiveMetrics["token_throughput"] }) {
  if (!data || data.length === 0) return null

  const maxVal = Math.max(...data.map((d) => d.total_tokens), 1)
  const points = data.map((d, i) => {
    const x = (i / (data.length - 1 || 1)) * 100
    const y = 100 - (d.total_tokens / maxVal) * 100
    return `${x},${y}`
  }).join(" ")

  const totalInput = data.reduce((s, d) => s + d.input_tokens, 0)
  const totalOutput = data.reduce((s, d) => s + d.output_tokens, 0)
  const turns = data.reduce((s, d) => s + d.turns, 0)

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <div className="text-center p-2 rounded-md bg-muted/50">
          <div className="text-lg font-bold text-emerald-600">{totalInput.toLocaleString()}</div>
          <div className="text-[10px] text-muted-foreground">Input</div>
        </div>
        <div className="text-center p-2 rounded-md bg-muted/50">
          <div className="text-lg font-bold text-blue-600">{totalOutput.toLocaleString()}</div>
          <div className="text-[10px] text-muted-foreground">Output</div>
        </div>
        <div className="text-center p-2 rounded-md bg-muted/50">
          <div className="text-lg font-bold">{turns}</div>
          <div className="text-[10px] text-muted-foreground">Turns</div>
        </div>
      </div>
      <svg viewBox="0 0 100 100" className="w-full h-16" preserveAspectRatio="none">
        <polyline
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          points={points}
          className="text-primary"
        />
        <polygon
          fill="currentColor"
          fillOpacity="0.1"
          points={`0,100 ${points} 100,100`}
          className="text-primary"
        />
      </svg>
      <div className="flex justify-between text-[10px] text-muted-foreground">
        <span>5分钟前</span>
        <span>现在</span>
      </div>
    </div>
  )
}

function SkillHeatmap({ skills }: { skills: LiveMetrics["skill_heatmap"] }) {
  const maxCalls = Math.max(...skills.map((s) => s.calls), 1)
  return (
    <div className="space-y-2">
      {skills.map((skill, idx) => {
        const pct = (skill.calls / maxCalls) * 100
        return (
          <div key={skill.skill_name} className="flex items-center gap-2">
            <span className="text-xs w-5 text-muted-foreground">{idx + 1}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-xs font-medium truncate">{skill.skill_name}</span>
                <span className="text-xs text-muted-foreground">{skill.calls}</span>
              </div>
              <div className="h-1.5 rounded-full bg-muted overflow-hidden">
                <div
                  className="h-full rounded-full bg-orange-500 transition-all"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </div>
          </div>
        )
      })}
      {skills.length === 0 && (
        <div className="text-xs text-muted-foreground text-center py-4">暂无技能调用记录</div>
      )}
    </div>
  )
}

export function LivePage() {
  const { events, connected, clear } = useWebSocket()
  const { data: activities, isLoading } = useQuery<ActivityLog[]>({
    queryKey: ["recent-activities"],
    queryFn: getRecentActivities,
    refetchInterval: 10000,
  })
  const { data: live } = useQuery<LiveMetrics>({
    queryKey: ["live-metrics"],
    queryFn: getLiveMetrics,
    refetchInterval: 5000,
  })

  const recentEvents = useMemo(() => events.slice(-20), [events])

  return (
    <div className="space-y-4 h-full flex flex-col">
      {/* ── 上半：实时监控面板 ── */}
      <div className="shrink-0">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-xl font-bold">实时监控</h1>
          <div className="flex items-center gap-3">
            <Badge variant={connected ? "default" : "destructive"}>
              {connected ? "已连接" : "已断开"}
            </Badge>
            <span className="text-xs text-muted-foreground">
              今日 {live?.daily.total_turns_today ?? 0} turns / {(live?.daily.total_tokens_today ?? 0).toLocaleString()} tokens
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
          {/* 左栏：活跃会话 */}
          <Card className="flex flex-col">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold flex items-center gap-2">
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
                活跃会话 ({live?.active_count ?? 0})
              </CardTitle>
            </CardHeader>
            <CardContent className="pt-0 flex-1 overflow-hidden">
              <ScrollArea className="h-52">
                <div className="space-y-2 pr-2">
                  {live?.active_sessions && live.active_sessions.length > 0 ? (
                    live.active_sessions.map((s) => (
                      <ActiveSessionCard key={s.session_id} session={s} />
                    ))
                  ) : (
                    <div className="text-sm text-muted-foreground text-center py-8">
                      暂无活跃会话
                    </div>
                  )}
                </div>
              </ScrollArea>
            </CardContent>
          </Card>

          {/* 中栏：Token 吞吐 */}
          <Card className="flex flex-col">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">📊 Token 吞吐（5 分钟）</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 flex-1">
              {live?.token_throughput ? (
                <TokenSparkline data={live.token_throughput} />
              ) : (
                <div className="text-sm text-muted-foreground text-center py-8">加载中…</div>
              )}
            </CardContent>
          </Card>

          {/* 右栏：技能热度 */}
          <Card className="flex flex-col">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm font-semibold">🔥 技能热度 Top 5</CardTitle>
            </CardHeader>
            <CardContent className="pt-0 flex-1">
              {live?.skill_heatmap ? (
                <SkillHeatmap skills={live.skill_heatmap} />
              ) : (
                <div className="text-sm text-muted-foreground text-center py-8">加载中…</div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* 实时事件流（紧凑模式） */}
        <Card className="mt-3">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-semibold">⚡ 实时事件</CardTitle>
              <button
                onClick={clear}
                className="text-xs text-muted-foreground hover:text-foreground"
              >
                清空
              </button>
            </div>
          </CardHeader>
          <CardContent className="pt-0">
            <div className="h-56 overflow-auto rounded border bg-muted/30 p-2 font-mono text-[10px] space-y-0.5">
              {recentEvents.length === 0 && (
                <span className="text-muted-foreground">等待事件…</span>
              )}
              {recentEvents.map((evt, i) => (
                <div key={i} className="flex gap-2">
                  <span className="text-muted-foreground shrink-0">
                    {new Date(evt.timestamp * 1000).toLocaleTimeString()}
                  </span>
                  <span className="text-blue-500 shrink-0">[{evt.type}]</span>
                  <span className="text-muted-foreground shrink-0">
                    {evt.session_id.slice(0, 8)}…
                  </span>
                  <span className="truncate">{JSON.stringify(evt.payload)}</span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── 下半：最近系统活动 ── */}
      <Card className="flex-1 min-h-0 flex flex-col">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">📋 最近系统活动</CardTitle>
        </CardHeader>
        <CardContent className="pt-0 overflow-hidden flex-1">
          <ScrollArea className="h-full">
            {isLoading && (
              <div className="text-sm text-muted-foreground p-2">加载中…</div>
            )}
            {!isLoading && (!activities || activities.length === 0) && (
              <div className="text-sm text-muted-foreground p-2">暂无活动记录</div>
            )}
            <div className="space-y-1">
              {activities?.map((activity) => (
                <ActivityItem key={activity.id} activity={activity} />
              ))}
            </div>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  )
}
