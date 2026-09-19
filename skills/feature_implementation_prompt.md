Task: You need to come up with the Implementation Plan for the Deep Search Feature Implementation

Description: The feature is quite broader in its horizon and therefore, required a very structured approach for its implementation. I have divided the feature into distinct responsibilities and each responsibility into a workflow that comprised of multiple mechanisms, and we will be implementing one mechanism (or its components) at a time.  That's the overall picture of how the implementation of the feature is broken down to the lowest level. 

For the better context, here is the file that provides the details about the following things:
1. Problem context of the feature
2. Problem statement of the feature
3. Workflow of the feature
4. Responsibilities of the feature
5. problem context and problem statement of the responsibility 1
6. Mechanisms of responsibility 1
7. Implementation curx of the Mechanism 1 

Now, we will be implementing the mechanism 2 Component 2A of the Responsibility 1.  
Note: We should not make classes for each mechanisms of the responsibility (Until it is necessary to have it otherwise feature would break):  

Here is the more precise definition of how the overall structure of the feature can look like:

Implement the feature as a set of classes that represent its responsibilities, with each responsibility encapsulating the workflow of its underlying mechanisms. Methods then implement the individual stages which are supposed to be derived from those mechanisms, while the feature coordinates the execution of the responsibilities.

Important rule: Stage methods should be derived from the mechanisms that define the responsibility's workflow, rather than being created independently at the implementation level.

So the implementation flow could be:
Feature
   ↓
Feature Class
   ↓
Responsibility Classes
   ↓
Mechanism Workflows
   ↓
Stage Methods


### Here is how you should structure the implementation plan ###


You need to follow the guidelines in Plan_output_format.md to compile your Implementation plan.


**While producing the plan (Plan mode, before the user confirms):**
- Output the implementation plan and architecture decisions in the plan
  document, following Plan_output_format.md.
- Put the full Build checklist in the plan `todos`. That checklist MUST
  include (a) writing the two canonical markdown files and (b) implementing
  the mechanism in code (schemas, exceptions, prompt module, methods on
  the existing responsibility class, tests, **and a live sample runner**).
- The sample runner is required, not optional. Plan it in Section 1 and
  Section 4 of Plan_output_format.md. It lives under
  `backend/src/services/deep_search/feature_sample_runs/`. It seeds dummy
  handoff state as after the previous mechanism and must not re-call
  already-implemented mechanisms. That seeded input must not reuse the
  mechanism's prompt worked-pair examples.
- Do not execute any todo. Do not create or edit application code. Do not
  write the markdown files to disk yet. Confirmation is clicking Build,
  not this planning turn.
**After the user confirms (Build):**
- Execute every todo on that checklist, in order.
- First write the two files under
  `backend/src/services/deep_search/feature_context/`:
  - `mechanism_N_implementation_plan.md`
  - `mechanism_N_architecture_decisions.md`
- Then implement the mechanism in code as specified in that plan,
  including the live sample runner. Do not stop after the markdown files.









