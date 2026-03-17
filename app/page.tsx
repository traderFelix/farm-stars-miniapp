import { AuthCard } from "@/components/home/AuthCard";
import { ProfileCard } from "@/components/home/ProfileCard";
import { StartCard } from "@/components/home/StartCard";

export default function HomePage() {
  return (
      <main className="min-h-dvh bg-app text-white">
        <div className="mx-auto flex min-h-dvh w-full max-w-md flex-col px-4 pb-6 pt-safe-top">
          <header className="mb-6 pt-4">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-white/70 backdrop-blur">
              <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
              Step 3 · Main Screen
            </div>

            <h1 className="mt-4 text-3xl font-semibold tracking-tight">
              Felix Farm
            </h1>

            <p className="mt-2 max-w-sm text-sm leading-6 text-white/60">
              Подключаем главный экран Mini App к backend и показываем реальные
              данные пользователя.
            </p>
          </header>

          <StartCard />
          <AuthCard />
          <ProfileCard />
        </div>
      </main>
  );
}
