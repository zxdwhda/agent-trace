import { useState } from "react"
import { useQuery } from "@tanstack/react-query"
import { getSessions } from "@/lib/api"
import { SessionListTable } from "./SessionListTable"
import { SessionDetailPanel } from "./SessionDetailPanel"
import type { SessionInfo } from "@/types"

export function SessionsPage() {
  const [showArchived, setShowArchived] = useState(false)
  const { data: sessions = [], isLoading } = useQuery({
    queryKey: ["sessions", showArchived],
    queryFn: () => getSessions(showArchived),
  })

  const [selected, setSelected] = useState<SessionInfo | null>(null)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">
          {showArchived ? "回收站" : "会话列表"}
        </h1>
        <span className="text-sm text-muted-foreground">
          共 {sessions.length} 个会话
        </span>
      </div>

      {isLoading ? (
        <div className="h-[400px] animate-pulse rounded-lg bg-muted" />
      ) : (
        <SessionListTable
          sessions={sessions}
          onSelect={setSelected}
          showArchived={showArchived}
          onToggleArchived={() => setShowArchived((v) => !v)}
        />
      )}

      {selected && (
        <SessionDetailPanel
          session={selected}
          onClose={() => setSelected(null)}
        />
      )}
    </div>
  )
}
