export function formatBalance(value: number): string {
    return Number(value || 0)
        .toFixed(2)
        .replace(/\.00$/, "");
}

export function formatActivity(value: number): string {
    return `${Number(value || 0).toFixed(2)}%`;
}
