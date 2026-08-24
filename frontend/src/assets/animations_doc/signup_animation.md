Yes. The key is to **describe the reference as a visual/motion system rather than as a screenshot to copy**. Since you're going to define the motion tokens and principles separately, the prompt should establish the **structural asset, visual language, hierarchy, relationships, and flexibility**—while explicitly leaving motion-token values open.

I've framed it so an AI coding tool can translate it into a **reusable React motion asset**, rather than hard-coding the exact text/icons from the reference.

# Build a Connected AI Motion Asset

Use the provided reference image as the **visual and compositional reference** for this component.

The goal is to create a reusable, interactive **AI ecosystem / workflow motion asset** inspired by the reference—not a pixel-perfect copy.

The final result should feel like a **premium futuristic AI system map**: a collection of illuminated interface nodes connected through animated pathways, with a strong sense of hierarchy, depth, intelligence, and flow.

## 1. Core Concept

Create a visual system consisting of **7 primary AI/function nodes** connected by animated lines.

The nodes represent:

1. **Home Wishlist**
2. **Deep Apartment Search**
3. **Automated Deep Analysis**
4. **Smart Matching Engine**
5. **Scoring Report**
6. **Communication Management**
7. **HomeScount Agents Workforce**


The component should visually communicate that these are not isolated icons. They are **parts of one connected intelligence system**, with information flowing between them.

The reference image uses many icons, but this implementation should contain **exactly 7 primary nodes**.

Do not reproduce the large number of icons from the reference.

---

## 2. Overall Composition

Use the reference image's general composition as inspiration:

* Dark, almost-black background.
* Six floating/suspended interface nodes.
* Nodes distributed across the canvas rather than arranged in a rigid grid.
* One node (HomeScout Agents Workforce) should have stronger visual prominence and act as important points in the network.
* Supporting nodes should sit around the primary nodes.
* Nodes should have enough negative space between them to make the connecting network clearly visible.
* The overall composition should feel like a **network / system architecture**, rather than a traditional UI dashboard.
* Avoid making the layout look like a simple six-card grid.

The composition should have an organic, slightly asymmetric arrangement similar to the reference.

### Suggested spatial hierarchy

Use a composition approximately like:

                    Deep Apartment Search
                           │
          Home Wishlist ───┼─── Automated Deep Analysis
                           │
                 ┌───────────────────────┐
                 │ HomeScount Agents      │
                 │      Workforce        │
                 └───────────────────────┘
                           │
      Smart Matching Engine┼────────Scoring Report
                           │
                  Communication Management
This is only a conceptual arrangement.

The implementation should be free to adjust positioning to achieve a visually balanced composition and responsive behavior.

The **Matching Engine** can act as the central/high-value node because it represents the system's coordination layer.

---

## 3. Node Design

Each node should visually resemble the floating icon modules in the reference.

Each node consists of:

* A rounded-square container.
* Dark translucent/near-black surface.
* Subtle border.
* Soft outer glow on all nodes.
* Slight dimensional depth.
* An internal icon representing the node's function.
* Optional secondary visual details inside the node.
* Optional label outside or adjacent to the node.

The nodes should feel like **objects floating above a dark digital canvas**, not ordinary flat cards.

### Important

The icons should NOT be treated as fixed assets that are permanently baked into the component.

Create the node as a reusable component with configurable content.

Conceptually:

```jsx
<MotionNode
  type="deep-search"
  icon={DeepSearchIcon}
  label="Deep Search"
/>
```

The actual implementation should allow:

* Icon replacement
* Label replacement
* Node title replacement
* Node size adjustment
* Visual state changes
* Active/inactive state
* Optional badge/status
* Optional metadata

Do not tightly couple the component to the six example labels.

---

## 4. Icon Direction

Use 7 visually distinct icons that communicate:
Here are the descriptions you can use as prompts to recreate exact style and set of icons.


### 🧩 Specific Icon Prompts (Append to the Base Style)

