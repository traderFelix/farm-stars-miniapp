import type { StoredOpenedTask } from "@/lib/tasks";

const OPENED_TASK_KEY = "ffs_opened_task";

export function saveOpenedTask(data: StoredOpenedTask) {
    if (typeof window === "undefined") return;
    localStorage.setItem(OPENED_TASK_KEY, JSON.stringify(data));
}

export function getOpenedTask(): StoredOpenedTask | null {
    if (typeof window === "undefined") return null;

    const raw = localStorage.getItem(OPENED_TASK_KEY);
    if (!raw) return null;

    try {
        return JSON.parse(raw) as StoredOpenedTask;
    } catch {
        return null;
    }
}

export function clearOpenedTask() {
    if (typeof window === "undefined") return;
    localStorage.removeItem(OPENED_TASK_KEY);
}