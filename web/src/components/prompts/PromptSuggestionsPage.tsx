import { useMemo } from "react"
import { useQuery } from "@tanstack/react-query"
import { Card, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { ScrollArea } from "@/components/ui/scroll-area"
import { getPromptSuggestions, type PromptSuggestion } from "@/lib/api"
import { Lightbulb, RefreshCw } from "lucide-react"

const severityOrder: Record<string, number> = {
  critical: 0,
  warning: 1,
  info: 2,
}

const severityBorder: Record<string, string> = {
  critical: "border-l-red-500",
  warning: "border-l-orange-500",
  info: "border-l-blue-500",
}

const severityBadge: Record<string, "default" | "secondary" | "destructive" | "outline"> = {
  critical: "destructive",
  warning: "secondary",
  info: "default",
}

function SuggestionCard({ suggestion }: { suggestion: PromptSuggestion }) {
  return (
    <Card
      className={`border-l-4 ${severityBorder[suggestion.severity] ?? "border-l-muted"}`}
    >
      <CardContent className="pt-4 pb-4 space-y-3">
        <div className="flex items-center gap-2 flex-wrap">
          <h3 className="font-semibold text-sm">{suggestion.title}</h3>
          <Badge variant={severityBadge[suggestion.severity] ?? "outline"}>
            {suggestion.severity}
          </Badge>
          <Badge variant="outline" className="text-muted-foreground">
            {suggestion.category}
          </Badge>
        </div>

        <p className="text-sm text-muted-foreground">{suggestion.description}</p>

        <div className="rounded-md bg-green-50 dark:bg-green-950/30 p-3">
          <div className="text-xs font-medium text-green-700 dark:text-green-400 mb-1">
            建议:
          </div>
          <p className="text-sm text-green-800 dark:text-green-300">
            {suggestion.suggestion}
          </p>
        </div>

        {suggestion.metric_value !== undefined && (
          <div className="text-xs text-muted-foreground">
            Metric: <span className="font-medium">{suggestion.metric_value}</span>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function PromptSuggestionsPage() {
  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["prompt-suggestions"],
    queryFn: getPromptSuggestions,
  })

  const suggestions: PromptSuggestion[] = data ?? []

  const grouped = useMemo(() => {
    const sorted = [...suggestions].sort(
      (a, b) => severityOrder[a.severity] - severityOrder[b.severity]
    )
    return sorted
  }, [suggestions])

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">提示词优化</h1>
        <Button
          variant="outline"
          size="sm"
          onClick={() => refetch()}
          disabled={isFetching}
        >
          <RefreshCw
            className={`h-4 w-4 mr-2 ${isFetching ? "animate-spin" : ""}`}
          />
          刷新
        </Button>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground py-8 text-center">
          加载建议中…
        </div>
      ) : grouped.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted-foreground">
          <Lightbulb className="h-8 w-8" />
          <p className="text-sm">No suggestions available. Everything looks good!</p>
        </div>
      ) : (
        <ScrollArea className="h-[calc(100vh-180px)]">
          <div className="space-y-4 pr-4">
            {grouped.map((s, i) => (
              <SuggestionCard key={`${s.title}-${i}`} suggestion={s} />
            ))}
          </div>
        </ScrollArea>
      )}
    </div>
  )
}
