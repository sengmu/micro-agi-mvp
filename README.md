# Micro-AGI Companion

An Android AI companion prototype for Seeker, with an animated character, a floating desktop pet and native Solana Mobile Wallet Adapter integration.

## What the prototype implements

- A bundled Python backend starts inside the Android process through Chaquopy. No separate Termux service is needed for the Android build.
- The main WebView and floating character use an authenticated loopback service. Chat history stays in the app's private storage.
- Chat supports Gemini or an HTTPS OpenAI-compatible model endpoint with a user-provided API key. Chat requires a working key, provider availability and internet access. Prompts are sent to the configured model provider.
- A native MWA panel supports Devnet wallet authorization and disconnection. It does not expose transaction signing or token transfers.
- A separate read-only Devnet balance lookup accepts a public address. This lookup does not prove address ownership.

## Android build

Requires JDK 17, Android SDK 34 and Gradle 8.7. The wrapper downloads Gradle and the build downloads its declared dependencies.

Live2D Cubism Core and the Hiyori sample are third-party dependencies, omitted as standalone files from this source repository. Restore them locally from the functional prototype APK before building or running the complete regression suite:

```sh
python tools/prepare_live2d_assets.py --apk path/to/micro-agi-companion-debug.apk
```

Alternatively, supply these assets from the official [SDK download](https://www.live2d.com/en/sdk/download/web/) and [Hiyori sample](https://www.live2d.com/en/learn/sample/momose-hiyori/), under their applicable terms. Their paths are listed in `android_host/app/build.gradle`. Restored files are ignored by Git.

```sh
cd android_host
./gradlew :app:assembleDebug
```

The repository includes a Unix Gradle wrapper. On Windows, use an installed Gradle 8.7 with `gradle :app:assembleDebug` from `android_host`. The local Windows helper in this repository refers to the original development workstation's tools and is not a portable setup script.

Output: `android_host/app/build/outputs/apk/debug/app-debug.apk`.
Debug application ID: `cloud.relayhub.microagi.debug`. Android 8.0 or newer, arm64-v8a and x86_64.

## Try the APK

Download the tested prototype APK, English-captioned demo and pitch deck from the repository's **Releases** section. The APK does not contain model access credentials. The recorded demonstration uses a USB model relay; reviewers should configure their own reachable model service.

1. Install the debug APK and open Micro-AGI.
2. Open Settings, Connections, Model and save either a Gemini API Key or an HTTPS compatible endpoint, model ID and access key. The Android Google account login flow is not supported yet.
3. Send a short chat and confirm a complete response.
4. Grant the overlay permission when you choose to enable the floating pet. Use the app button or foreground notification to stop it.
5. Open the native wallet panel. Approve or reject authorization in your wallet yourself. This demo uses Devnet and requires no real funds.

## Checks

```sh
python -m unittest discover -s tests
node --test tests/test_background_init.js tests/test_runtime_capabilities.js tests/test_voice_capabilities.js
python android_host/verify-apk-contents.py android_host/app/build/outputs/apk/debug/app-debug.apk
```

## Prototype limits

The submitted debug build is a hackathon prototype. Release signing, production domain association, a complete device regression, model onboarding and dApp Store publication remain release work. SKR integration is not implemented. Desktop-only command execution, attachments and legacy login/update features are unavailable in the embedded Android mode.

This project existed before the submission sprint. The entrant must check the competition's rules for existing projects and disclose the work completed during the eligible period.

Third-party runtime and artwork rights are separate from the application's source. See THIRD_PARTY.md before redistribution or store publication.
