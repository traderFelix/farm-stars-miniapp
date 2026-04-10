export function formatBalance(value: number): string {
    return Number(value || 0)
        .toFixed(2)
        .replace(/\.00$/, "");
}

export function formatCompactBalance(value: number): string {
    return String(Number(Number(value || 0).toFixed(2)));
}

export function formatActivity(value: number): string {
    return `${Number(value || 0).toFixed(2)}%`;
}
