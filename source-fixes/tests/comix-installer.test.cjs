'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const source = fs.readFileSync(path.join(__dirname, '../en.comix/src/installer.js'), 'utf8');
const install = vm.runInNewContext(source + '\ninstallComixInterceptors;', {}, { timeout: 1000 });
const requestToken = '__test_request__';
const responseToken = '__test_response__';
const discover = root => install(root, requestToken, responseToken);
function complete(client) {
    client.interceptors.request.use(request => request);
    client.interceptors.response.use(response => response);
}

test('discovers a complete installer among several existing and new VM modules', () => {
    let completeCalls = 0;
    const root = {
        vmUnrelated: { unrelated() {} },
        vmOld: { partial(client) { client.interceptors.request.use(value => value); } }
    };
    root.vmNew = { installer(client) { completeCalls++; complete(client); } };
    assert.equal(discover(root), 'ok');
    assert.equal(completeCalls, 1, 'selected installer must only run once');
    assert.equal(typeof root[requestToken], 'function');
    assert.equal(typeof root[responseToken], 'function');
});

test('finds nonenumerable existing modules and exports without invoking getters', () => {
    let getterCalls = 0;
    const module = {};
    Object.defineProperty(module, 'trap', { get() { getterCalls++; throw new Error('do not read'); } });
    Object.defineProperty(module, 'install', { value: complete });
    const root = {};
    Object.defineProperty(root, 'vmTrap', { get() { getterCalls++; throw new Error('do not read'); } });
    Object.defineProperty(root, 'vmExisting', { value: module });
    assert.equal(discover(root), 'ok');
    assert.equal(getterCalls, 0);
});

test('never combines request-only and response-only candidate registrations', () => {
    const root = {
        vmA: { requestOnly(client) { client.interceptors.request.use(value => value); } },
        vmB: { responseOnly(client) { client.interceptors.response.use(value => value); } }
    };
    assert.equal(discover(root), 'error: no installer registered both request and response interceptors');
    assert.equal(Object.hasOwn(root, requestToken), false);
    assert.equal(Object.hasOwn(root, responseToken), false);
});

test('requires callable handlers from a successful candidate invocation', () => {
    const root = { vmA: {
        invalid(client) {
            client.interceptors.request.use('not callable');
            client.interceptors.response.use(value => value);
        },
        throws(client) { complete(client); throw new Error('incomplete installation'); }
    } };
    assert.match(discover(root), /no installer registered both/);
    assert.equal(Object.hasOwn(root, requestToken), false);
    assert.equal(Object.hasOwn(root, responseToken), false);
});

test('deduplicates function aliases and proceeds after a failed candidate', () => {
    let failedCalls = 0;
    let selectedCalls = 0;
    const failed = client => { failedCalls++; client.interceptors.request.use(value => value); };
    const root = {
        vmA: { one: failed, alias: failed },
        vmB: { otherAlias: failed, selected(client) { selectedCalls++; complete(client); } }
    };
    assert.equal(discover(root), 'ok');
    assert.equal(failedCalls, 1);
    assert.equal(selectedCalls, 1);
});

test('stops after success and saves the handlers from that exact invocation', () => {
    const request = value => ({ signed: value });
    const response = value => ({ decoded: value });
    let calls = 0;
    let laterCalls = 0;
    const root = { vmA: {
        install(client) {
            calls++;
            client.interceptors.request.use(request);
            client.interceptors.response.use(response);
        },
        mustNotRun() { laterCalls++; }
    } };
    assert.equal(discover(root), 'ok');
    assert.equal(calls, 1);
    assert.equal(laterCalls, 0);
    assert.equal(root[requestToken], request);
    assert.equal(root[responseToken], response);
});

test('returns a specific missing-module error without inspecting inherited modules', () => {
    const root = Object.create({ vmInherited: { install: complete } });
    root.vmPrimitive = 42;
    root.vmSelf = root;
    assert.equal(discover(root), 'error: secure module object not found');
});

test('bounds callable discovery even when many plausible modules are present', () => {
    let calls = 0;
    const root = {};
    for (let moduleIndex = 0; moduleIndex < 4; moduleIndex++) {
        const module = {};
        for (let index = 0; index < 40; index++) module['candidate' + index] = () => { calls++; };
        root['vm' + moduleIndex] = module;
    }
    assert.equal(discover(root), 'error: interceptor discovery limit exceeded');
    assert.ok(calls > 0 && calls < 160);
    assert.equal(Object.hasOwn(root, requestToken), false);
});

test('bounds module and property discovery with distinguishable errors', () => {
    const root = {};
    for (let index = 0; index < 33; index++) root['vm' + index] = {};
    assert.equal(discover(root), 'error: secure module discovery limit exceeded');
    const large = {};
    for (let index = 0; index < 257; index++) large['item' + index] = index;
    assert.equal(discover({ vmLarge: large }), 'error: secure module property limit exceeded');
});

test('skips an uninspectable module and retains a specific root discovery error', () => {
    const bad = new Proxy({}, { ownKeys() { throw new Error('blocked metadata'); } });
    assert.equal(discover({ vmBad: bad, vmGood: { install: complete } }), 'ok');
    assert.equal(discover(bad), 'error: secure module discovery failed');
});

test('rejects handlers registered after the discovery time budget', () => {
    let clock = 0;
    const timedInstall = vm.runInNewContext(source + '\ninstallComixInterceptors;', {
        Date: { now: () => clock }
    }, { timeout: 1000 });
    let calls = 0;
    const root = { vmA: { slow(client) { calls++; complete(client); clock += 5001; } } };
    assert.equal(timedInstall(root, requestToken, responseToken), 'error: interceptor discovery budget exceeded');
    assert.equal(calls, 1);
    assert.equal(Object.hasOwn(root, requestToken), false);
    assert.equal(Object.hasOwn(root, responseToken), false);
});
