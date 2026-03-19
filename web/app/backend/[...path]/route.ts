import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.API_INTERNAL_BASE_URL || "http://127.0.0.1:8000";

async function proxy(
    req: NextRequest,
    ctx: { params: Promise<{ path: string[] }> }
) {
    const { path } = await ctx.params;
    const bodyText =
        req.method === "GET" || req.method === "HEAD" ? "" : await req.text();

    const target = `${API_BASE}/${path.join("/")}${req.nextUrl.search}`;

    console.log("PROXY IN:", {
        method: req.method,
        path,
        target,
        bodyText,
    });

    const headers = new Headers(req.headers);
    headers.delete("host");
    headers.delete("content-length");

    try {
        const res = await fetch(target, {
            method: req.method,
            headers,
            body:
                req.method === "GET" || req.method === "HEAD" ? undefined : bodyText,
            redirect: "manual",
        });

        console.log("PROXY OUT:", {
            status: res.status,
            target,
        });

        return new NextResponse(res.body, {
            status: res.status,
            headers: res.headers,
        });
    } catch (error) {
        console.error("PROXY ERROR:", error);
        return NextResponse.json(
            { detail: "proxy_failed", error: String(error) },
            { status: 500 }
        );
    }
}

export async function GET(
    req: NextRequest,
    ctx: { params: Promise<{ path: string[] }> }
) {
    return proxy(req, ctx);
}

export async function POST(
    req: NextRequest,
    ctx: { params: Promise<{ path: string[] }> }
) {
    return proxy(req, ctx);
}