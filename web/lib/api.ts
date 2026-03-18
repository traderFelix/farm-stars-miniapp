const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL || "/backend";

type ApiRequestOptions = Omit<RequestInit, "body"> & {
    token?: string | null;
    body?: unknown;
};

export async function apiRequest<T>(
    path: string,
    options: ApiRequestOptions = {},
): Promise<T> {
    const { token, headers, body, ...rest } = options;

    const normalizedBody: BodyInit | undefined =
        body == null
            ? undefined
            : typeof body === "string" ||
            body instanceof FormData ||
            body instanceof URLSearchParams ||
            body instanceof Blob ||
            body instanceof ArrayBuffer
                ? body
                : JSON.stringify(body);

    const res = await fetch(`${API_BASE_URL}${path}`, {
        ...rest,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
            ...(headers || {}),
        },
        body: normalizedBody,
        cache: "no-store",
    });

    if (!res.ok) {
        throw new Error(`${options.method || "GET"} ${path} failed: ${res.status}`);
    }

    return res.json();
}

export async function apiGet<T>(path: string, token?: string): Promise<T> {
    return apiRequest<T>(path, { method: "GET", token });
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
    return apiRequest<T>(path, { method: "POST", body });
}