* **Home Wishlist**
"Center a stylized house with a heart cut-out in the middle. Place a larger, solid white heart next to it, along with a small user profile silhouette and simple bulleted list lines. Add curved, radiating arcs on the left and right sides of the black box to suggest a glowing, interactive state."
* **Deep Apartment Search**
"Feature two tall apartment buildings with clear window grids. Overlay a large magnifying glass over the buildings. On the right side, add floating UI elements that look like search filter bars and list lines."
* **Automated Deep Analysis**
"Draw a side-profile of a human brain constructed entirely from technological circuit board lines and nodes. Surround the brain with abstract data visualization elements, including vertical bar charts and a small network of connected nodes at the bottom."
* **Scoring Report**
"Design a central bullseye target with an arrow hitting the center. Surround it with a circular progress ring, an ascending bar chart, a checklist with checkmarks, and three rating stars. Include a white 'pointing hand' cursor clicking the target. **Important:** Give the outer edge of the black square box a glowing white border to show it is selected."
* **Smart Matching Engine**
"Create four interlocking jigsaw puzzle pieces that fit together to form a larger square. Overlay a geometric network of connected dots and lines (nodes) spanning perfectly across the surface of the puzzle pieces."
* **HomeScout Agents Workforce**
"The icon features a collective of three stylized human head profiles clustered together. Inside each head is a glowing circuit-brain symbol. They are all interconnected by a complex, glowing network of data lines and small nodes, symbolizing a collaborative team of artificial intelligences. A small, central "AI" label anchors the connection network, and scattered small stars complete the detail. The overall design communicates a unified, network-based workforce of intelligent agents."
* **Communication Management**
"Feature two overlapping, rounded speech bubbles. The top bubble should contain a user profile silhouette and horizontal lines representing text, with the specific word 'owner/' visible. The bottom bubble should contain a user profile silhouette and three horizontal dots."


The icons should belong to a **consistent visual family**.

Do not mix unrelated icon styles.

---

## 5. Labels and Text

The exact text shown in the reference image should NOT be reproduced.

The component needs to be designed so labels are configurable.

For example:

```jsx
<MotionNode
  label="Deep Search"
/>
```

and:

```jsx
<MotionNode
  label="Analysis"
/>
```

The user should be able to change the labels without modifying the animation or layout logic.

Text may appear:

* underneath an icon

The text should be secondary to the visual nodes.

The design should work equally well with without breaking the composition.

Do not hard-code text dimensions based on the reference.

---

## 6. Connected Animated Lines

One of the most important characteristics of this design is the **network of connecting lines**.

The six nodes should be connected through elegant animated lines.
**Core Prompt:**

"A futuristic UI ecosystem map on a dark, subtle grid background. Generate animated, glowing energy lines connecting various rounded square nodes. The connecting lines should not be single solid strokes, but rather look like bundles of luminous fiber-optic cables or flowing streams of digital data. The lines must have smooth, organic, sweeping curves—no sharp angles."

**Detailed Modifiers to Add for Accuracy:**

Color & Lighting: "The lines feature vibrant, neon gradient transitions shifting seamlessly between electric cyan, deep blue, vibrant purple, and bright magenta. They should emit a strong, soft outer glow (bloom effect) with intense, bright white-hot cores."

**Animation & Motion Details:** "Animate the lines to show continuous, flowing directional movement. Include bright, glowing light particles (like data packets or energy pulses) traveling swiftly along the curved paths from one node to another. The bundled strands within the lines should subtly undulate and shimmer, giving a sense of active, living electrical current."

**Connection Points:** "The glowing lines should smoothly merge into the glowing borders of the rounded square UI nodes they are connecting to, looking as if they are actively powering or feeding data into the icons."

**Style/Aesthetic:** "Cyberpunk, high-tech, futuristic dashboard, neon glassmorphism, 3D data visualization, ultra-high resolution, smooth 60fps motion."

### Critical requirement

Do NOT implement the lines as manually positioned decorative SVG lines that only work for one fixed layout.

The connector system should understand relationships between nodes.

Conceptually:

```js
connections = [
  ["deep-search", "analysis"],
  ["analysis", "matching-engine"],
  ["matching-engine", "score-card"],
  ["matching-engine", "communication"],
  ["communication", "user"],
  ["score-card", "user"]
]
```

The visual connector should derive its path from the positions of the connected nodes.

This allows the nodes to be repositioned without manually redrawing every line.

---

## 7. Data Flow Visualization

The connectors should not simply sit on the canvas as static lines.

They should communicate **flow**.

Use subtle visual movement such as:

* Traveling light particles
* Moving highlights
* Pulses
* Flowing gradients
* Small energy points moving along the connector path

The movement should be restrained and sophisticated.

It should feel like **information moving through an AI system**, rather than electricity or a sci-fi laser effect.

The motion should remain legible even when the component is viewed at a distance.

---

## 8. Node States

Each node should support multiple visual states.

At minimum:

### Default

Subtle glow and restrained presence.

### Active

The node becomes more prominent through:

* Increased glow
* Slight brightness increase
* More visible internal details
* Potential connector activity

### Processing

The node can communicate that it is currently working.

For example:

* Internal pulse
* Rotating/subtle processing indicator
* Increased activity on connected lines

### Completed / Result

The node can visually communicate that a process has completed.

For example:

* Check state
* Result highlight
* Brief pulse

These states should be implemented as reusable component states rather than separate hard-coded designs.

