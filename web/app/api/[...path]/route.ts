import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.API_INTERNAL_BASE_URL || "http://127.0.0.1:8000";

async function proxyRequest(
    request: NextRequest,
    params: { path: string[] },
) {
    const path = params.path.join("/");
    const search = request.nextUrl.search || "";
    const targetUrl = `${API_BASE}/${path}${search}`;

    const headers = new Headers();
    const contentType = request.headers.get("content-type");
    const authorization = request.headers.get("authorization");
    const userAgent = request.headers.get("user-agent");
    const clientSession = request.headers.get("x-client-session");
    const forwardedFor = request.headers.get("x-forwarded-for");
    const realIp = request.headers.get("x-real-ip");
    const cfConnectingIp = request.headers.get("cf-connecting-ip");

    if (contentType) {
        headers.set("content-type", contentType);
    }

    if (authorization) {
        headers.set("authorization", authorization);
    }

    if (userAgent) {
        headers.set("user-agent", userAgent);
    }

    if (clientSession) {
        headers.set("x-client-session", clientSession);
    }

    if (forwardedFor) {
        headers.set("x-forwarded-for", forwardedFor);
    } else if (cfConnectingIp) {
        headers.set("x-forwarded-for", cfConnectingIp);
    } else if (realIp) {
        headers.set("x-forwarded-for", realIp);
    }

    if (realIp) {
        headers.set("x-real-ip", realIp);
    } else if (cfConnectingIp) {
        headers.set("x-real-ip", cfConnectingIp);
    }

    let body: BodyInit | undefined = undefined;

    if (request.method !== "GET" && request.method !== "HEAD") {
        body = await request.text();
    }

    const backendResponse = await fetch(targetUrl, {
        method: request.method,
        headers,
        body,
        cache: "no-store",
    });

    const responseText = await backendResponse.text();

    return new NextResponse(responseText, {
        status: backendResponse.status,
        headers: {
            "content-type":
                backendResponse.headers.get("content-type") || "application/json",
        },
    });
}

export async function GET(
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) {
    return proxyRequest(request, await context.params);
}

export async function POST(
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) {
    return proxyRequest(request, await context.params);
}

export async function PUT(
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) {
    return proxyRequest(request, await context.params);
}

export async function PATCH(
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) {
    return proxyRequest(request, await context.params);
}

export async function DELETE(
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) {
    return proxyRequest(request, await context.params);
}

export async function OPTIONS(
    request: NextRequest,
    context: { params: Promise<{ path: string[] }> },
) {
    return proxyRequest(request, await context.params);
}
