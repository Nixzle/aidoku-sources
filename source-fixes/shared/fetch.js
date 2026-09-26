async function aidokuFetch(url, headers) {
    const target = new URL(url);
    if (target.protocol !== 'https:' || target.origin !== location.origin || target.username || target.password) {
        throw new Error('Cross-origin or unsafe fallback request rejected');
    }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 12000);
    try {
        const response = await fetch(target.href, {
            method: 'GET', headers, credentials: 'include', redirect: 'error',
            cache: 'no-store', signal: controller.signal
        });
        const limit = 8 * 1024 * 1024;
        if (Number(response.headers.get('content-length')) > limit) throw new Error('Response too large');
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let size = 0, body = '';
        try {
            for (;;) {
                const next = await reader.read();
                if (next.done) break;
                size += next.value.byteLength;
                if (size > limit) throw new Error('Response too large');
                body += decoder.decode(next.value, {stream: true});
            }
            body += decoder.decode();
        } finally {
            await reader.cancel();
        }
        return JSON.stringify({body, status: response.status, url: target.href,
            x_enc: response.headers.get('x-enc'),
            challenge: response.headers.get('cf-mitigated') === 'challenge'});
    } finally {
        clearTimeout(timeout);
    }
}
