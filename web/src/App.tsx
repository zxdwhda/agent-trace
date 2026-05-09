import { Routes, Route } from "react-router-dom"
import { Sidebar } from "@/components/layout/Sidebar"
import { Header } from "@/components/layout/Header"
import { DashboardPage } from "@/components/dashboard/DashboardPage"
import { SessionsPage } from "@/components/sessions/SessionsPage"
import { LivePage } from "@/components/live/LivePage"
import { SettingsPage } from "@/components/settings/SettingsPage"
import { ImportPage } from "@/components/import/ImportPage"
import { SkillsPage } from "@/components/skills/SkillsPage"
import { PromptSuggestionsPage } from "@/components/prompts/PromptSuggestionsPage"

function App() {
  return (
    <div className="flex h-screen w-screen bg-background text-foreground">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Header />
        <main className="flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/sessions" element={<SessionsPage />} />
            <Route path="/live" element={<LivePage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/import" element={<ImportPage />} />
            <Route path="/skills" element={<SkillsPage />} />
            <Route path="/prompts" element={<PromptSuggestionsPage />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}

export default App
