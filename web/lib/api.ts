import type {
    TaskCheckRequest,
    TaskCheckResponse,
    TaskListItem,
    TaskOpenRequest,
    TaskOpenResponse,
} from "@/lib/tasks";

const ACCESS_TOKEN_KEY = "farmstars_access_token";

export type TelegramAuthResponse = {
    ok: boolean;
    token: string;
    session: {
        user_id: number;
        username?: string | null;
        first_name?: string | null;
    };
};

export type Profile = {
    user_id: number;
    username?: string | null;
    first_name?: string | null;
    balance: number;
    role: string;
    activity_index: number;
};

export type CheckinStatus = {
    can_claim: boolean;
    already_claimed_today: boolean;
    current_cycle_day: number;
    reward_today: number;
    next_cycle_day: number;
    next_reward: number;
    last_checkin_at?: string | null;
    server_time: string;
};

export type CheckinClaimResponse = {
    ok: boolean;
    claimed_amount: number;
    current_cycle_day: number;
    balance: number;
    claimed_at: string;
    message: string;
};

type RequestOptions = {
    method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
    body?: unknown;
    auth?: boolean;
};

function isBrowser(): boolean {
    return typeof window !== "undefined";
}

export function setAccessToken(token: string): void {
    if (!isBrowser()) return;
    localStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function getAccessToken(): string | null {
    if (!isBrowser()) return null;
    return localStorage.getItem(ACCESS_TOKEN_KEY);
}

export function clearAccessToken(): void {
    if (!isBrowser()) return;
    localStorage.removeItem(ACCESS_TOKEN_KEY);
}

function buildHeaders(auth: boolean, hasBody: boolean): HeadersInit {
    const headers: HeadersInit = {};

    if (hasBody) {
        headers["Content-Type"] = "application/json";
    }

    if (auth) {
        const token = getAccessToken();
        if (token) {
            headers["Authorization"] = `Bearer ${token}`;
        }
    }

    return headers;
}

async function apiRequest<T>(
    path: string,
    { method = "GET", body, auth = false }: RequestOptions = {},
): Promise<T> {
    const hasBody = body !== undefined;

    const response = await fetch(`/api${path}`, {
        method,
        headers: buildHeaders(auth, hasBody),
        body: hasBody ? JSON.stringify(body) : undefined,
        cache: "no-store",
    });

    let data: any;
    const contentType = response.headers.get("content-type") || "";

    if (contentType.includes("application/json")) {
        data = await response.json();
    } else {
        const text = await response.text();
        data = text ? { detail: text } : null;
    }

    if (!response.ok) {
        const message =
            data?.detail ||
            data?.message ||
            `Request failed with status ${response.status}`;
        throw new Error(message);
    }

    return data as T;
}

export async function authTelegram(
    initData: string,
): Promise<TelegramAuthResponse> {
    const result = await apiRequest<TelegramAuthResponse>("/auth/telegram", {
        method: "POST",
        body: {
            init_data: initData,
        },
        auth: false,
    });

    if (!result?.token) {
        throw new Error("Token was not returned by /auth/telegram");
    }

    setAccessToken(result.token);
    return result;
}

export async function getMyProfile(): Promise<Profile> {
    return apiRequest<Profile>("/profile/me", {
        method: "GET",
        auth: true,
    });
}

export async function getNextTask(): Promise<TaskListItem | null> {
    try {
        return await apiRequest<TaskListItem>("/tasks/next", {
            method: "GET",
            auth: true,
        });
    } catch (error) {
        const message = error instanceof Error ? error.message : "";
        if (message === "No available tasks") {
            return null;
        }
        throw error;
    }
}

export async function openTask(
    taskId: number,
    payload: TaskOpenRequest,
): Promise<TaskOpenResponse> {
    return apiRequest<TaskOpenResponse>(`/tasks/${taskId}/open`, {
        method: "POST",
        body: payload,
        auth: true,
    });
}

export async function checkTask(
    taskId: number,
    payload: TaskCheckRequest,
): Promise<TaskCheckResponse> {
    return apiRequest<TaskCheckResponse>(`/tasks/${taskId}/check`, {
        method: "POST",
        body: payload,
        auth: true,
    });
}

export async function getCheckinStatus(): Promise<CheckinStatus> {
    return apiRequest("/checkin/status", {
        method: "GET",
        auth: true,
    });
}

export async function claimCheckin(): Promise<CheckinClaimResponse> {
    return apiRequest("/checkin/claim", {
        method: "POST",
        auth: true,
    });
}