---

## 9. Visual Language

The overall visual language should be inspired by the reference:

### Background

* Very dark / black
* Minimal visual noise
* Optional extremely subtle gradient or atmospheric glow
* No busy background imagery

### Surfaces

Nodes should use:

* Dark glass-like surfaces
* Soft gradients
* Subtle highlights
* Fine borders
* Rounded corners
* Layered shadows

### Lighting

Use restrained lighting rather than excessive neon.

The visual hierarchy should come from:

* luminance
* glow
* depth
* scale
* contrast
* active states

The design should feel **premium, technical, futuristic, and sophisticated**.

Avoid making it look like a gaming UI.

---

## 10. Depth and Dimensionality

The nodes should not look completely flat.

Create subtle depth through:

* Outer shadows
* Inner shadows
* Edge highlights
* Soft gradients
* Slight glass/translucent effects
* Layered glow
* Very subtle perspective

The internal icon can have its own visual depth.

However, keep the overall design restrained.

The reference works because the objects feel dimensional while the overall canvas remains visually minimal.

---

## 11. Animation Architecture

Build the component so that the **animation implementation is independent from the content**.

The node should represent the visual object.

The connector should represent the relationship.

The motion system should control the behavior.

Conceptually:

```text
Motion Network
│
├── Nodes
│   ├── Deep Search
│   ├── Analysis
│   ├── Matching Engine
│   ├── Score Card
│   ├── Communication
│   └── User
│
├── Connections
│   ├── Node → Node
│   ├── Flow
│   └── Pulse
│
└── Motion System
    ├── Entrance
    ├── Idle
    ├── Active
    ├── Processing
    └── Transition
```

Do not hard-code animation values directly into individual nodes.

The implementation should be prepared to consume a separate motion-token system.

---

## 12. Motion Tokens

Do NOT invent or finalize the motion tokens.

The motion-token system will be provided separately.

Your implementation should instead expose the appropriate parameters/hooks/configuration points so that motion tokens can later control:

* Duration
* Delay
* Easing
* Stagger
* Distance
* Scale
* Opacity
* Glow intensity
* Connector speed
* Pulse frequency
* Spring behavior
* Entrance behavior
* Exit behavior

The component should therefore be **motion-token ready**.

Do not bury these values throughout the component code.

Centralize animation configuration so that a motion system can be applied later.

---

## 13. Motion Principles

Do NOT independently define the final motion principles.

The motion principles will be supplied separately.

However, architect the component so those principles can control:

* How nodes enter the canvas
* How relationships are established
* How information flows
* How active nodes respond
* How focus moves through the system
* How transitions occur
* How the system behaves when content changes

The component should be designed as a **motion-aware visual system**, not as six independent animated cards.

---

## 14. Responsive Behavior

The asset must work across different viewport sizes.

On large screens:

* Use the full network composition.
* Preserve the asymmetric system-map feeling.
* Give the central node enough visual prominence.
* Maintain generous negative space.

On smaller screens:

* Reposition nodes intelligently.
* Preserve the logical connections.
* Prevent connector lines from overlapping labels.
* Avoid shrinking everything until the icons become illegible.
* Allow the network to reorganize rather than simply scaling down.

The node relationships should remain understandable regardless of layout.

---

## 15. Technical Direction

Build this as a reusable React component/system.

Prefer a structure similar to:

```text
MotionNetwork/
│
├── MotionNetwork
├── MotionNode
├── MotionConnector
├── MotionParticle
├── NodeIcon
├── NodeLabel
├── motion.config
└── types
```

The system should separate:

### Content

```text
Node data
Icons
Labels
Metadata
```

from:

### Structure

```text
Node positions
Connections
Hierarchy
Relationships
```

from:

### Motion

```text
Animation behavior
Tokens
States
Transitions
```

from:

### Visual styling

```text
Surface
Glow
Border
Typography
Depth
```

This separation is important because the same motion system should eventually be usable with completely different content.

---

## 16. Desired Result

The final component should feel like:

> **An intelligent visual network where six AI capabilities exist as interconnected objects, with information visibly flowing between them.**

It should resemble the reference image in terms of:

* composition
* visual hierarchy
* dark futuristic aesthetic
* floating dimensional nodes
* connected architecture
* animated data pathways
* restrained glow
* sophisticated motion

But it should NOT be a literal recreation of the reference.

The final asset should be **cleaner, more intentional, and less crowded**, with exactly six meaningful nodes.

The most important visual idea is:

**Six intelligent nodes + meaningful relationships + animated information flow + premium futuristic interface language.**

Build the system so that the **content, icons, labels, relationships, layout, and motion tokens can all be changed without rewriting the underlying component.**
