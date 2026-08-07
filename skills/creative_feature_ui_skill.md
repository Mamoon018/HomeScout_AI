# Creative Feature & Viral UI Engineering Skill (`creative-product-ideation.md`)

This skill equips LLM agents with behavioral psychology, viral growth frameworks, and creative product design mental models. Use this guide to push past generic suggestions and generate software features and UI micro-interactions that feel **contagious, snappy, pleasant, and highly functional**.

---

## 1. Core Operating Principles for LLM Agents

When invoked, do not default to standard B2B/B2C design patterns (e.g., "add a basic search filter" or "send a transactional email"). Force ideation through these constraints:

1. **Anti-Boring Rule:** Reject the first three conventional ideas that come to mind.
2. **Creativity Grounded in Utility:** Never design for novelty alone. Every creative twist or pleasant UI interaction must solve a real user friction point or make a task meaningfully easier. If it isn't useful, it's bloat.
3. **Tactile Snappiness & Polish:** Make software feel like a high-end physical object—responsive, smooth, and tactile with immediate visual or micro-spatial feedback.
4. **The "Show, Don't Tell" Flex:** Design features that make users want to screenshot, share a link, or show a friend simply because the execution is so surprisingly elegant or helpful.

---

## 2. Product-Adapted Creative Frameworks

### Framework A: The Product STEPPS Matrix

*Adapted from "Contagious: Why Things Catch On" by Jonah Berger*

To make a feature or UI element naturally viral or worth talking about, evaluate it against the 6 STEPPS adapted for consumer-facing apps:

| STEPPS Dimension | Book Principle | Product & UI Application | Agent Prompting Mechanism |
| --- | --- | --- | --- |
| **Social Proof / Currency** | People share what makes them look smart, cultured, or ahead of the curve. | Design shareable artifacts, curated lists, or aesthetic summary views built directly into the core app. | *How does using this feature make the user feel like an insider or taste-maker to their peers?* |
| **Triggers** | Top of mind = top of tongue. Environment prompts memory. | Tie features to real-world contexts, locations, seasons, or personal habits (e.g., "planning a weekend getaway on Thursday night"). | *What external environmental or real-world event naturally triggers the user to open this feature?* |
| **Emotion** | High-arousal emotions (awe, delight, curiosity) drive memorable actions. | Inject moments of sensory delight, rich visual transitions, or dramatic reduction of friction during stressful steps. | *How can we transform a mundane task (e.g., browsing options or checkout) into a moment of awe or calm satisfaction?* |
| **Public** | Built to show, built to grow. Making private utility visually striking. | Create high-craft visual assets that look beautiful when screenshot or shared externally. | *How can this feature produce an output that users naturally want to share on social channels or messages?* |
| **Practical Value** | News you can use. High utility organized for instant clarity. | Curate multi-layered information into digestible, visual decision cards or instant comparisons. | *How can we collapse hours of research/browsing into a 5-second crystal-clear insight?* |
| **Stories** | Information travels under the guise of an idea or story. | Frame choices or options as part of a narrative journey rather than just database entries in a grid. | *What shareable story does the user tell when describing this experience to a friend?* |

---

### Framework B: The Tactile Hook Loop

*Adapted from "Hooked" by Nir Eyal & High-Craft Consumer Philosophy*

To build natural retention without relying on intrusive popups or complex keyboard paths, structure UI features around a 4-phase loop:

```
[ Real-World Trigger ] ➔ [ Frictionless Action ] ➔ [ Variable Reward ] ➔ [ Immediate Investment ]

```

1. **Trigger:** Internal desire or external context (e.g., "looking for inspiration", "comparing choices").
2. **Action:** The absolute simplest touch-friendly gesture or interaction possible (fluid drag, swipe, intuitive map pinch).
3. **Variable Reward:** Unpredictable visual or functional delight:
* **Reward of the Hunt:** Uncovering a hidden gem, unexpected value, or perfect match.
* **Reward of the Self:** Sense of mastery, aesthetic satisfaction, effortlessly organizing options.


4. **Investment:** Asking the user for a tiny effort *immediately after* the delight (e.g., save to a custom list, set a preference) that makes the app smarter for next time.

---

### Framework C: The MAYA Principle (Most Advanced Yet Acceptable)

*Adapted from "Hit Makers" by Derek Thompson & Raymond Loewy*

> **Formula:** `Novelty = 80% Familiar Core + 20% Radical Twist`

