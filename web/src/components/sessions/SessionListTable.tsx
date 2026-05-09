import { useState, useMemo } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Input } from "@/components/ui/input"
import { Button } from "@/components/ui/button"
import { Search, ArrowUpDown, Trash2, Archive, ArchiveRestore } from "lucide-react"
import { deleteSession, archiveSession } from "@/lib/api"
import type { SessionInfo } from "@/types"

type SortKey = keyof SessionInfo | null
type SortDir = "asc" | "desc"

interface SessionListTableProps {
  sessions: SessionInfo[]
  onSelect: (session: SessionInfo) => void
  showArchived: boolean
  onToggleArchived: () => void
}

export function SessionListTable({ sessions, onSelect, showArchived, onToggleArchived }: SessionListTableProps) {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState("")
  const [sortKey, setSortKey] = useState<SortKey>("last_active")
  const [sortDir, setSortDir] = useState<SortDir>("desc")

  const deleteMutation = useMutation({
    mutationFn: (id: string) => deleteSession(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
    },
  })

  const archiveMutation = useMutation({
    mutationFn: ({ id, archived }: { id: string; archived: boolean }) => archiveSession(id, archived),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
    },
  })

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"))
    } else {
      setSortKey(key)
      setSortDir("asc")
    }
  }

  const filtered = useMemo(() => {
    const term = search.trim().toLowerCase()
    let rows = term
      ? sessions.filter(
          (s) =>
            s.session_id.toLowerCase().includes(term) ||
            (s.title || "").toLowerCase().includes(term) ||
            s.agent_type.toLowerCase().includes(term) ||
            s.model_name.toLowerCase().includes(term)
        )
      : [...sessions]

    if (sortKey) {
      rows.sort((a, b) => {
        const av = a[sortKey] ?? 0
        const bv = b[sortKey] ?? 0
        if (av < bv) return sortDir === "asc" ? -1 : 1
        if (av > bv) return sortDir === "asc" ? 1 : -1
        return 0
      })
    }
    return rows
  }, [sessions, search, sortKey, sortDir])

  const SortIcon = ({ colKey }: { colKey: SortKey }) => (
    <ArrowUpDown
      className={`ml-1 h-3 w-3 inline ${sortKey === colKey ? "text-foreground" : "text-muted-foreground opacity-50"}`}
    />
  )

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-2 top-2.5 h-4 w-4 text-muted-foreground" />
          <Input
            placeholder="搜索会话..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-8"
          />
        </div>
        <Button
          variant={showArchived ? "default" : "outline"}
          size="sm"
          onClick={onToggleArchived}
        >
          {showArchived ? "返回列表" : "回收站"}
        </Button>
      </div>

      <div className="rounded-lg border bg-card overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="cursor-pointer" onClick={() => handleSort("title")}>
                标题 <SortIcon colKey="title" />
              </TableHead>
              <TableHead className="cursor-pointer" onClick={() => handleSort("agent_type")}>
                Agent <SortIcon colKey="agent_type" />
              </TableHead>
              <TableHead className="cursor-pointer" onClick={() => handleSort("model_name")}>
                模型 <SortIcon colKey="model_name" />
              </TableHead>
              <TableHead className="cursor-pointer text-right" onClick={() => handleSort("total_tokens")}>
                Token <SortIcon colKey="total_tokens" />
              </TableHead>
              <TableHead className="cursor-pointer" onClick={() => handleSort("status")}>
                状态 <SortIcon colKey="status" />
              </TableHead>
              <TableHead className="cursor-pointer" onClick={() => handleSort("last_active")}>
                最后活跃 <SortIcon colKey="last_active" />
              </TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {filtered.length === 0 ? (
              <TableRow>
                <TableCell colSpan={7} className="text-center text-muted-foreground">
                  {showArchived ? "回收站为空" : "未找到会话"}
                </TableCell>
              </TableRow>
            ) : (
              filtered.map((session) => (
                <TableRow
                  key={session.session_id}
                  className="cursor-pointer"
                >
                  <TableCell onClick={() => onSelect(session)}>
                    <div className="font-medium text-sm max-w-[200px] truncate" title={session.title || session.session_id}>
                      {session.title || session.session_id.slice(0, 16) + "…"}
                    </div>
                    <div className="font-mono text-xs text-muted-foreground">
                      {session.session_id.slice(0, 12)}…
                    </div>
                  </TableCell>
                  <TableCell onClick={() => onSelect(session)}>{session.agent_type}</TableCell>
                  <TableCell className="font-mono text-xs" onClick={() => onSelect(session)}>
                    {session.model_name}
                  </TableCell>
                  <TableCell className="text-right tabular-nums" onClick={() => onSelect(session)}>
                    {session.total_tokens.toLocaleString()}
                  </TableCell>
                  <TableCell onClick={() => onSelect(session)}>
                    <span
                      className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                        session.status === "active"
                          ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                          : "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
                      }`}
                    >
                      {session.status === "active" ? "活跃中" : session.status === "historical" ? "历史" : "已结束"}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground" onClick={() => onSelect(session)}>
                    {session.last_active
                      ? new Date(session.last_active * 1000).toLocaleString()
                      : session.source === "active"
                        ? "活跃中"
                        : "—"}
                  </TableCell>
                  <TableCell className="text-right">
                    <div className="flex items-center justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => onSelect(session)}>
                        查看
                      </Button>
                      {showArchived ? (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => {
                            e.stopPropagation()
                            archiveMutation.mutate({ id: session.session_id, archived: false })
                          }}
                          title="恢复"
                        >
                          <ArchiveRestore className="h-4 w-4" />
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={(e) => {
                            e.stopPropagation()
                            archiveMutation.mutate({ id: session.session_id, archived: true })
                          }}
                          title="归档"
                        >
                          <Archive className="h-4 w-4" />
                        </Button>
                      )}
                      <Button
                        size="sm"
                        variant="ghost"
                        className="text-destructive hover:text-destructive"
                        onClick={(e) => {
                          e.stopPropagation()
                          if (confirm(`确定要删除会话 ${session.title || session.session_id.slice(0, 12)} 吗？`)) {
                            deleteMutation.mutate(session.session_id)
                          }
                        }}
                        title="删除"
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </div>
  )
}
