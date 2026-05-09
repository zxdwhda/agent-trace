import { Link, useLocation } from "react-router-dom"
import { LayoutDashboard, List, Radio, Settings, Upload, Wrench, Lightbulb } from "lucide-react"
import { cn } from "@/lib/utils"

const nav = [
  { path: "/", label: "总览", icon: LayoutDashboard },
  { path: "/sessions", label: "会话", icon: List },
  { path: "/live", label: "实时监控", icon: Radio },
  { path: "/import", label: "批量导入", icon: Upload },
  { path: "/skills", label: "技能分析", icon: Wrench },
  { path: "/prompts", label: "提示优化", icon: Lightbulb },
  { path: "/settings", label: "设置", icon: Settings },
]

export function Sidebar() {
  const location = useLocation()
  return (
    <aside className="w-56 border-r bg-card flex flex-col">
      <div className="h-14 flex items-center px-4 border-b font-semibold text-lg">
        AgentTrace
      </div>
      <nav className="flex-1 p-2 space-y-1">
        {nav.map((item) => {
          const active = location.pathname === item.path
          const Icon = item.icon
          return (
            <Link
              key={item.path}
              to={item.path}
              className={cn(
                "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                active
                  ? "bg-primary text-primary-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Icon className="h-4 w-4" />
              {item.label}
            </Link>
          )
        })}
      </nav>
    </aside>
  )
}
