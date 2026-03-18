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

    const url = path;

    console.log("REQUEST PATH =", path);
    console.log("FULL REQUEST URL =", url);

    const response = await fetch(url, {
        method,
        headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
        cache: "no-store",
    });

    console.log("RESPONSE STATUS =", response.status);

    if (!response.ok) {
        const text = await response.text();
        console.log("RESPONSE TEXT =", text);
        throw new Error(text || `Request failed: ${response.status}`);
    }

    return response.json() as Promise<T>;
}
