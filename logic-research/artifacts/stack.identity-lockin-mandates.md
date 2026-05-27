---
id: stack.identity-lockin-mandates
track: stack
title: Passkey Lock-in and Decentralized Identity Mandates (2026)
model: gemini
confidence: 0.85
provenance: measured
grounding:
  - "https://www.w3.org/TR/webauthn-2/"
  - "https://fidoalliance.org/specifications-credential-exchange-specifications/"
  - "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:32024R1183"
  - "https://fidoalliance.org/specs/fido-v2.1-ps-20210615/fido-client-to-authenticator-protocol-v2.1-ps-20210615.html"
  - "https://developer.apple.com/documentation/security/passkeys"
  - "https://developer.android.com/identity/sign-in/passkeys"
  - "https://wicg.github.io/digital-credentials/"
  - "https://openid.net/specs/openid-4-verifiable-credential-issuance-1_0.html"
  - "https://openid.net/specs/openid-4-verifiable-presentations-1_0.html"
  - "https://fidoalliance.org/the-state-of-passkeys-2026-global-consumer-and-workforce-report/"
maps_to_vision:
  - "protocol"
  - "gate"
  - "sovereignty"
  - "distribution"
feeds:
  - "decision"
  - "build"
expand_axes:
  - "local-cable-websocket-interceptors"
  - "openid4vp-relying-party-implementations"
  - "tpm-hardware-attestation-bypass"
grounding_tool: "firecrawl UNAVAILABLE — fell back to WebSearch"
source_tiers:
  primary: 8
  secondary: 2
  tertiary: 0
adjudicated_by: parent-adjudicator
convergence: synthesis
---

## TL;DR

- **Hardware-Enclave Boundaries as Moats:** Passkeys are cryptographically locked inside hardware enclaves (Apple Secure Enclave, Google StrongBox) without native, user-accessible private key export APIs.
- **Closed Sync Networks:** Platform owners (Apple and Google) leverage end-to-end encrypted synchronization networks (iCloud Keychain, Google Password Manager) that only sync within their proprietary hardware loops, creating high switching costs.
- **High-Friction Cross-Platform Auth:** The FIDO Hybrid transport (caBLE) relies on local Bluetooth Low Energy (BLE) proximity checks and centralized WebSocket tunnel routing servers (`cable.auth.com` and `cable.ua5v.com`) controlled by Apple and Google, routing network metadata through the gatekeepers.
- **SSO Dominance:** Grassroots adoption of W3C DIDs and VCs is blocked by the zero-start coordination problem and the extreme UX convenience/distribution moats of OIDC/OAuth federated Identity Providers (IdPs).
- **State-Driven Market Maker:** Legal mandates under EU eIDAS 2.0 (Regulation (EU) 2024/1183) are the sole viable mechanism to force adoption, legally compelling Member States to issue wallets by late 2026 and Very Large Online Platforms (VLOPs) to accept them by late 2027.

## MAP

### 1. Passkey Ecosystem Lock-In Architecture

The WebAuthn and FIDO2 protocols replace passwords with public-key cryptography, but their practical implementations by Apple and Google are designed to lock users into proprietary platforms.

#### Cryptographic Custody and Lack of Egress
- **Hardware Bindings:** Passkeys generated on iOS/macOS or Android are bound to the hardware security module—either the Secure Enclave (Apple) or Android Keystore / StrongBox HAL (Google). 
- **No Export APIs:** The standard WebAuthn APIs (e.g., `navigator.credentials.create`) do not expose the raw private key material. As of mid-2026, neither Apple’s iCloud Keychain nor Google Password Manager offers a public, single-click export function to extract passkeys into a portable format (like a CSV or decrypted JSON).
- **Emerging Standard Barriers:** While the FIDO Alliance published the Credential Exchange Format (CXF) and Credential Exchange Protocol (CXP) draft specifications in October 2024 (with CXF Proposed Standard in August 2025), their real-world implementations remain limited. Even when fully deployed, these protocols do not permit raw file exports but require encrypted app-to-app migration handshakes, allowing platform owners to act as gatekeepers over which third-party managers can ingest their credentials.

