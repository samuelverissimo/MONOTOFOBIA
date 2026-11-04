'use strict';

const CACHE_NAME = 'monotofobia-static-v1';
const OFFLINE_PATH = '/__offline__';
const STATIC_ASSETS = [
    '/static/css/style.css',
    '/static/icons/monotofobia.svg',
    '/static/manifest.webmanifest',
];
const OFFLINE_PAGE = `<!doctype html>
<html lang="pt-br">
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Sem conexão | MONOTOFOBIA</title>
<main>
    <h1>Sem conexão</h1>
    <p>As páginas da mesa exigem conexão e autenticação. Reconecte-se para continuar.</p>
</main>
</html>`;

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then(async (cache) => {
            await cache.addAll(STATIC_ASSETS);
            await cache.put(
                OFFLINE_PATH,
                new Response(OFFLINE_PAGE, {
                    headers: { 'Content-Type': 'text/html; charset=utf-8' },
                }),
            );
            await self.skipWaiting();
        }),
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then(async (keys) => {
            await Promise.all(
                keys
                    .filter((key) => key.startsWith('monotofobia-') && key !== CACHE_NAME)
                    .map((key) => caches.delete(key)),
            );
            await self.clients.claim();
        }),
    );
});

self.addEventListener('fetch', (event) => {
    const request = event.request;
    const url = new URL(request.url);
    if (request.method !== 'GET' || url.origin !== self.location.origin) {
        return;
    }

    if (url.pathname.startsWith('/static/')) {
        event.respondWith(
            caches.match(request).then((cached) => {
                if (cached) {
                    return cached;
                }
                return fetch(request).then((response) => {
                    if (response.ok) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(request, copy));
                    }
                    return response;
                });
            }),
        );
        return;
    }

    if (request.mode === 'navigate') {
        event.respondWith(fetch(request).catch(() => caches.match(OFFLINE_PATH)));
    }
});
