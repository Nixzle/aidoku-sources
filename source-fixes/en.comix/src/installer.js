// Discover Comix's current interceptor installer without depending on one new global.
function installComixInterceptors(root, requestToken, responseToken) {
    const MAX_MODULES = 32;
    const MAX_PROPERTIES = 256;
    const MAX_FUNCTIONS = 128;
    // This bounds discovery decisions; synchronous site code cannot be preempted here.
    const deadline = Date.now() + 5000;
    const seen = new Set();
    let modules = 0;
    let attempted = 0;
    const ownValue = (object, key) => {
        try {
            const descriptor = Object.getOwnPropertyDescriptor(object, key);
            return descriptor && Object.prototype.hasOwnProperty.call(descriptor, 'value')
                ? descriptor.value : undefined;
        } catch (_) { return undefined; }
    };
    let names;
    try { names = Object.getOwnPropertyNames(root); }
    catch (_) { return 'error: secure module discovery failed'; }
    for (const name of names) {
        if (Date.now() >= deadline) return 'error: interceptor discovery budget exceeded';
        if (!name.startsWith('vm')) continue;
        const module = ownValue(root, name);
        if (!module || module === root ||
            (typeof module !== 'object' && typeof module !== 'function')) continue;
        if (++modules > MAX_MODULES) return 'error: secure module discovery limit exceeded';
        let keys;
        try { keys = Object.getOwnPropertyNames(module); }
        catch (_) { continue; }
        if (keys.length > MAX_PROPERTIES) return 'error: secure module property limit exceeded';
        for (const key of keys) {
            if (Date.now() >= deadline) return 'error: interceptor discovery budget exceeded';
            const candidate = ownValue(module, key);
            if (typeof candidate !== 'function' || seen.has(candidate)) continue;
            if (++attempted > MAX_FUNCTIONS) return 'error: interceptor discovery limit exceeded';
            seen.add(candidate);
            let request;
            let response;
            const client = { interceptors: {
                request: { use(handler) { if (typeof handler === 'function') request = handler; return 0; } },
                response: { use(handler) { if (typeof handler === 'function') response = handler; return 0; } }
            } };
            let succeeded = true;
            try { Reflect.apply(candidate, module, [client]); }
            catch (_) { succeeded = false; }
            if (Date.now() >= deadline) return 'error: interceptor discovery budget exceeded';
            if (!succeeded) continue;
            if (typeof request !== 'function' || typeof response !== 'function') continue;
            try {
                Object.defineProperty(root, requestToken, { value: request, configurable: true, writable: true });
                Object.defineProperty(root, responseToken, { value: response, configurable: true, writable: true });
            } catch (_) { return 'error: interceptor storage failed'; }
            return 'ok';
        }
    }
    return modules === 0
        ? 'error: secure module object not found'
        : 'error: no installer registered both request and response interceptors';
}
