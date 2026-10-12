# Micro-AGI Companion

## One-line description
An animated AI companion for Seeker, with a floating character and a native Solana wallet connection panel.

## Product description
Micro-AGI Companion brings an animated character to an Android chat experience. Users can talk with the companion in a room scene and keep a floating pet visible over other apps. The Android package runs its backend inside the app through Chaquopy, so users do not need to run a separate terminal service.

The prototype includes a native Solana Mobile Wallet Adapter panel for Devnet authorization and disconnection, plus a read-only public-address balance lookup. Wallet approval stays in the user's wallet. Transaction signing, token transfers and SKR rewards are future work.

Chat supports Gemini or an HTTPS compatible model service configured by the user. Chat history is stored in the app's private storage, while prompts are sent to the model provider. The entry is a prototype and requires model configuration before chat works.

## Intended users and return use
The initial audience is Seeker owners who want a personal character to accompany daily phone use. The core product hypothesis is that a persistent character and remembered conversation can make repeat use more inviting. Retention and product-market fit have not yet been measured.

## Technical implementation
Android Java/Kotlin host, Chaquopy embedded Python, a local authenticated HTTP service, WebView/Live2D presentation, SQLite conversation history and native Mobile Wallet Adapter integration. Overlay behavior uses Android's overlay permission and foreground service.

## Current status

The submitted demonstration records actual Seeker operation. The successful recorded chat uses a USB loopback relay to the configured model service. Direct public model access from the phone had a failure and remains unresolved. The video shows floating-pet activation and does not claim a completed wallet authorization or transaction.
The local regression suite has 121 passing Python tests and 10 passing JavaScript tests. The debug APK builds and installs on a connected Seeker. The entrant reports that the main room and character display correctly. The entrant confirmed a real chat response on Seeker. The latest wallet panel still requires device acceptance before final submission.

## Existing work disclosure
Micro-AGI is an existing project. A submission sprint began on October 12, 2026. The entrant must describe eligible-period development from their own records and confirm that the competition accepts this entry. Do not present the complete existing codebase as newly created during the sprint.

## Final links
Add the verified public GitHub URL, downloadable APK URL and actual device demo video URL to the competition form. Team identity and contact details must come from the entrant.

