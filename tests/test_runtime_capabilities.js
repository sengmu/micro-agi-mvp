const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'script.js'), 'utf8');
const capabilityCode = source.slice(0, source.indexOf("window.addEventListener('DOMContentLoaded'"));

function fixture(response) {
    const classes = new Set();
    const elements = new Map();
    const element = id => {
        if (!elements.has(id)) {
            elements.set(id, {
                placeholder: '输入消息，和日和聊天…',
                style: { setProperty() {} },
            });
        }
        return elements.get(id);
    };
    const context = {
        window: {},
        document: {
            getElementById: element,
            querySelector: () => null,
            documentElement: { classList: {
                add: name => classes.add(name),
                remove: name => classes.delete(name),
            } },
        },
        fetch: async () => response,
        console,
    };
    vm.runInNewContext(capabilityCode, context);
    return { context, classes, element };
}

test('unknown capability response keeps desktop-only controls hidden', async () => {
    for (const response of [
        { ok: false },
        { ok: true, json: async () => ({}) },
    ]) {
        const { context, classes, element } = fixture(response);
        assert.equal(classes.has('capabilities-pending'), true);
        await context.applyRuntimeCapabilities();
        assert.equal(context.window.microAgiEmbedded, null);
        assert.equal(classes.has('capabilities-pending'), true);
        assert.equal(element('chatInput').placeholder, '输入消息，和日和聊天…');
    }
});

test('confirmed desktop mode restores desktop controls and prompt', async () => {
    const { context, classes, element } = fixture({
        ok: true, json: async () => ({ embedded: false }),
    });
    await context.applyRuntimeCapabilities();
    assert.equal(context.window.microAgiEmbedded, false);
    assert.equal(classes.has('capabilities-pending'), false);
    assert.equal(classes.has('embedded-host'), false);
    assert.match(element('chatInput').placeholder, /控制指令/);
});

test('confirmed embedded mode retains standalone controls and disables uploads', async () => {
    const { context, classes, element } = fixture({
        ok: true, json: async () => ({ embedded: true }),
    });
    await context.applyRuntimeCapabilities();
    assert.equal(context.window.microAgiEmbedded, true);
    assert.equal(classes.has('capabilities-pending'), false);
    assert.equal(classes.has('embedded-host'), true);
    assert.equal(element('file-upload').disabled, true);
    assert.equal(element('chatInput').placeholder, '输入消息，和日和聊天…');
});
