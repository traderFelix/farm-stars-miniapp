"use client";

import { useEffect, useState } from "react";

import { authTelegram, clearAccessToken, getMyProfile, type Profile } from "@/lib/api";
import { getTelegramInitData, initTelegramMiniApp } from "@/lib/telegram";

type BootstrapState = "idle" | "loading" | "ready" | "error";

export default function HomePage() {
  const [bootstrapState, setBootstrapState] = useState<BootstrapState>("idle");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [debugMessage, setDebugMessage] = useState<string>("STEP 1: start");
  const [errorMessage, setErrorMessage] = useState<string>("");

  useEffect(() => {
    let cancelled = false;

    async function bootstrap() {
      try {
        setBootstrapState("loading");
        setErrorMessage("");
        setDebugMessage("STEP 1: start");

        initTelegramMiniApp();
        if (cancelled) return;

        setDebugMessage("STEP 2: telegram ready");

        const initData = getTelegramInitData();

        if (!initData) {
          // noinspection ExceptionCaughtLocallyJS
          throw new Error("Telegram initData is empty");
        }

        setDebugMessage("STEP 3: auth request");

        await authTelegram(initData);
        if (cancelled) return;

        setDebugMessage("STEP 4: profile request");

        const nextProfile = await getMyProfile();
        if (cancelled) return;

        setProfile(nextProfile);
        setBootstrapState("ready");
        setDebugMessage("STEP 5: ready");
      } catch (error) {
        if (cancelled) return;

        clearAccessToken();

        const message =
            error instanceof Error ? error.message : "Unknown bootstrap error";

        setBootstrapState("error");
        setErrorMessage(message);
        setDebugMessage(`BOOTSTRAP ERROR {"message":"${message}"}`);
      }
    }

    bootstrap();

    return () => {
      cancelled = true;
    };
  }, []);

  return (
      <main className="min-h-screen bg-black text-white">
        <div className="mx-auto flex min-h-screen w-full max-w-md flex-col px-4 py-6">
          <header className="mb-6">
            <div className="text-xs uppercase tracking-[0.2em] text-zinc-500">
              Felix Farm Stars
            </div>
            <h1 className="mt-2 text-2xl font-semibold">Главный экран</h1>
          </header>

          {bootstrapState === "loading" && (
              <section className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4 shadow-lg">
                <div className="text-sm text-zinc-400">Загрузка mini app...</div>
                <div className="mt-3 rounded-xl bg-zinc-900 p-3 text-sm text-zinc-300">
                  {debugMessage}
                </div>
              </section>
          )}

          {bootstrapState === "error" && (
              <section className="rounded-2xl border border-red-900 bg-zinc-950 p-4 shadow-lg">
                <div className="text-sm font-medium text-red-400">Ошибка загрузки</div>

                <div className="mt-3 rounded-xl bg-zinc-900 p-3 text-sm text-zinc-300">
                  {debugMessage}
                </div>

                <div className="mt-3 text-sm text-zinc-400">{errorMessage}</div>
              </section>
          )}

          {bootstrapState === "ready" && profile && (
              <div className="space-y-4">
                <section className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4 shadow-lg">
                  <div className="text-sm text-zinc-500">Профиль</div>

                  <div className="mt-4 space-y-3">
                    <Row label="User ID" value={String(profile.user_id)} />
                    <Row label="Имя" value={profile.first_name || "-"} />
                    <Row
                        label="Username"
                        value={profile.username ? `@${profile.username}` : "-"}
                    />
                    <Row label="Роль" value={profile.role || "-"} />
                  </div>
                </section>

                <section className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4 shadow-lg">
                  <div className="text-sm text-zinc-500">Баланс</div>

                  <div className="mt-3 text-3xl font-semibold">
                    {formatBalance(profile.balance)}⭐
                  </div>
                </section>

                <section className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4 shadow-lg">
                  <div className="text-sm text-zinc-500">Активность</div>

                  <div className="mt-3 text-2xl font-semibold">
                    {formatActivity(profile.activity_index)}
                  </div>
                </section>

                <section className="rounded-2xl border border-zinc-800 bg-zinc-950 p-4 shadow-lg">
                  <div className="text-sm text-zinc-500">Статус</div>

                  <div className="mt-3 rounded-xl bg-zinc-900 p-3 text-sm text-zinc-300">
                    {debugMessage}
                  </div>
                </section>
              </div>
          )}
        </div>
      </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
      <div className="flex items-center justify-between gap-3 rounded-xl bg-zinc-900 px-3 py-2">
        <div className="text-sm text-zinc-500">{label}</div>
        <div className="text-sm font-medium text-zinc-100">{value}</div>
      </div>
  );
}

function formatBalance(value: number): string {
  return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}

function formatActivity(value: number): string {
  const numeric = Number(value || 0);
  return `${numeric.toFixed(1)}%`;
}