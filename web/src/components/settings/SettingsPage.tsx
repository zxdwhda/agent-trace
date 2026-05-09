import { useState, useEffect } from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import { getConfig, updateConfig, type AppConfig } from "@/lib/api"

const DEFAULT_CONFIG: AppConfig = {
  coze_loop_mode: "official",
  workspace_id: "",
  api_token: "",
  opensource_url: "http://localhost:8082",
  poll_interval_seconds: 5,
  log_level: "INFO",
}

export function SettingsPage() {
  const queryClient = useQueryClient()

  const [config, setConfig] = useState<AppConfig>(DEFAULT_CONFIG)

  const { data: serverConfig } = useQuery({
    queryKey: ["config"],
    queryFn: getConfig,
  })

  useEffect(() => {
    if (serverConfig) {
      setConfig((prev) => ({ ...prev, ...serverConfig }))
    } else {
      // fallback to localStorage when API returns nothing
      try {
        const raw = localStorage.getItem("agenttrace:config")
        if (raw) {
          setConfig((prev) => ({ ...prev, ...JSON.parse(raw) }))
        }
      } catch {
        // ignore parse errors
      }
    }
  }, [serverConfig])

  const [saved, setSaved] = useState(false)

  const mutation = useMutation({
    mutationFn: updateConfig,
    onSuccess: () => {
      localStorage.setItem("agenttrace:config", JSON.stringify(config))
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
      queryClient.invalidateQueries({ queryKey: ["config"] })
    },
  })

  const handleChange = <K extends keyof AppConfig>(key: K, value: AppConfig[K]) => {
    setConfig((prev) => ({ ...prev, [key]: value }))
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    mutation.mutate(config)
  }

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-2xl font-bold">设置</h1>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">CozeLoop 配置</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">模式</label>
              <Select
                value={config.coze_loop_mode}
                onValueChange={(v) =>
                  handleChange("coze_loop_mode", v as AppConfig["coze_loop_mode"])
                }
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select mode" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="official">官方</SelectItem>
                  <SelectItem value="opensource">开源</SelectItem>
                  <SelectItem value="dual">双平台</SelectItem>
                </SelectContent>
              </Select>
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">Workspace ID</label>
              <Input
                value={config.workspace_id}
                onChange={(e) => handleChange("workspace_id", e.target.value)}
                placeholder="输入 Workspace ID"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">API Token</label>
              <Input
                type="password"
                value={config.api_token}
                onChange={(e) => handleChange("api_token", e.target.value)}
                placeholder="输入 API Token"
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">开源地址</label>
              <Input
                value={config.opensource_url}
                onChange={(e) => handleChange("opensource_url", e.target.value)}
                placeholder="http://localhost:8082"
              />
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">通用</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <label className="text-sm font-medium">轮询间隔 (秒)</label>
              <Input
                type="number"
                min={1}
                max={300}
                value={config.poll_interval_seconds}
                onChange={(e) =>
                  handleChange("poll_interval_seconds", Number(e.target.value))
                }
              />
            </div>

            <div className="space-y-2">
              <label className="text-sm font-medium">日志级别</label>
              <Select
                value={config.log_level}
                onValueChange={(v) => handleChange("log_level", v)}
              >
                <SelectTrigger>
                  <SelectValue placeholder="Select log level" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="DEBUG">DEBUG</SelectItem>
                  <SelectItem value="INFO">INFO</SelectItem>
                  <SelectItem value="WARNING">WARNING</SelectItem>
                  <SelectItem value="ERROR">ERROR</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? "保存中…" : "保存设置"}
          </Button>
          {saved && (
            <span className="text-sm text-green-600 dark:text-green-400">
              保存成功
            </span>
          )}
          {mutation.isError && (
            <span className="text-sm text-destructive">
              保存失败
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
