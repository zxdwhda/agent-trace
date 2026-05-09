import { useQuery } from "@tanstack/react-query"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { ScrollArea } from "@/components/ui/scroll-area"
import { getSession } from "@/lib/api"
import type { SessionInfo, SpanNode } from "@/types"
import { ChevronRight, ChevronDown } from "lucide-react"
import { useState } from "react"

interface SessionDetailPanelProps {
  session: SessionInfo
  onClose: () => void
}

function SpanTreeNode({ node, depth = 0 }: { node: SpanNode; depth?: number }) {
  const [expanded, setExpanded] = useState(true)
  const hasChildren = node.children && node.children.length > 0

  const typeColor: Record<string, string> = {
    entry: "text-blue-600 dark:text-blue-400",
    agent: "text-emerald-600 dark:text-emerald-400",
    model: "text-purple-600 dark:text-purple-400",
    tool: "text-amber-600 dark:text-amber-400",
  }

  return (
    <div className="select-none">
      <div
        className="flex items-start gap-1 py-1 hover:bg-muted/50 rounded px-1"
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
      >
        {hasChildren ? (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="mt-0.5 text-muted-foreground hover:text-foreground"
          >
            {expanded ? (
              <ChevronDown className="h-3.5 w-3.5" />
            ) : (
              <ChevronRight className="h-3.5 w-3.5" />
            )}
          </button>
        ) : (
          <span className="w-3.5" />
        )}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 text-sm">
            <span className={`font-medium ${typeColor[node.span_type] || "text-foreground"}`}>
              {node.span_name}
            </span>
            <span className="text-xs text-muted-foreground">({node.span_type})</span>
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                node.status === "ok"
                  ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                  : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200"
              }`}
            >
              {node.status}
            </span>
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">
            {node.duration}ms · {new Date(node.started_at * 1000).toLocaleTimeString()}
          </div>
          {(node.input || node.output) && expanded && (
            <div className="mt-1 space-y-1">
              {node.input && (
                <div className="text-xs bg-muted rounded p-1.5 font-mono truncate" title={node.input}>
                  <span className="text-muted-foreground">输入:</span> {node.input}
                </div>
              )}
              {node.output && (
                <div className="text-xs bg-muted rounded p-1.5 font-mono truncate" title={node.output}>
                  <span className="text-muted-foreground">输出:</span> {node.output}
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      {hasChildren && expanded && (
        <div>
          {node.children!.map((child) => (
            <SpanTreeNode key={child.span_id} node={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export function SessionDetailPanel({ session, onClose }: SessionDetailPanelProps) {
  const { data, isLoading } = useQuery({
    queryKey: ["session", session.session_id],
    queryFn: () => getSession(session.session_id),
  })

  const spans = data?.trace_context?.span_tree ?? []

  return (
    <Dialog open onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[85vh] flex flex-col">
        <DialogHeader>
          <DialogTitle className="text-base">会话详情</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 overflow-hidden flex flex-col">
          <div className="rounded-lg border p-4 space-y-2 text-sm">
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-muted-foreground">会话 ID</span>
                <div className="font-mono text-xs">{session.session_id}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Agent</span>
                <div>{session.agent_type}</div>
              </div>
              <div>
                <span className="text-muted-foreground">模型</span>
                <div className="font-mono text-xs">{session.model_name}</div>
              </div>
              <div>
                <span className="text-muted-foreground">Token</span>
                <div className="tabular-nums">
                  {session.total_input_tokens.toLocaleString()} in /{" "}
                  {session.total_output_tokens.toLocaleString()} out
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">状态</span>
                <div>
                  <span
                    className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                      session.status === "active"
                        ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200"
                        : "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-200"
                    }`}
                  >
                    {session.status}
                  </span>
                </div>
              </div>
              <div>
                <span className="text-muted-foreground">轮次</span>
                <div>{session.turn_index}</div>
              </div>
            </div>
          </div>

          <div className="rounded-lg border flex-1 overflow-hidden flex flex-col min-h-[300px]">
            <div className="px-4 py-2 border-b bg-muted/30 text-sm font-medium">
              Trace 调用链
            </div>
            <ScrollArea className="flex-1 p-2">
              {isLoading ? (
                <div className="h-[200px] animate-pulse rounded bg-muted" />
              ) : spans.length === 0 ? (
                <div className="text-center text-sm text-muted-foreground py-8">
                  暂无 Trace 数据
                </div>
              ) : (
                <div>
                  {spans.map((span) => (
                    <SpanTreeNode key={span.span_id} node={span} />
                  ))}
                </div>
              )}
            </ScrollArea>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