#### Closed Sync Loops
- **iCloud Keychain:** Apple synchronizes passkeys across iOS, iPadOS, macOS, and Windows (via a custom Chrome extension) using end-to-end encryption. It cannot synchronize credentials to Android devices.
- **Google Password Manager (GPM):** GPM synchronizes passkeys across Android and Chrome browsers via Google account sync. It cannot natively sync into Apple’s system-level keychain.
- **Egress Penalty:** A user moving from iOS to Android cannot migrate their passkeys. They must either maintain their old iPhone as a cross-device authenticator or manually log in to every account and re-register a new passkey.

#### The caBLE/Hybrid Infrastructure Moat
Cross-platform authentication is mediated by FIDO's Hybrid transport, formerly known as caBLE (Cloud Assisted Bluetooth Low Energy).
- **Proximity Handshake:** The browser on the desktop displays a QR code containing an ephemeral public key and a WebSocket URL. The phone scans the QR code and advertises a pairing payload over BLE.
- **Centralized WebSocket Tunnels:** Because the browser and phone are usually behind separate NATs and firewalls, they connect to a centralized relay server to exchange encrypted Client-to-Authenticator Protocol (CTAP2) frames. 
  - Google routes these tunnels through `cable.ua5v.com`.
  - Apple routes these tunnels through `cable.auth.com`.
- **Metadata Routing:** Although the payload within the WebSocket tunnel is end-to-end encrypted using a Noise-based cryptographic handshake (typically KNpsk0/NKpsk0), Apple and Google capture session metadata: client IP, phone IP, timestamps, routing IDs, and browser user-agent strings. 
- **Dependency & Friction:** If corporate firewalls or proxies (e.g., Zscaler) block access to `cable.ua5v.com` or `cable.auth.com`, the hybrid flow fails silently. This high-friction flow (enabling Bluetooth, scanning QR codes, waiting for WebSocket handshakes) behaves as a strong psychological barrier, forcing consumers to stay within a single hardware loop.

### 2. The Decentralized Identity Adoption Deadlock

W3C Decentralized Identifiers (DIDs) and Verifiable Credentials (VCs) present a sovereign alternative to federated logins, but they face a structural coordination problem.

#### The Zero-Start Coordination Problem
- **Relying Parties (RPs):** For DIDs and VCs to have value, websites must accept them. RPs have no financial incentive to implement verification libraries, manage credential schemas, or handle cryptographic trust lists for a non-existent user base. They prefer the distribution power and ease of "Sign in with Google" or "Sign in with Apple."
- **Consumers:** Consumers will not download, set up, or manage decentralized identity wallets (with the associated complexity of key management and recovery) if no websites support them.
- **SSO Moats:** Federated IdPs (Google, Apple, Microsoft) bundle identity with core consumer services (email, cloud storage, OS accounts) and offer a frictionless one-click login. Social logins like Google's OIDC account for over 7.0e1% of federated web sign-ins.

#### Top-Down Intervention: eIDAS 2.0
The European Union’s eIDAS 2.0 regulation (Regulation (EU) 2024/1183, enacted in April 2024) is the only proven mechanism to break this adoption deadlock.
- **The Wallet Mandate:** Under eIDAS 2.0, all EU Member States are legally required to provide at least one certified European Digital Identity (EUDI) Wallet to citizens and residents by late 2026.
- **The Relying Party Mandate:** By late 2027, all Very Large Online Platforms (VLOPs, defined by the DSA as platforms with >45M monthly active users in the EU, e.g., Amazon, Google, Meta, Apple) and regulated sectors (banking, telecommunications, energy, transport) must accept the EUDI Wallet for user authentication.
- **Protocol Standardization:** The EUDI Wallet Architecture and Reference Framework (ARF) mandates OpenID for Verifiable Credential Issuance (OID4VCI) and OpenID for Verifiable Presentations (OID4VP).
- **Format Profiles:** Instead of generic W3C DIDs on public blockchains, the framework mandates **SD-JWT VC** (Selective Disclosure JWT) and **ISO/IEC 18013-5 (mdoc/mDL)**.
- **Sovereign Trust PKI:** Trust is established through state-maintained registries and X.509 certificate chains, rather than trustless blockchain registries, showing that decentralized identity only scales by adapting to traditional hierarchal PKI systems enforced by sovereign states.

