export type TaskType = "view_post";

export type TaskStatus =
    | "available"
    | "in_progress"
    | "completed"
    | "blocked";

export type TaskCheckStatus =
    | "completed"
    | "already_completed"
    | "too_early"
    | "rejected";

export type TaskListItem = {
    id: number;
    type: TaskType;
    title: string;
    description?: string | null;
    reward: number;

    status: TaskStatus;

    chat_id?: string | null;
    channel_post_id?: number | null;
    post_url?: string | null;

    already_completed: boolean;
    can_claim: boolean;
    hold_seconds: number;
};

export type TaskOpenRequest = {
    source?: string;
};

export type TaskOpenResponse = {
    ok: boolean;
    task_id: number;
    opened_at: number;
    hold_seconds: number;
    can_check_at: number;

    chat_id?: string | null;
    channel_post_id?: number | null;
    post_url?: string | null;

    session_id?: string | null;
};

export type TaskCheckRequest = {
    session_id?: string | null;
};

export type TaskCheckResponse = {
    ok: boolean;
    task_id: number;
    status: TaskCheckStatus;
    message: string;

    reward_granted: number;
    new_balance: number;
    task_completed: boolean;
};

export type StoredOpenedTask = {
    task_id: number;
    opened_at: number;
    hold_seconds: number;
    can_check_at: number;
    session_id?: string | null;
};