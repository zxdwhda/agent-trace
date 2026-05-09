/// <reference types="vite/client" />

declare module "@tauri-apps/api/core" {
  export function invoke<T>(cmd: string, args?: Record<string, unknown>): Promise<T>
}

declare module "@tauri-apps/api/app" {
  export function getVersion(): Promise<string>
}
