import { SummaryCards } from "./SummaryCards"
import { TokenTrendChart } from "./TokenTrendChart"
import { ModelDistributionChart } from "./ModelDistributionChart"

export function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">总览面板</h1>
      <SummaryCards />
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TokenTrendChart />
        <ModelDistributionChart />
      </div>
    </div>
  )
}
