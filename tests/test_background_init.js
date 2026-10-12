const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '..', 'script.js'), 'utf8');
const backgroundCode = source.slice(
    source.indexOf('function applyCustomBg('),
    source.indexOf('// Wardrobe UI Logic')
);

function fixture(initial = {}) {
    const values = new Map(Object.entries(initial));
    const elements = Object.fromEntries([
        ['bg-brightness-slider', { value: '50', max: '100' }],
        ['bg-blur-slider', { value: '0' }],
        ['bg-opacity-slider', { value: '60' }],
        ['bg-brightness-val', { textContent: '' }],
        ['bg-blur-val', { textContent: '' }],
        ['bg-opacity-val', { textContent: '' }],
        ['avatarCustomBg', { style: { setProperty() {}, backgroundImage: '' } }],
    ]);
    const classes = new Set();
    const context = {
        document: {
            documentElement: { classList: { contains: name => classes.has(name) } },
            getElementById: id => elements[id],
        },
        localStorage: {
            getItem: key => values.get(key) ?? null,
            setItem: (key, value) => values.set(key, value),
            removeItem: key => values.delete(key),
        },
        console,
    };
    vm.runInNewContext(backgroundCode, context);
    return { context, elements, classes, values };
}

test('embedded health transition replaces the dim legacy room defaults', () => {
    const { context, elements, classes, values } = fixture();
    context.loadAvatarBgSettings(); // DOMContentLoaded before async health response
    assert.equal(elements['bg-brightness-slider'].value, '50');
    classes.add('embedded-host');
    context.loadAvatarBgSettings(); // health response applies native mode
    assert.equal(elements['bg-brightness-slider'].value, '120');
    assert.equal(elements['bg-brightness-slider'].max, '150');
    assert.equal(elements['bg-opacity-slider'].value, '100');
    assert.equal(values.get('micro-agi-room-bg-v2'), '1');
    const hook = source.slice(source.indexOf('// Initialize Theme from localStorage'),
        source.indexOf('// --- Chat History Management System UI & Logic ---'));
    assert.match(hook, /await window\.microAgiCapabilitiesReady;\s*loadAvatarBgSettings\(\)/);
});

test('later brightness choices survive reload', () => {
    const { context, elements, classes, values } = fixture({
        'micro-agi-room-bg-v1': '1',
        'micro-agi-room-bg-v2': '1',
        'micro-agi-bg-settings': JSON.stringify({ brightness: '90', blur: '2', opacity: '80' }),
    });
    classes.add('embedded-host');
    context.loadAvatarBgSettings();
    assert.equal(elements['bg-brightness-slider'].value, '90');
    assert.equal(elements['bg-opacity-slider'].value, '80');
    assert.equal(values.get('micro-agi-room-bg-v2'), '1');
});

test('pre-migration room adjustments are not mistaken for legacy defaults', () => {
    const { context, elements, classes, values } = fixture({
        'micro-agi-room-bg-v1': '1',
        'micro-agi-bg-settings': JSON.stringify({ brightness: '90', blur: '2', opacity: '80' }),
    });
    classes.add('embedded-host');
    context.loadAvatarBgSettings();
    assert.equal(elements['bg-brightness-slider'].value, '90');
    assert.equal(elements['bg-opacity-slider'].value, '80');
    assert.equal(values.get('micro-agi-room-bg-v2'), '1');
});

test('pre-migration legacy 50/60 setting receives the brighter room default', () => {
    const { context, elements, classes } = fixture({
        'micro-agi-room-bg-v1': '1',
        'micro-agi-bg-settings': JSON.stringify({ brightness: '50', blur: '0', opacity: '60' }),
    });
    classes.add('embedded-host');
    context.loadAvatarBgSettings();
    assert.equal(elements['bg-brightness-slider'].value, '120');
    assert.equal(elements['bg-opacity-slider'].value, '100');
});

test('user-uploaded background is not migrated', () => {
    const { context, elements, classes, values } = fixture({
        'micro-agi-custom-bg': 'data:image/png;base64,example',
        'micro-agi-bg-settings': JSON.stringify({ brightness: '45', blur: '1', opacity: '65' }),
    });
    classes.add('embedded-host');
    context.loadAvatarBgSettings();
    assert.equal(elements['bg-brightness-slider'].value, '45');
    assert.equal(elements['bg-opacity-slider'].value, '65');
    assert.equal(values.get('micro-agi-room-bg-v2'), undefined);
});
