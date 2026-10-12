const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'script.js'), 'utf8');
const speechCode = source.slice(source.indexOf('        function speakText(text)'),
    source.indexOf('        function startLipSync()'));

test('WebView without speech synthesis can stop speech before sending chat', () => {
    let lipSyncStops = 0;
    const context = {window: {}, isSpeaking: true, stopLipSync: () => { lipSyncStops++; }};
    vm.runInNewContext(speechCode, context);
    context.stopSpeech();
    context.speakText('A real model reply');
    assert.equal(context.isSpeaking, false);
    assert.equal(lipSyncStops, 2);
});

test('partial speech support does not fail text replies', () => {
    let cancels = 0;
    const context = {window: {speechSynthesis: {cancel: () => {cancels++;}}},
        isSpeaking: true, stopLipSync() {}};
    vm.runInNewContext(speechCode, context);
    context.speakText('Response with no utterance API');
    assert.equal(cancels, 1);
    assert.equal(context.isSpeaking, false);
});
