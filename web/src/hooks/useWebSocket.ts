import { useEffect, useRef, useState, useCallback } from "react"
import type { TraceEvent } from "@/types"
import { IS_TAURI } from "@/lib/tauri"

export function useWebSocket() {
  const [events, setEvents] = useState<TraceEvent[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const wsUrl = IS_TAURI
      ? "ws://localhost:18765/ws/events"
      : `${window.location.protocol === "https:" ? "wss:" : "ws:"}//${window.location.host}/ws/events`
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (msg) => {
      try {
        const evt: TraceEvent = JSON.parse(msg.data)
        setEvents((prev) => [...prev.slice(-499), evt])
      } catch {
        // ignore malformed
      }
    }

    return () => ws.close()
  }, [])

  const clear = useCallback(() => setEvents([]), [])

  return { events, connected, clear }
}
