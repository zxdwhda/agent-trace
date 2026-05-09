import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { getSkillsAnalysis, type SkillAnalysis } from "@/lib/api"
import { Wrench, Layers, Hammer } from "lucide-react"

function formatNumber(n: number): string {
  return n.toLocaleString("en-US")
}

function SummaryCard({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string
  icon: React.ElementType
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between pb-2">
        <CardTitle className="text-sm font-medium">{label}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  )
}

function CallBar({ pct }: { pct: number }) {
  return (
    <div className="w-full">
      <div className="text-xs text-muted-foreground mb-1">{pct.toFixed(1)}%</div>
      <div className="h-2 w-full rounded-full bg-muted overflow-hidden">
        <div
          className="h-full rounded-full bg-primary transition-all"
          style={{ width: `${Math.min(pct, 100)}%` }}
        />
      </div>
    </div>
  )
}

export function SkillsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["skills-analysis"],
    queryFn: getSkillsAnalysis,
  })

  const skills: SkillAnalysis[] = data ?? []

  const totals = useMemo(() => {
    const totalSessions = skills.reduce((s, k) => s + k.total_sessions, 0)
    const totalCalls = skills.reduce((s, k) => s + k.total_calls, 0)
    return {
      totalSkills: skills.length,
      totalSessions,
      totalCalls,
    }
  }, [skills])

  const chartData = useMemo(
    () =>
      skills.map((s) => ({
        name: s.skill_name,
        calls: s.total_calls,
      })),
    [skills]
  )

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">技能分析</h1>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <SummaryCard
          label="技能种类"
          value={String(totals.totalSkills)}
          icon={Wrench}
        />
        <SummaryCard
          label="涉及会话"
          value={formatNumber(totals.totalSessions)}
          icon={Layers}
        />
        <SummaryCard
          label="总调用次数"
          value={formatNumber(totals.totalCalls)}
          icon={Hammer}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">技能明细</CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="text-sm text-muted-foreground py-8 text-center">
              加载中…
            </div>
          ) : skills.length === 0 ? (
            <div className="text-sm text-muted-foreground py-8 text-center">
              暂无技能数据（请先导入历史会话）
            </div>
          ) : (
            <div className="overflow-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>技能名称</TableHead>
                    <TableHead className="text-right">涉及会话</TableHead>
                    <TableHead className="text-right">总调用</TableHead>
                    <TableHead className="text-right">平均/会话</TableHead>
                    <TableHead className="w-40">调用占比</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {skills.map((skill) => {
                    const callPct =
                      totals.totalCalls > 0
                        ? (skill.total_calls / totals.totalCalls) * 100
                        : 0
                    return (
                      <TableRow key={skill.skill_name}>
                        <TableCell>
                          <Badge variant="secondary">{skill.skill_name}</Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {formatNumber(skill.total_sessions)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatNumber(skill.total_calls)}
                        </TableCell>
                        <TableCell className="text-right">
                          {skill.avg_calls_per_session.toFixed(1)}
                        </TableCell>
                        <TableCell>
                          <CallBar pct={callPct} />
                        </TableCell>
                      </TableRow>
                    )
                  })}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      {chartData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">各技能调用次数</CardTitle>
          </CardHeader>
          <CardContent>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
                <XAxis dataKey="name" className="text-xs" />
                <YAxis className="text-xs" />
                <Tooltip
                  formatter={(value: number) => [formatNumber(value), "调用次数"]}
                />
                <Bar dataKey="calls" fill="#8884d8" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
