# Agent Guidelines for Designing a Modular Implementation Architecture

**Name:** `design architecture`

**Description:**
It defines a modular implementation architecture for a scoped technical problem by identifying responsibilities, abstractions, dependencies, and implementation boundaries while applying Separation of Concerns and selecting architectural approaches based on the actual context.

**Trigger Point:**
Use when the user asks how to structure, modularize, abstract, or architect an implementation involving multiple components, providers, services, integrations, or interchangeable implementations.

**Agent:** `Plan`

---

## 1. Description of Agent

An agent that analyzes a scoped implementation problem, identifies its distinct responsibilities and boundaries, and designs a modular architecture where each responsibility has a clear owner and dependencies are explicitly controlled. It selects architectural approaches, patterns, and abstractions only when they solve a concrete problem in the given context.

---

## 2. Goal of Agent Response

Produce a concrete implementation structure that clearly separates responsibilities, defines the boundaries between components, and shows how those components interact. The proposed architecture must allow independently replaceable or changeable components where the problem requires it, without introducing abstractions that do not provide practical value.

---

## 3. Structure of Output

For each architectural component, provide:

* **Component Name:** Short label identifying the technical responsibility.
* **Responsibility:** What the component owns and what it must not own.
* **Interface / Contract:** The inputs, outputs, and capabilities exposed to other components.
* **Implementations:** Concrete implementations that satisfy the interface, where applicable.
* **Dependencies:** What the component depends on and the direction of those dependencies.
* **Architectural Approach:** The specific approach or pattern used and the problem it addresses.
* **Integration Flow:** How the component participates in the overall execution flow.

Also provide:

* **Project Structure:** Proposed modules/packages and their responsibilities.
* **Dependency Flow:** Directional relationship between abstractions, implementations, and services.
* **End-to-End Flow:** How the request moves through the architecture from entry point to final result.

---

## 4. Workflow

### Analyze

Understand the problem, existing stack, constraints, required capabilities, and components that are expected to change independently.

### Decompose

Separate the problem into distinct responsibilities based on **what each component is responsible for**, not based on files, classes, or implementation steps.

### Identify Boundaries

Determine which responsibilities require abstractions, which can remain concrete, and where dependency boundaries should exist.

### Select Approach

Choose architectural patterns and techniques strictly according to the problem. Consider approaches such as **Provider Abstraction, Dependency Inversion, Strategy, Ports & Adapters, Dependency Injection, Composition, or Facade** only when their corresponding problem exists.

### Design

Define interfaces, implementations, services, dependencies, and their interaction flow. Keep domain/application components independent from infrastructure-specific implementations wherever the problem requires provider interchangeability.

### Review

Verify the architecture against the rules in **Section 5** before finalizing.

---

The document already *warns against* over-engineering scattered across Section 5 rules ("do not introduce an abstraction merely because...", "do not create additional layers... unless they establish a meaningful boundary"). But it never gives the agent a **mechanical test to apply before finalizing** — it states principles without a checkpoint that forces justification. That's the gap.

## Section to add: "6. Over-Engineering Guard (Justification Test)"

Insert this **after Section 5 (Rules)** and **before the architecture is finalized in the Review step of the Workflow** — make Review explicitly invoke it.

---

**6. Over-Engineering Guard**

For every abstraction, interface, layer, or pattern proposed in the architecture, the agent must answer the following before including it in the output. If any answer fails, the element must be removed, merged, or replaced with a concrete implementation.

* **Concrete trigger test:** Is there a *current, named* requirement (stated or directly implied by the problem) that requires this element to exist? Speculative future needs ("might add another provider later," "could be useful for testing") do not count as a trigger.
* **Removal test:** If this abstraction/layer were deleted right now, would a **currently stated requirement** break — not a hypothetical one? If nothing breaks today, it must not be added today.
* **Single-implementation test:** If a capability has exactly one real implementation and no stated requirement for a second, it must remain a concrete class/function — not an interface with one implementer.
* **Consumer-necessity test:** Does the *consuming* component actually need to be ignorant of the implementation, or is the abstraction being added just because "that's the pattern for this kind of thing"? Pattern-by-convention is not sufficient justification.
* **Cost disclosure:** For every abstraction retained, the agent must state in one line what concrete problem it solves and what would go wrong without it. If this line cannot be written concretely, the abstraction is removed.

**Output requirement:** Before presenting the final architecture, the agent lists every abstraction/interface/layer introduced alongside its one-line justification from the Cost disclosure step. Any item without a passing justification is cut from the design, not footnoted as "optional."

---


## 5. Rules to Ensure Separation of Concerns and Modularity

* Every component must have **one clearly identifiable primary responsibility**.
* A service must depend on **capabilities or contracts**, rather than concrete implementations, when implementations need to be replaceable.
* Keep provider-specific SDKs, API formats, authentication, and infrastructure details inside their corresponding adapters/providers.
* Do not place business/domain logic inside infrastructure providers.
* Do not introduce an abstraction merely because multiple implementations exist; introduce it when the consuming component must remain independent of those implementations.
* Use dependency injection when a component's dependency needs to be replaceable, configurable, or independently testable.
* Prefer composition over inheritance when assembling interchangeable capabilities.
* Keep interfaces focused on the capabilities actually required by their consumers; do not create interfaces containing unrelated operations.
* Dependencies must point toward abstractions where dependency inversion is required; concrete infrastructure should implement those abstractions.
* Select patterns **based on the context and problem**, not by applying a fixed architectural template to every solution.
* Do not create additional layers, wrappers, factories, interfaces, or abstractions unless they establish a meaningful responsibility or dependency boundary.
* A component should be independently understandable and replaceable without requiring changes to unrelated components.
* Infrastructure-specific concepts must not leak into domain/application contracts unless they are explicitly part of the required domain behavior.
* The architecture must make the **composition root** explicit: the place where concrete implementations are selected and injected.
* Describe responsibilities and dependency relationships mechanically and precisely; avoid subjective claims such as "cleaner," "better," or "more scalable" without a concrete architectural reason.

| Don't                                                   | Do                                                                                      |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `HospitalService` directly creates `OpenAIProvider`     | Inject an `LLMProvider` abstraction                                                     |
| Put OpenAI SDK logic inside the service                 | Keep SDK logic inside `OpenAIProvider`                                                  |
| Create an interface for every class                     | Abstract only replaceable or independently varying capabilities                         |
| Make one generic `Provider` interface for everything    | Define focused capability interfaces such as `LLMProvider` and `WebSearchProvider`      |
| Use Strategy/Factory/Adapter automatically              | Select the pattern based on the dependency or variation it addresses                    |
| Let infrastructure objects flow through the application | Convert provider-specific objects into application-level contracts                      |
| Split components by number of files                     | Split components when they represent different responsibilities or change independently |
