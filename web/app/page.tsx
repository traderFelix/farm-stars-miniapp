"use client";

import { useEffect, useMemo, useState } from "react";

import {
  authTelegram,
  checkTask,
  claimCheckin,
  clearAccessToken,
  getCheckinStatus,
  getMyProfile,
  getNextTask,
  openTask,
  type CheckinStatus,
  type Profile,
} from "@/lib/api";
import { clearOpenedTask, getOpenedTask, saveOpenedTask } from "@/lib/opened-task";
import type { TaskCheckResponse, TaskListItem } from "@/lib/tasks";
import { getTelegramInitData, initTelegramMiniApp } from "@/lib/telegram";
import WithdrawalPanel from "@/components/withdrawal/WithdrawalPanel";

type BootstrapState = "idle" | "loading" | "ready" | "error";

type TaskState =
    | "idle"
    | "loading"
    | "ready"
    | "opening"
    | "opened"
    | "checking"
    | "done"
    | "empty"
    | "error";

type CheckinState = "idle" | "loading" | "ready" | "claiming" | "error";

export default function HomePage() {
  const [bootstrapState, setBootstrapState] = useState<BootstrapState>("idle");
  const [profile, setProfile] = useState<Profile | null>(null);

  const [checkin, setCheckin] = useState<CheckinStatus | null>(null);
  const [checkinState, setCheckinState] = useState<CheckinState>("idle");
  const [checkinMessage, setCheckinMessage] = useState("");

  const [task, setTask] = useState<TaskListItem | null>(null);
  const [taskState, setTaskState] = useState<TaskState>("idle");
  const [openedAt, setOpenedAt] = useState<number | null>(null);
  const [taskMessage, setTaskMessage] = useState("");

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

        setDebugMessage("STEP 5: checkin request");
        await loadCheckinStatus({ preserveMessage: true });
        if (cancelled) return;

        setDebugMessage("STEP 6: task request");
        await loadNextTask();
        if (cancelled) return;

        setBootstrapState("ready");
        setDebugMessage("STEP 7: ready");
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

    if (task.already_completed || task.status === "completed") {
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
  const isTaskCompleted = Boolean(task?.already_completed || task?.status === "completed");

  async function loadCheckinStatus(options?: { preserveMessage?: boolean }) {
    setCheckinState("loading");
    if (!options?.preserveMessage) {
      setCheckinMessage("");
    }

    try {
      const status = await getCheckinStatus();
      setCheckin(status);
      setCheckinState("ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка загрузки daily bonus";
      setCheckin(null);
      setCheckinState("error");
      setCheckinMessage(message);
    }
  }

  async function handleClaimCheckin() {
    if (!checkin?.can_claim || checkinState === "claiming") return;

    try {
      setCheckinState("claiming");
      setCheckinMessage("");

      const result = await claimCheckin();

      setCheckinMessage(result.message);

      setProfile((prev) =>
          prev
              ? {
                ...prev,
                balance: Number(result.balance ?? prev.balance),
              }
              : prev,
      );

      await loadCheckinStatus({ preserveMessage: true });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка получения daily bonus";
      setCheckinState("error");
      setCheckinMessage(message);
    }
  }

  async function loadNextTask() {
    setTaskState("loading");
    setTaskMessage("");

    try {
      const nextTask = await getNextTask();

      if (!nextTask) {
        setTask(null);
        clearOpenedTask();
        setOpenedAt(null);
        setTaskState("empty");
        return;
      }

      setTask(nextTask);

      if (nextTask.already_completed || nextTask.status === "completed") {
        clearOpenedTask();
        setOpenedAt(null);
        setTaskState("done");
        setTaskMessage("Задание уже выполнено.");
        return;
      }

      setTaskState("ready");
    } catch (error) {
      const message = error instanceof Error ? error.message : "Ошибка загрузки задания";
      setTask(null);
      setTaskState("error");
      setTaskMessage(message);
    }
  }

  async function handleOpenTask() {
    if (!task || isTaskCompleted) return;

    try {
      setTaskState("opening");
      setTaskMessage("");

      const result = await openTask(task.id, {
        source: "miniapp",
      });

      if (!result.ok) {
        setTaskState("done");
        setTaskMessage("Задание уже недоступно или было выполнено ранее.");
        await loadNextTask();
        return;
      }

      const openedTask = {
        task_id: result.task_id,
        opened_at: result.opened_at,
        hold_seconds: result.hold_seconds,
        can_check_at: result.can_check_at,
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
    if (!task || isTaskCompleted) return;

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
        return;
      }

      if (result.status === "too_early") {
        setTaskState("opened");
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
      <main className="min-h-screen bg-neutral-950 px-4 py-5 text-white">
        <div className="mx-auto flex max-w-md flex-col gap-4">
          <header className="rounded-2xl border border-white/10 bg-white/5 p-4">
            <h1 className="text-xl font-semibold">Felix Farm Stars</h1>
            <p className="mt-1 text-sm text-white/60">Главный экран</p>
          </header>

          {bootstrapState === "loading" && (
              <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                <div className="text-sm font-medium">Загрузка mini app...</div>
                <div className="mt-2 text-xs text-white/60">{debugMessage}</div>
              </section>
          )}

          {bootstrapState === "error" && (
              <section className="rounded-2xl border border-red-500/30 bg-red-500/10 p-4">
                <div className="text-sm font-medium">Ошибка загрузки</div>
                <div className="mt-2 text-xs text-white/60">{debugMessage}</div>
                <div className="mt-2 text-sm text-red-200">{errorMessage}</div>
              </section>
          )}

          {bootstrapState === "ready" && profile && (
              <>
                <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <h2 className="text-sm font-semibold uppercase tracking-wide text-white/70">Профиль</h2>
                  <div className="mt-3 grid gap-3">
                    <Row label="ID" value={String(profile.user_id)} />
                    <Row label="Username" value={profile.username ? `@${profile.username}` : "-"} />
                    <Row label="Роль" value={profile.role || "пользователь"} />
                  </div>

                  <div className="mt-4 grid grid-cols-2 gap-3">
                    <Stat label="Баланс" value={`${formatBalance(profile.balance)} ⭐`} />
                    <Stat label="Активность" value={formatActivity(profile.activity_index)} />
                  </div>
                </section>

                <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-white/70">
                      Daily bonus
                    </h2>

                    <button
                        type="button"
                        onClick={() => loadCheckinStatus()}
                        className="text-xs text-white/60 transition hover:text-white"
                        disabled={checkinState === "loading" || checkinState === "claiming"}
                    >
                      Обновить
                    </button>
                  </div>

                  {checkinState === "loading" && (
                      <p className="mt-3 text-sm text-white/60">Загружаю статус daily bonus...</p>
                  )}

                  {checkinState === "error" && (
                      <div className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
                        {checkinMessage || "Не удалось загрузить daily bonus"}
                      </div>
                  )}

                  {checkin && checkinState !== "loading" && (
                      <>
                        <div className="mt-3 grid grid-cols-2 gap-3">
                          <Stat label="День цикла" value={String(checkin.current_cycle_day)} />
                          <Stat label="Сегодня" value={`${formatBalance(checkin.reward_today)} ⭐`} />
                          <Stat label="Завтра" value={`${formatBalance(checkin.next_reward)} ⭐`} />
                          <Stat
                              label="Статус"
                              value={checkin.can_claim ? "Можно забрать" : "Уже получено"}
                          />
                        </div>

                        <button
                            type="button"
                            onClick={handleClaimCheckin}
                            disabled={!checkin.can_claim || checkinState === "claiming"}
                            className="mt-4 w-full rounded-xl bg-white px-4 py-3 text-sm font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          {checkinState === "claiming" ? "Забираю..." : "Забрать бонус"}
                        </button>

                        {checkinMessage && (
                            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/80">
                              {checkinMessage}
                            </div>
                        )}
                      </>
                  )}
                </section>

                <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <WithdrawalPanel />
                </section>

                <section className="rounded-2xl border border-white/10 bg-white/5 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <h2 className="text-sm font-semibold uppercase tracking-wide text-white/70">
                      Задание
                    </h2>

                    <button
                        type="button"
                        onClick={loadNextTask}
                        className="text-xs text-white/60 transition hover:text-white"
                        disabled={taskState === "loading" || taskState === "opening" || taskState === "checking"}
                    >
                      Обновить
                    </button>
                  </div>

                  {taskState === "loading" && (
                      <p className="mt-3 text-sm text-white/60">Загружаю следующее задание...</p>
                  )}

                  {taskState === "empty" && (
                      <div className="mt-3">
                        <p className="text-sm text-white/70">Сейчас доступных заданий нет.</p>
                      </div>
                  )}

                  {taskState === "error" && taskMessage && (
                      <div className="mt-3 rounded-xl border border-red-500/30 bg-red-500/10 p-3 text-sm text-red-200">
                        {taskMessage}
                      </div>
                  )}

                  {task && taskState !== "loading" && taskState !== "empty" && (
                      <>
                        <div className="mt-3">
                          <div className="text-base font-medium">{task.title}</div>
                          <div className="mt-1 text-sm text-white/60">
                            {task.description || "Открой пост и подержи нужное время"}
                          </div>
                        </div>

                        {isTaskCompleted && (
                            <div className="mt-3 rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-200">
                              Задание уже выполнено
                            </div>
                        )}

                        {!isTaskCompleted && openedAt && (
                            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/80">
                              {remainingSeconds > 0
                                  ? `Подожди еще ${remainingSeconds} сек`
                                  : "Можно проверять выполнение"}
                            </div>
                        )}

                        {!isTaskCompleted && (
                            <div className="mt-4 grid grid-cols-2 gap-3">
                              <button
                                  type="button"
                                  onClick={handleOpenTask}
                                  disabled={taskState === "opening" || taskState === "checking"}
                                  className="rounded-xl bg-white px-4 py-3 text-sm font-medium text-black transition disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {taskState === "opening" ? "Открываю..." : "Открыть пост"}
                              </button>

                              <button
                                  type="button"
                                  onClick={handleCheckTask}
                                  disabled={!canCheck || taskState === "opening" || taskState === "checking"}
                                  className="rounded-xl border border-white/15 bg-transparent px-4 py-3 text-sm font-medium text-white transition disabled:cursor-not-allowed disabled:opacity-50"
                              >
                                {taskState === "checking" ? "Проверяю..." : "Проверить"}
                              </button>
                            </div>
                        )}

                        {isTaskCompleted && (
                            <button
                                type="button"
                                onClick={loadNextTask}
                                className="mt-4 w-full rounded-xl bg-white px-4 py-3 text-sm font-medium text-black transition"
                            >
                              Следующее задание
                            </button>
                        )}

                        {taskMessage && (
                            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-white/80">
                              {taskMessage}
                            </div>
                        )}
                      </>
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
      <div className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2">
        <span className="text-sm text-white/60">{label}</span>
        <span className="text-sm font-medium text-white">{value}</span>
      </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
      <div className="rounded-xl border border-white/10 bg-black/20 p-3">
        <div className="text-xs uppercase tracking-wide text-white/50">{label}</div>
        <div className="mt-1 text-base font-semibold text-white">{value}</div>
      </div>
  );
}

function useElapsedSeconds(openedAt: number | null): number {
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000));

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