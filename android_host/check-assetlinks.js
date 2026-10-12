#!/usr/bin/env node
// Verify a local APK against a proposed Digital Asset Links file before upload.
// This script only reads local files. It does not contact or modify the website.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');

const projectRoot = path.resolve(__dirname, '..');
const apkPath = path.resolve(process.argv[2] || path.join(__dirname, 'app/build/outputs/apk/debug/app-debug.apk'));
const linksPath = path.resolve(process.argv[3] || path.join(__dirname, 'assetlinks.debug.example.json'));
const expectedPackage = process.argv[4] || 'cloud.relayhub.microagi.debug';
const remoteUrl = process.argv[5];
const sdkRoot = process.env.ANDROID_HOME || path.join(projectRoot, '.android-tools/android-home');
const buildToolsRoot = path.join(sdkRoot, 'build-tools');
const versions = fs.readdirSync(buildToolsRoot, { withFileTypes: true })
  .filter((entry) => entry.isDirectory())
  .map((entry) => entry.name)
  .sort((a, b) => b.localeCompare(a, undefined, { numeric: true }));
if (!versions.length) throw new Error('Android build-tools not found');
const toolsDir = path.join(buildToolsRoot, versions[0]);
const aapt = path.join(toolsDir, process.platform === 'win32' ? 'aapt2.exe' : 'aapt2');
const apksigner = path.join(toolsDir, 'lib', 'apksigner.jar');
const javaRoot = process.env.JAVA_HOME || path.join(projectRoot, '.android-tools/jdk/jdk-17.0.20.1+1');
const java = path.join(javaRoot, 'bin', process.platform === 'win32' ? 'java.exe' : 'java');

const badging = execFileSync(aapt, ['dump', 'badging', apkPath], { encoding: 'utf8' });
const packageName = /^package: name='([^']+)'/m.exec(badging)?.[1];
if (!packageName) throw new Error('APK package name not found');
if (packageName !== expectedPackage) {
  throw new Error(`Unexpected APK package ${packageName}; expected ${expectedPackage}`);
}
const signature = execFileSync(java, ['-jar', apksigner, 'verify', '--print-certs', apkPath], {
  encoding: 'utf8',
});
const digests = [...signature.matchAll(/Signer #\d+ certificate SHA-256 digest: ([0-9a-f]{64})/gi)]
  .map((match) => match[1].toUpperCase().match(/../g).join(':'));
if (!digests.length) throw new Error('APK has no verified signing certificate');

const entries = JSON.parse(fs.readFileSync(linksPath, 'utf8'));
function hasMatchingEntry(statements) {
  return Array.isArray(statements) && statements.some((entry) =>
    entry?.relation?.includes('delegate_permission/common.handle_all_urls') &&
    entry?.target?.namespace === 'android_app' &&
    entry?.target?.package_name === packageName &&
    Array.isArray(entry?.target?.sha256_cert_fingerprints) &&
    digests.some((digest) => entry.target.sha256_cert_fingerprints.includes(digest)));
}
if (!hasMatchingEntry(entries)) {
  throw new Error(`No matching package and signing certificate for ${packageName}`);
}
console.log(`Digital Asset Links matches ${packageName} (${digests.join(', ')})`);

if (remoteUrl) {
  const url = new URL(remoteUrl);
  if (url.protocol !== 'https:' || url.hostname !== 'relayhub.cloud' || url.port
      || url.pathname !== '/.well-known/assetlinks.json'
      || url.search || url.hash || url.username || url.password) {
    throw new Error('Remote URL must be https://relayhub.cloud/.well-known/assetlinks.json');
  }
  fetch(url, { redirect: 'manual', signal: AbortSignal.timeout(8000) }).then(async (response) => {
    if (response.status !== 200) throw new Error(`Remote assetlinks returned HTTP ${response.status}`);
    if (!/^application\/json(?:\s*;|$)/i.test(response.headers.get('content-type') || '')) {
      throw new Error('Remote assetlinks Content-Type must be application/json');
    }
    const body = await response.text();
    if (body.length > 65536) throw new Error('Remote assetlinks file exceeds 64 KiB');
    if (!hasMatchingEntry(JSON.parse(body))) {
      throw new Error(`Remote assetlinks does not match ${packageName} and its signing certificate`);
    }
    console.log(`Remote Digital Asset Links verified at ${url.origin}${url.pathname}`);
  }).catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}
