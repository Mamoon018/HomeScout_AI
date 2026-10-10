Task: You need to come up with the Implementation Plan for the Deep Search Feature Implementation

Description: The feature is quite broader in its horizon and therefore, required a very structured approach for its implementation. I have divided the feature into distinct responsibilities and each responsibility into a workflow that comprised of multiple mechanisms, and we will be implementing one mechanism (or its components) at a time.  That's the overall picture of how the implementation of the feature is broken down to the lowest level. 


Here are the skills that you need to use for the plan:
1. file for architectural decisions use skill defined in  @skills\Implementation_architecture_skill.md
2. Split the code among relevant files without over-engineering it. Do not create new files uncessarily in the name of separation of concerns unless there is genuine need for it.
3. Make sure that you follow guidelines to structure the plan @skills\Plan_output_format.md
4. Make sure you follow the guidelines to keep implementation async @skills\async_app_skill.md
5. Make sure you use the skill @skills\drift_analyzer.md to ensure that along with the happy path you also consider and guard the drifts as well
6. You need to ensure that you use the skill @skills\logs_recorder.md to write logs for the implementation


For the better context, here is the file @backend\src\services\deep_search\feature_context\deep_search_context.md that provides the details about the following things:
1. Responsibility-2 of the feature
2. problem context and problem statement of the responsibility 2
3. Mechanisms of responsibility 2
4. Implementation details in the form of sub-components of the Mechanism 3 subcomponent C3.1.2 (You need to implement this)

# Current Mechanism Implementation: 
Now, we will be implementing the mechanism 3 component M3.1.2 subcomponents of responsibility 2

Note: We should not make classes for mechanisms of the responsibility (Until it is necessary to have it otherwise feature would break):  

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


IMPORTANT NOTE: Implementation must be grounded in the spec of the specified sub-component, skills that are specified, and the structure of the code that is defined for the feature. 

### Here is how you should structure the implementation plan ###
You need to follow the guidelines in Plan_output_format.md to compile your Implementation plan.


**While producing the plan (Plan mode, before the user confirms):**
- Output the implementation plan following Plan_output_format.md, make architectural decision plan as part of the implementation plan file at the end and do not generate separately.
- Put the full Build checklist in the plan `todos`. That checklist MUST not include "writing the two canonical markdown files". 
  It MUST include only (a) implementing the mechanism in code (schemas, exceptions, prompt module, methods on
  the existing responsibility class, tests, **and a live sample runner** and other things guided as per skill).
- The sample runner is required, not optional. Plan it in Section 1 and
  Section 4 of Plan_output_format.md. It lives under
  `backend/src/services/deep_search/feature_sample_runs/`. It seeds dummy
  handoff state as after the previous mechanism and must not re-call
  already-implemented mechanisms. That seeded input must not reuse the
  mechanism's prompt worked-pair examples.
- Do not execute any todo. Do not create or edit application code. Do not
  write the markdown files to disk yet. Confirmation is clicking accept,
  not this planning turn.
**After the user confirms (accepts):**
- Execute every todo on that checklist, in order.
- Implement the mechanism in code as specified in that plan,
  including the live sample runner. Do not stop after the markdown files.

Make this part of the implementation plan, based on the implementation you need to check @feature_context if it requires any updates in other mechanisms which were written before this implementation and if you find any then update them.





