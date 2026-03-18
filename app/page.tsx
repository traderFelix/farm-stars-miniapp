import { AuthCard } from "@/components/home/AuthCard";
import { HistoryCard } from "@/components/home/HistoryCard";
import { ProfileCard } from "@/components/home/ProfileCard";
import { StartCard } from "@/components/home/StartCard";
import { TaskCard } from "@/components/home/TaskCard";

export default function HomePage() {
  return (
      <main className="min-h-dvh bg-app text-white">
        <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-4 pb-6 pt-safe-top">
          <header className="mb-6 pt-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70 backdrop-blur">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
              Step 8 · DB tasks + history
            </div>

            <h1 className="mt-4 text-3xl font-semibold tracking-tight">
              Felix Farm
            </h1>

            <p className="mt-2 max-w-sm text-sm leading-6 text-white/60">
              Убираем временную память, переносим задания в базу и добавляем
              историю.
            </p>
          </header>

          <StartCard />
          <AuthCard />
          <ProfileCard />
          <TaskCard />
          <HistoryCard />
        </div>
      </main>
  );
}