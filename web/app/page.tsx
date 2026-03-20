"use client";

import { useEffect, useMemo, useState } from "react";

import {
  authTelegram,
  checkTask,
  clearAccessToken,
  getMyProfile,
  getNextTask,
  openTask,
  type Profile,
} from "@/lib/api";
import { clearOpenedTask, getOpenedTask, saveOpenedTask } from "@/lib/opened-task";
import type { TaskCheckResponse, TaskListItem } from "@/lib/tasks";
import { getTelegramInitData, initTelegramMiniApp } from "@/lib/telegram";

type BootstrapState = "idle" | "loading" | "ready" | "error";
type TaskState = "idle" | "loading" | "ready" | "opening" | "opened" | "checking" | "done" | "empty" | "error";

export default function HomePage() {
  const [bootstrapState, setBootstrapState] = useState<BootstrapState>("idle");
  const [profile, setProfile] = useState<Profile | null>(null);
  const [task, setTask] = useState<TaskListItem | null>(null);
  const [taskState, setTaskState] = useState<TaskState>("idle");
  const [openedAt, setOpenedAt] = useState<number | null>(null);
  const [taskMessage, setTaskMessage] = useState<string>("");
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

        setDebugMessage("STEP 5: task request");
        await loadNextTask();

        if (cancelled) return;
        setBootstrapState("ready");
        setDebugMessage("STEP 6: ready");
      } catch (error) {
        if (cancelled) return;

        clearAccessToken();

        const message = error instanceof Error ? error.message : "Unknown bootstrap error";
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

  useEffect(() => {
    if (!task) {
      setOpenedAt(null);
      clearOpenedTask();
      return;
    }

    const stored = getOpenedTask();
    if (!stored) {
      setOpenedAt(null);
      return;
    }

    if (stored.task_id !== task.id) {
      clearOpenedTask();
      setOpenedAt(null);
      return;
    }

    setOpenedAt(stored.opened_at);
    setTaskState("opened");
  }, [task]);

  const elapsedSeconds = useElapsedSeconds(openedAt);
  const holdSeconds = task?.hold_seconds ?? 0;
  const remainingSeconds = useMemo(() => {
    return Math.max(0, holdSeconds - elapsedSeconds);
  }, [elapsedSeconds, holdSeconds]);

  const canCheck = Boolean(task && openedAt && remainingSeconds <= 0);

  async function loadNextTask() {
    setTaskState("loading");
    setTaskMessage("");

    const nextTask = await getNextTask();

    if (!nextTask) {
      setTask(null);
      clearOpenedTask();
      setOpenedAt(null);
      setTaskState("empty");
      return;
    }

    setTask(nextTask);
    setTaskState("ready");
  }

  async function handleOpenTask() {
    if (!task) return;

    try {
      setTaskState("opening");
      setTaskMessage("");

      const result = await openTask(task.id, {
        source: "miniapp",
      });

      if (!result.ok) {
        // noinspection ExceptionCaughtLocallyJS
        throw new Error("Не удалось открыть задание");
      }

      const openedTask = {
        task_id: result.task_id,
        opened_at: result.opened_at,
        hold_seconds: result.hold_seconds,
        session_id: result.session_id ?? null,
      };

      saveOpenedTask(openedTask);
      setOpenedAt(result.opened_at);
      setTaskState("opened");
      setTaskMessage("Пост открыт. Подожди нужное время и нажми проверить.");

      if (result.post_url) {
        window.open(result.post_url, "_blank", "noopener,noreferrer");
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка открытия задания";
      setTaskState("error");
      setTaskMessage(message);
    }
  }

  async function handleCheckTask() {
    if (!task) return;

    try {
      setTaskState("checking");
      setTaskMessage("");

      const stored = getOpenedTask();

      const result: TaskCheckResponse = await checkTask(task.id, {
        session_id: stored?.session_id ?? null,
      });

      setTaskMessage(result.message);

      if (result.status === "completed" || result.status === "already_completed") {
        clearOpenedTask();
        setOpenedAt(null);

        setProfile((prev) =>
            prev
                ? {
                  ...prev,
                  balance: Number(result.new_balance || prev.balance),
                }
                : prev,
        );

        await loadNextTask();
        setTaskState("done");
        return;
      }

      setTaskState("ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка проверки задания";
      setTaskState("error");
      setTaskMessage(message);
    }
  }

  return (
      <main className="min-h-screen bg-neutral-950 text-white">
        <div className="mx-auto flex min-h-screen w-full max-w-md flex-col gap-4 px-4 py-6">
          <header className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <div className="text-lg font-semibold">Felix Farm Stars</div>
            <div className="mt-1 text-sm text-white/60">Главный экран</div>
          </header>

          {bootstrapState === "loading" && (
              <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-base font-medium">Загрузка mini app...</div>
                <div className="mt-2 text-sm text-white/70">{debugMessage}</div>
              </section>
          )}

          {bootstrapState === "error" && (
              <section className="rounded-2xl border border-red-500/30 bg-red-500/10 p-4">
                <div className="text-base font-medium">Ошибка загрузки</div>
                <div className="mt-2 text-sm text-white/70">{debugMessage}</div>
                <div className="mt-2 text-sm text-red-200">{errorMessage}</div>
              </section>
          )}

          {bootstrapState === "ready" && profile && (
              <>
                <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="mb-3 text-base font-medium">Профиль</div>

                  <Row label="Баланс" value={`${formatBalance(profile.balance)}⭐`} />
                  <Row label="Активность" value={formatActivity(profile.activity_index)} />
                  <Row label="Роль" value={profile.role || "-"} />
                  <Row label="Статус" value={debugMessage} />
                </section>

                <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="mb-3 text-base font-medium">Задание</div>

                  {taskState === "loading" && (
                      <div className="text-sm text-white/70">Загружаю следующее задание...</div>
                  )}

                  {taskState === "empty" && (
                      <div className="text-sm text-white/70">Сейчас доступных заданий нет.</div>
                  )}

                  {task && taskState !== "loading" && (
                      <div className="space-y-3">
                        <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                          <div className="text-sm font-medium">{task.title}</div>
                          <div className="mt-1 text-sm text-white/60">
                            {task.description || "Открой пост и подержи нужное время"}
                          </div>

                          <div className="mt-3 grid grid-cols-2 gap-2 text-sm">
                            <Stat label="Награда" value={`${formatBalance(task.reward)}⭐`} />
                            <Stat label="Удержание" value={`${task.hold_seconds} сек`} />
                          </div>

                          {openedAt && (
                              <div className="mt-3 rounded-lg border border-white/10 bg-white/5 p-2 text-sm text-white/80">
                                {remainingSeconds > 0
                                    ? `Подожди еще ${remainingSeconds} сек`
                                    : "Можно проверять выполнение"}
                              </div>
                          )}
                        </div>

                        <div className="flex gap-2">
                          <button
                              type="button"
                              onClick={handleOpenTask}
                              disabled={taskState === "opening" || taskState === "checking"}
                              className="flex-1 rounded-xl bg-white px-4 py-3 text-sm font-medium text-black disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {taskState === "opening" ? "Открываю..." : "Открыть пост"}
                          </button>

                          <button
                              type="button"
                              onClick={handleCheckTask}
                              disabled={!canCheck || taskState === "checking"}
                              className="flex-1 rounded-xl border border-white/15 bg-white/10 px-4 py-3 text-sm font-medium text-white disabled:cursor-not-allowed disabled:opacity-60"
                          >
                            {taskState === "checking" ? "Проверяю..." : "Проверить"}
                          </button>
                        </div>

                        {taskMessage && (
                            <div className="text-sm text-white/75">{taskMessage}</div>
                        )}
                      </div>
                  )}
                </section>
              </>
          )}
        </div>
      </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
      <div className="flex items-center justify-between border-b border-white/10 py-2 last:border-b-0">
        <div className="text-sm text-white/60">{label}</div>
        <div className="text-sm font-medium text-white">{value}</div>
      </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
      <div className="rounded-lg border border-white/10 bg-white/5 p-2">
        <div className="text-xs text-white/50">{label}</div>
        <div className="mt-1 text-sm font-medium text-white">{value}</div>
      </div>
  );
}

function useElapsedSeconds(openedAt: number | null): number {
  const [now, setNow] = useState<number>(() => Math.floor(Date.now() / 1000));

  useEffect(() => {
    if (!openedAt) return;

    const timer = window.setInterval(() => {
      setNow(Math.floor(Date.now() / 1000));
    }, 1000);

    return () => {
      window.clearInterval(timer);
    };
  }, [openedAt]);

  if (!openedAt) return 0;
  return Math.max(0, now - openedAt);
}

function formatBalance(value: number): string {
  return Number(value || 0).toFixed(2).replace(/\.00$/, "");
}

function formatActivity(value: number): string {
  const numeric = Number(value || 0);
  return `${numeric.toFixed(1)}%`;
}