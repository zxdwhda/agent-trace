export interface SessionInfo {
  session_id: string
  agent_type: string
  model_name: string
  title?: string
  turn_index: number
  total_input_tokens: number
  total_output_tokens: number
  total_tokens: number
  status: "active" | "ended" | "historical"
  trace_id?: string | null
  source: "active" | "db"
  archived?: boolean
  first_seen?: number
  last_active?: number
}

export interface TraceEvent {
  type: "turn_begin" | "step_begin" | "tool_call" | "tool_result" | "token_update" | "turn_end" | "content_part"
  session_id: string
  timestamp: number
  payload: Record<string, unknown>
}

export interface MonitorStats {
  active_sessions: number
  monitored_files: number
  total_turns_today: number
  total_tokens_today: number
  uptime_seconds: number
}

export interface TokenStats {
  timestamps: number[]
  input_tokens: number[]
  output_tokens: number[]
  models: Record<string, number>
}

export interface SpanNode {
  span_id: string
  span_name: string
  span_type: string
  parent_id: string
  started_at: number
  duration: number
  status: string
  input: string
  output: string
  tags_string?: Record<string, string>
  children?: SpanNode[]
}

export interface ActivityLog {
  id: number
  activity_type: string
  description: string
  metadata: Record<string, unknown>
  timestamp: number
}

export interface LiveMetrics {
  active_sessions: {
    session_id: string
    turn_index: number
    model_name: string
    agent_type: string
    user_input: string
    total_tokens: number
    elapsed_seconds: number
    has_root_span: boolean
    pending_tools: number
  }[]
  active_count: number
  token_throughput: {
    minute_offset: number
    input_tokens: number
    output_tokens: number
    total_tokens: number
    turns: number
  }[]
  skill_heatmap: {
    skill_name: string
    calls: number
  }[]
  daily: {
    total_tokens_today: number
    total_turns_today: number
  }
  timestamp: number
}