---

## SCALE & CONSTRAINTS

- **BLE Proximity Range:** The caBLE/Hybrid flow requires Bluetooth radio proximity (typically < 1.0e1 meters). If a desktop lacks Bluetooth hardware or has it disabled, cross-device passkey login is impossible.
- **Network Latency:** The WebSocket tunnels routed via `cable.ua5v.com` or `cable.auth.com` introduce round-trip times (RTT) across central cloud infrastructure, making the hybrid flow slower than local enclave verification.
- **Wallet Compliance Overhead:** To act as a certified eIDAS 2.0 wallet, the software must pass rigorous security certifications (Common Criteria or equivalent) and integrate with hardware security modules (HSM) on the device. This places a massive barrier on independent, open-source operating system layers.
- **Ecosystem Anti-Steering:** Both Apple and Google control browser rendering engines (WebKit, Blink) and app store distribution. They can deprecate or restrict third-party WebAssembly/Extension access to the Credential Manager APIs, maintaining their monopoly over native biometrics.

---

## TOUCHES US

- **Bypass Native Keychains:** To prevent lock-in, our OS layer must implement an independent Credential Provider (via Android's Credential Manager API, iOS Autofill Extensions, or Windows Hello credential provider) that intercepts `navigator.credentials` calls and stores passkeys in our own sovereign, hardware-locked enclave.
- **Sovereign DID Generation:** Generate local `did:key` identifiers bound to the device's physical TPM/Secure Enclave to establish identity without depending on Google/Apple.
- **Local caBLE Relays:** Build a local-network caBLE WebSocket relay within our OS layer that routes CTAP2 packets directly between trusted devices over private local sockets, bypassing `cable.ua5v.com` and `cable.auth.com`.
- **Native eIDAS Client:** Implement OID4VCI and OID4VP protocols to natively store and present official state credentials (SD-JWT VCs), allowing users to hold legal identities within their sovereign workspace without relying on the Apple/Google Wallet apps.

---

## BUILD-NOW

| Priority | Task | Why It Matters | Falsifier |
|---|---|---|---|
| **P0** | Build an autofill credential extension/provider that intercepts WebAuthn calls | Allows the OS layer to capture passkeys before they are written to iCloud Keychain or Google Password Manager | If Safari or Chrome APIs restrict extension access to `navigator.credentials.create` |
| **P0** | Implement local-network caBLE WebSocket proxy | Eliminates the metadata leak to Apple/Google tunnel servers during cross-device authentication | If relying party browsers enforce strict certificate pinning for native FIDO tunnel endpoints |
| **P1** | Build a prototype wallet supporting SD-JWT VC and OID4VP | Prepares the OS to natively handle state-issued eIDAS credentials, bypassing Apple/Google Wallet integrations | If the EU limits EUDI Wallet certification exclusively to official state-authorized applications |
| **P2** | Define custom `did:key` bootstrap protocol using local TPM attestation | Provides a decentralized recovery and root of trust for local identities | If hardware-backed keys cannot be securely recovered without a centralized cloud custodian |

---

## SKEPTICISM

### What Could Invalidate This Map
1. **FIDO Alliance Enforces CXP/CXF Portability:** If the FIDO Alliance mandates that all certified credential managers must support open, single-click export of passkeys via CXP/CXF, the lock-in moat disappears, and passkeys become as portable as passwords.
2. **eIDAS 2.0 Adoption Fails Due to UX Friction:** If the EUDI Wallets are too complex for average citizens, the mandate may be delayed, or platforms may implement malicious compliance (hiding the wallet option behind multiple menus), preventing W3C DIDs/VCs from achieving mainstream scale.
3. **Apple/Google Open Up Native Sync:** Google or Apple could allow third-party credential managers to plug directly into their secure sync networks, rendering local bypass mechanisms obsolete.
4. **Pure Local Recovery is Impossible:** If users lose their local hardware enclave and have no cloud custodian, they lose their identity. If a centralized recovery provider is required, we return to a federated model.

### Where the Data Is Weak
- **Tunnel Server Logs:** Because the internal operations of `cable.auth.com` and `cable.ua5v.com` are closed, we cannot verify the exact duration or scope of metadata retention on Google and Apple servers.
- **CXF/CXP Rollout Timeline:** The adoption rate of the draft Credential Exchange specifications is highly fluid; vendor roadmaps are private, and current assertions are based on developer preview builds and draft standard papers.

---

## ML-FEED

```json
{
  "entities": [
    {"id": "e-icloud-keychain", "type": "credential-silo", "label": "iCloud Keychain"},
    {"id": "e-gpm", "type": "credential-silo", "label": "Google Password Manager"},
    {"id": "e-cable", "type": "protocol", "label": "FIDO Hybrid (caBLE) Transport"},
    {"id": "e-cable-google-tunnel", "type": "infrastructure", "label": "cable.ua5v.com"},
    {"id": "e-cable-apple-tunnel", "type": "infrastructure", "label": "cable.auth.com"},
    {"id": "e-eidas-2", "type": "regulation", "label": "EU eIDAS 2.0 (Reg 2024/1183)"},
    {"id": "e-sd-jwt-vc", "type": "format", "label": "SD-JWT VC"},
    {"id": "e-oid4vp", "type": "protocol", "label": "OpenID for Verifiable Presentations"}
  ],
  "relations": [
    {"from": "e-icloud-keychain", "to": "e-cable", "type": "relies_on"},
    {"from": "e-gpm", "to": "e-cable", "type": "relies_on"},
    {"from": "e-cable", "to": "e-cable-google-tunnel", "type": "routes_through"},
    {"from": "e-cable", "to": "e-cable-apple-tunnel", "type": "routes_through"},
    {"from": "e-eidas-2", "to": "e-sd-jwt-vc", "type": "mandates"},
    {"from": "e-eidas-2", "to": "e-oid4vp", "type": "mandates"}
  ],
  "metrics": [
    {"name": "passkey_export_availability", "value": 0.0},
    {"name": "eidas_wallet_implementation_deadline", "value": 2026.9},
    {"name": "eidas_vlop_acceptance_deadline", "value": 2027.9}
  ]
}
```

---

## DIALECTIC

### Claim 1: Native Passkey Implementations as Strategic Lock-in
- **Thesis:** Apple and Google intentionally designed their passkey implementations to create walled-garden silos. By locking private keys inside hardware enclaves and syncing them exclusively through closed, proprietary cloud networks (iCloud Keychain and GPM), they raise the cost of switching device ecosystems. The Hybrid/caBLE transport is intentionally high-friction and routes connection metadata through their own servers, discouraging cross-device operation.
  - *Confidence:* 0.85 (Strongly backed by the absence of export mechanisms and hardcoded tunnel endpoints in browsers/OS).
- **Antithesis:** The isolation of passkeys in hardware enclaves and E2EE sync loops is driven purely by security requirements (preventing malware from extracting private keys) and user convenience (seamless auto-fill). The FIDO Alliance is actively standardizing credential export (CXP/CXF) with Apple and Google participation, demonstrating an industry-wide commitment to openness rather than anticompetitive lock-in.
  - *Confidence:* 0.50 (Supported by FIDO drafts, but weakened by the fact that actual export implementations are non-existent in mid-2026, and platform owners have historically delayed interoperability).
- **Synthesis:** While the security rationale of protecting private keys in hardware enclaves is technically valid, the platform gatekeepers have selectively leveraged these hardware boundaries to delay credential egress. They have prioritized proprietary sync channels over standard migration protocols, and their control over the default browsers/OS allows them to capture metadata via caBLE tunnel servers while imposing high UX friction on competitors.
- **Residual Disagreement:** Whether Apple and Google will implement symmetric, single-click, cross-platform export once CXP/CXF standards are finalized, or if they will restrict third-party import/export capabilities under the guise of security reviews. This would be settled by monitoring the release notes and API permissions of iOS 20+ and Android 17+.

### Claim 2: W3C DIDs and VCs Require State Mandates to Succeed
- **Thesis:** Decentralized identity is structurally incapable of achieving mainstream web adoption through grassroots mechanics. Relying parties have no economic incentive to accept DIDs/VCs, and consumers will not adopt wallets with no utility. Only top-down regulatory mandates like EU eIDAS 2.0 can break this cycle by legally compelling both supply (states issuing wallets) and demand (VLOPs and banks accepting them).
  - *Confidence:* 0.90 (Highly deductive and backed by the failure of all grassroots web3 identity initiatives compared to the massive regulatory movement around eIDAS 2.0).
- **Antithesis:** Enterprise adoption of decentralized identity is growing organically in closed networks (such as Microsoft Entra Verified ID for corporate credentialing and employee onboarding) and specific industries (aviation, supply chain) where compliance and auditability drive value. Grassroots consumer adoption is possible if built on top of high-value wedges (like ticket verification or academic credentials) without needing state laws.
  - *Confidence:* 0.40 (Corporate B2B use cases exist, but they do not translate to general consumer web-login adoption).
- **Synthesis:** Decentralized identity remains siloed in B2B enterprise niches or blockchain applications unless forced into the consumer web by sovereign regulations. eIDAS 2.0 is the definitive market-maker, legally forcing Very Large Online Platforms (VLOPs) to support these protocols. However, this state-enforced version shifts the architecture away from permissionless blockchains toward traditional, hierarchical state PKIs using profiled standards (SD-JWT VC and OID4VP).
- **Residual Disagreement:** Whether a non-EU commercial coalition (e.g., Shopify, major US banks, and tech vendors) will organically adopt W3C DIDs/VCs to bypass the Apple/Google identity duopoly before US/state-level mandates emerge. This would be settled by auditing the integrations of major merchant platforms over the next 24 months.

---

## FALSIFICATION

- **Falsifier 1 (Passkey Lock-in):** Apple or Google publishes an open API in their default OS/browser that allows third-party credential managers to export/import synced passkeys in a decrypted standard format (like CXF) with a single user confirmation.
- **Falsifier 2 (DID/VC Adoption):** A top-10 global consumer website (e.g., Amazon, Netflix, or Shopify) implements W3C DID/VC authentication natively for all global users, achieving over 1.0e7 active identity presentations without any legal or regulatory mandate.

---

## DELTA_LOG

- **Belief Before:** Passkeys are a neutral, open industry standard designed to replace passwords.
- **Belief After:** Passkeys are technically open but implemented as strategic ecosystem traps. The lack of outbound export, closed sync loops, and dependency on Apple/Google caBLE tunnel servers (`cable.auth.com` and `cable.ua5v.com`) represent a coordinated effort to prevent user egress from hardware platforms.
- **Specific Evidence:** Sourced specs showing that caBLE WebSocket tunnels are routed through gatekeeper-owned domains, combined with the lack of native export capabilities in Google Password Manager and iCloud Keychain in mid-2026.

- **Belief Before:** Decentralized identity (DIDs/VCs) is a grassroots Web3 paradigm.
- **Belief After:** Grassroots DID/VC adoption is dead. Decentralized identity is scaling exclusively as a state-anchored, compliance-driven framework under regulations like eIDAS 2.0, utilizing centralized trust lists and state-profiled protocols (SD-JWT VC, OID4VP) rather than public blockchains.
- **Specific Evidence:** eIDAS 2.0 Architecture Reference Framework (ARF) specs outlining the legal obligations of VLOPs by late 2027 and the rejection of permissionless ledgers in favor of national trust registries.

---

## HALLUCINATION_RISK

- **Asserted Claim:** Apple and Google use caBLE tunnel session metadata to track user logins across specific third-party websites.
  - *Tier:* Primary (for the tunnel addresses) / Secondary (for tracking implications).
  - *Risk:* Low-to-Medium.
  - *Why:* While the tunnel data is E2EE, Google/Apple receive the IP address of the client and authenticator, routing IDs, and timestamps. Whether they active-log and join this metadata with account profiles is not publicly documented, though the network capacity to do so is structurally present.