* **Too Familiar:** Boring, forgotten, feels like a generic template.
* **Too Novel:** High cognitive load, confusing, abandoned.
* **Agent Strategy:** Take a standard component (a search filter, a product card, a map view) and apply **one** unexpected interaction dimension (fluid spatial transitions, interactive price sliders, tactile image carousels).

---

## 3. Real-World Case Studies: Premium Consumer Craft

### Case Study 1: Airbnb – Spatial Exploration & Image-First UX

* **The Technique:** **Map-Grid Fluidity & Aesthetic Curation.**
* **The Story:** Airbnb transformed travel search from boring table listings (like traditional hotels) into an inspiring visual magazine. By linking the map view seamlessly with hovering listing cards, panning the map dynamically updates listings without reloading. They added category icons ("Off-the-grid", "Design", "A-frames") that turn browsing into aspirational browsing.
* **Product Lesson:** **Turn a search tool into an exploration tool.** Combine functional filters with beautiful visual feedback so browsing feels like flipping through a high-end catalog rather than querying a database.

### Case Study 2: Apple’s Touch & Physics (iOS / Mac)

* **The Technique:** **Direct Manipulation & Inertial Physics.**
* **The Story:** When Apple pioneered modern touch UI, they didn't just render buttons—they mapped UI movement directly to physical gestures. Features like **Rubber Banding (overscroll bounce)** and fluid sheet-modal dragging gave digital objects weight and responsiveness.
* **Product Lesson:** **Perceived snappiness comes from immediate UI responsiveness.** Even if a server call takes a moment, the interface must respond to user input on frame zero ($0\text{ ms}$) with natural elasticity.

### Case Study 3: Uber – Real-Time Spatial Expectation Management

* **The Technique:** **Visual Transparency & Dynamic State Feedback.**
* **The Story:** Before Uber, waiting for a taxi was filled with anxiety because you had zero visibility. Uber made the invisible visible by displaying cars moving in real time on a map. They turned a boring waiting state into an engaging, visual progress loop. 
* **Product Lesson:** **Eliminate user anxiety with live visual feedback.** When a background process or multi-step service is happening, show dynamic visual progress rather than a static spinner.

### Case Study 4: Arc Browser – AI Canvas & Workspace Contextualization

* **The Technique:** **Active Workspace Manipulation & Workspace Synthesis.**
* **The Story:** Traditional browsers keep AI isolated in a side-chat drawer where users manually copy and paste text. Arc embedded AI directly into the primary workspace canvas—auto-titling messy tabs based on content, summarizing long pages into hoverable visual cards, and grouping fragmented web research into structured, contextual "Spaces."
* **Product Lesson:** **Don't restrict intelligence to a chat window.** Use AI to actively organize, clean, and enrich the primary user workspace, transforming raw, unstructured browser data into a cohesive, readable dossier.

### Case Study 5: Ramp – Autonomous Out-of-Band Reconciliation

* **The Technique:** **Background Agent Execution & Asynchronous Pipeline Tracking.**
* **The Story:** Financial platforms historically forced users into manual forms to track down missing receipts and verify ambiguous vendor data. Ramp introduced background agents that independently execute out-of-band communication (via SMS/email) with third parties, parse unstructured incoming replies, and continuously update the internal ledger without blocking the user.
* **Product Lesson:** **Treat multi-step processes as an active pipeline, not a static index.** Shift from passive user-driven forms to proactive, agent-driven execution, providing the user with real-time status updates on background workflows.

---

## 4. Agent Ideation Protocol & Requirement

When tasked with generating feature or UI ideas for a product prompt, the LLM agent **must adhere to the following workflow**:

1. **Deconstruct the Boring Baseline:** Identify how standard apps handle this feature. List standard UX patterns to explicitly avoid.
2. **Apply Creative Frameworks (STEPPS / Hook Loop / MAYA):** Infuse the concept with tactile snappiness, pleasant visual interactions, or viral mechanics.
3. **Rigorous Utility Justification:** For every creative concept proposed, explicitly justify:
* **Why it's useful:** Exactly how it solves a core user problem, reduces friction, or saves effort.
* **Why it applies here:** How it fits naturally into this specific application type (e.g., e-commerce, marketplace, booking, discovery) without feeling forced.


*Note: Do not restrict yourself to a rigid template. Be creative, expressive, and detailed in your reasoning while ensuring every idea balances delight with pure practical value.*