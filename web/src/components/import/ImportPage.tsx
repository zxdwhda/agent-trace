import { useState, useMemo } from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { previewImport, runImport, type ImportPreview, type ImportResult } from "@/lib/api"
import { FileSearch, Upload, CheckCircle, AlertCircle } from "lucide-react"

function formatDateInput(d: Date): string {
  return d.toISOString().split("T")[0]
}

export function ImportPage() {
  const queryClient = useQueryClient()
  const today = useMemo(() => new Date(), [])
  const weekAgo = useMemo(() => {
    const d = new Date()
    d.setDate(d.getDate() - 7)
    return d
  }, [])

  const [dateFrom, setDateFrom] = useState(formatDateInput(weekAgo))
  const [dateTo, setDateTo] = useState(formatDateInput(today))
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [result, setResult] = useState<ImportResult | null>(null)

  const previewMutation = useMutation({
    mutationFn: () => previewImport(dateFrom, dateTo),
    onSuccess: (data) => {
      setPreview(data)
      setResult(null)
    },
  })

  const importMutation = useMutation({
    mutationFn: () => runImport(dateFrom, dateTo),
    onSuccess: (data) => {
      setResult(data)
      // 导入成功后刷新所有相关数据
      queryClient.invalidateQueries({ queryKey: ["sessions"] })
      queryClient.invalidateQueries({ queryKey: ["skills-analysis"] })
      queryClient.invalidateQueries({ queryKey: ["token-stats"] })
      queryClient.invalidateQueries({ queryKey: ["status"] })
    },
  })

  const canImport = preview ? preview.new_sessions > 0 : false

  return (
    <div className="space-y-6 max-w-3xl">
      <h1 className="text-2xl font-bold">批量导入</h1>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">选择日期范围</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">开始</label>
              <Input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium">结束</label>
              <Input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
              />
            </div>
          </div>

          <Button
            onClick={() => previewMutation.mutate()}
            disabled={previewMutation.isPending || !dateFrom || !dateTo}
          >
            <FileSearch className="h-4 w-4 mr-2" />
            {previewMutation.isPending ? "分析中…" : "预览"}
          </Button>

          {previewMutation.isError && (
            <div className="flex items-center gap-2 text-sm text-destructive">
              <AlertCircle className="h-4 w-4" />
              预览失败，请重试。
            </div>
          )}
        </CardContent>
      </Card>

      {preview && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base">预览结果</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">扫描文件</div>
                <div className="text-xl font-bold">{preview.total_files}</div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">总会话</div>
                <div className="text-xl font-bold">{preview.total_sessions}</div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">已存在 (跳过)</div>
                <div className="text-xl font-bold text-muted-foreground">
                  {preview.existing_sessions}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">新会话</div>
                <div className="text-xl font-bold text-green-600 dark:text-green-400">
                  {preview.new_sessions}
                </div>
              </div>
              <div className="space-y-1 col-span-2">
                <div className="text-sm text-muted-foreground">日期范围</div>
                <div className="text-sm font-medium">
                  {preview.date_range.from} → {preview.date_range.to}
                </div>
              </div>
            </div>

            <Button
              onClick={() => importMutation.mutate()}
              disabled={importMutation.isPending || !canImport}
            >
              <Upload className="h-4 w-4 mr-2" />
              {importMutation.isPending ? "导入中…" : "立即导入"}
            </Button>
          </CardContent>
        </Card>
      )}

      {result && (
        <Card>
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <CheckCircle className="h-5 w-5 text-green-600 dark:text-green-400" />
              导入完成
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">已导入</div>
                <div className="text-xl font-bold text-green-600 dark:text-green-400">
                  {result.imported}
                </div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">已跳过</div>
                <div className="text-xl font-bold">{result.skipped}</div>
              </div>
              <div className="space-y-1">
                <div className="text-sm text-muted-foreground">错误</div>
                <div
                  className={`text-xl font-bold ${
                    result.errors.length > 0
                      ? "text-destructive"
                      : "text-muted-foreground"
                  }`}
                >
                  {result.errors.length}
                </div>
              </div>
            </div>

            {result.errors.length > 0 && (
              <div className="rounded-md bg-destructive/10 p-3 space-y-1">
                <div className="text-sm font-medium text-destructive">错误:</div>
                <ul className="text-sm text-destructive space-y-1 list-disc list-inside">
                  {result.errors.map((err, i) => (
                    <li key={i}>{err}</li>
                  ))}
                </ul>
              </div>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  )
}
