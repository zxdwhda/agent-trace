import { useQuery } from "@tanstack/react-query"
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { getTokenStats } from "@/lib/api"

export function TokenTrendChart() {
  const { data } = useQuery({
    queryKey: ["token-stats"],
    queryFn: getTokenStats,
  })

  const chartData =
    data && data.timestamps.length > 0
      ? data.timestamps.map((hourOffset, i) => {
          const dt = new Date(Date.now() - (23 - hourOffset) * 3600 * 1000)
          return {
            time: dt.toLocaleTimeString("en-US", {
              hour: "2-digit",
              minute: "2-digit",
            }),
            input: data.input_tokens[i] ?? 0,
            output: data.output_tokens[i] ?? 0,
          }
        })
      : []

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Token 趋势</CardTitle>
      </CardHeader>
      <CardContent>
        {chartData.length === 0 ? (
          <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
            暂无数据
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={240}>
            <AreaChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" className="stroke-border" />
              <XAxis dataKey="time" className="text-xs" />
              <YAxis className="text-xs" />
              <Tooltip />
              <Area
                type="monotone"
                dataKey="input"
                stackId="1"
                stroke="#8884d8"
                fill="#8884d8"
                fillOpacity={0.6}
              />
              <Area
                type="monotone"
                dataKey="output"
                stackId="1"
                stroke="#82ca9d"
                fill="#82ca9d"
                fillOpacity={0.6}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  )
}
