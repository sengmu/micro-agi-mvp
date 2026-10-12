# Wallet identity setup (relayhub.cloud)

The Android wallet screen uses `https://relayhub.cloud/` and relative icon path
`favicon.ico`, as approved by the domain owner. This is a Devnet test identity,
not proof that a wallet has verified the app.
The app declares a verified HTTPS App Link only for
`https://relayhub.cloud/micro-agi/open`, so it does not take over other site
pages. This route is an Android identity/deep-link entry; the app currently
opens its ordinary home screen when launched through it.

## Debug-device test

1. Review `assetlinks.debug.example.json`. It associates only
   `cloud.relayhub.microagi.debug` with the SHA-256 certificate of the local
   debug keystore. The current phone APK still uses the old package name, so
   this template must be checked against a **newly built** APK before upload.
   If the website already has an `assetlinks.json`, merge this entry
   rather than replacing existing associations.
2. Publish the reviewed JSON at
   `https://relayhub.cloud/.well-known/assetlinks.json` with HTTP 200 and
   `Content-Type: application/json`. Do this through the site's normal deployment
   process. Do not send hosting credentials or API tokens in chat.
3. Confirm `https://relayhub.cloud/favicon.ico` is reachable. If it changes,
   update `solana_icon_path` in `app/src/main/res/values/strings.xml` and rebuild.
4. After a fresh debug APK is built, run
   `node android_host/check-assetlinks.js <apk> <assetlinks.json> cloud.relayhub.microagi.debug`
   and verify that
   the package and signing certificate match. The checker is read-only.
   Add `https://relayhub.cloud/.well-known/assetlinks.json` as a final argument
   to also check the published HTTPS response, JSON content type, and association.
5. On an Android device with an MWA-compatible wallet, request connection and
   confirm the displayed name and URL in the wallet itself. Test approval,
   rejection, no wallet, disconnect, activity recreation, and process restart.
   Do not sign or transfer funds for this test.

## Release gate

The debug package and certificate are not the release identity. Before a release,
choose and protect a dedicated signing key, add a **separate** Digital Asset Links
entry for `cloud.relayhub.microagi` with the actual release APK certificate, configure and
verify Android App Links, and test wallet identity on-device. Never reuse the
debug fingerprint as the release fingerprint. Run the checker with `cloud.relayhub.microagi`
as the expected package for the release APK. The current release build is also
blocked until the temporary Live2D `unsafe-eval` CSP exception is removed.
