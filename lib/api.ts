const API_BASE_URL =
    process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

type RequestOptions = {
    method?: "GET" | "POST";
    body?: unknown;
    token?: string | null;
};

export async function apiRequest<T>(
    path: string,
    options: RequestOptions = {},
): Promise<T> {
    const { method = "GET", body, token } = options;

    const response = await fetch(`${API_BASE_URL}${path}`, {
        method,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
    });

    if (!response.ok) {
        const text = await response.text();
        throw new Error(text || `Request failed: ${response.status}`);
    }

    return response.json() as Promise<T>;
}
