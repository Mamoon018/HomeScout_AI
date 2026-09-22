# Problem Definer Agent

As of now, I have defined the problem context for the feature and not the “Actual problem statement”. I have only defined the problem statement for the overall problem that the application aims to solve for now.

Now, I am defining the user and environment and problem relevance in the context of the overall problem statement however, only for this specific Feature: Login Authentication Layer in the application.

Now, as a first step I want to see if I can add some dimensions in the user, environment and problem relevance and refine all these things because eventually the ACTUAL problem statement depends on these things.

So, Can you take each point of the problem context of this feature and think out of creativity about the dimensions that we can consider for defining it WHILE STAYING WITHIN the context and specificity of the overall problem statement & EXTRA INFO about the product of which this feature is part of, that we have defined rather than being generic about thinking for the dimensions.

## Just to give the context here is an example with intent of what I am trying to define for each point in problem context:

Sample response: This example is in the context of the Conduct the web search for the housing Apartment feature.

## Definition of User Point and rules for defining it:

**User:** Here we are supposed to define the "wants/requirements" of the user. It defines how a user would want a generic/simple feature solution to work that fulfill his wants/requirements in a given context of overall problem. (In our example, Web Search feature (Simple search is generic) however, we defined how user would want it to work in order to satisfy his wants so, that it can work in a specific way.)

**Definition:** the set of end states the user wants to reach regarding the problem, each paired with the friction that blocks him from reaching that state without the feature.

### Approach for defining it:

1. Identify every stakeholder who interacts with this feature, not just the primary one. Define separately if their wants differ.
2. For each stakeholder, list wants as end states, not actions or solutions ("not missing an option" not "search should crawl all sites").
3. Pair each want with the friction that exists today, without the feature, that blocks that state. Friction should describe his current manual effort or its failure point, not the absence of the feature.
4. Exclude system, environment, or feature mechanics from this section entirely. A want should hold true regardless of what solution eventually gets built.
5. Check completeness by asking: if all these wants were satisfied, would the stakeholder consider the problem solved from his side. If not, a want is missing.
6. Completeness Check: Name each of the want and make them a noun to define the user section.

   Here is the example of defining point User: Understood. Each dimension below is framed strictly as: what the user wants from the search, and the friction that currently stops him from getting it (independent of how the feature would solve it).

   Want: Not missing any option that exists. Friction: doing this manually means checking multiple sites repeatedly, and still not being sure nothing was missed. The user carries constant doubt about whether he saw everything.

   Want: Only seeing what matters to him, not everything that exists. Friction: manually going through listings means wading through many that don't fit his critical preferences before finding ones that do. This wastes his effort and attention.

   Want: What he's looking at is still available, not gone. Friction: by the time he finds and considers a listing manually, it may already be taken. He wastes time evaluating something he can no longer act on.

   Want: Having something to choose from, even if not perfect. Friction: if he search too strictly for his ideal, he risks ending up with nothing, and no options at all is worse than imperfect ones, because he has no ability to compare or decide. Each of these states a want (what he's after) and a friction (what stops him from getting it today, without the feature), with no mention of environment, system, or how the feature would work internally.

## Definition of Environment Point and rules for defining it:

**Definition:** It describe the world your feature is entering. The fixed conditions surrounding the user's situation, outside the feature and outside his own wants, that shape what a solution must account for. Things that our feature interact with and therefore, change in the way they work would require product to adjust because now environment in which feature operates has changed so, assumptions/facts that are basis for the feature needs to be updated.

### Approach for defining it:

1. Identify what's true about the user's situation independent of whether this feature exists (his decision constraints, timeline, external competition, market conditions).
2. State conditions as facts about the world, not preferences ("listings expire and get taken by other seekers" not "user wants to be fast").
3. Separate two categories: (a) conditions that constrain what "success" can look like (e.g., some options are better than none), and (b) conditions that constrain how the solution must operate (e.g., data lives across separate sources, situation changes over time).
4. Exclude anything that's actually a want in disguise. A test: if removing the feature doesn't change whether the statement is true, it's environment. If it does, it's a want.
5. Check completeness by asking: does this environment explain why a naive, one-time version of the feature would fail. If the environment doesn't justify that, it's incomplete or irrelevant.

## Definition of Problem relevance point and rules for defining it:

**Problem relevance:**

**Definition:** the reason the gap between the user's current state and his wants actually matters, stated as a consequence, used to filter and justify which capabilities belong in the problem statement.

### Approach for defining it:

6. State what fails or what the user loses if the wants remain unmet, in one or two sentences. Not a restatement of the wants, but the downstream effect of not having them met.
7. Keep it at the level of the core decision the user is trying to make, not at the level of individual friction points (those already live in User).
8. Use it as a test during problem statement drafting: for every capability being written into the problem statement, check whether it traces back to closing the gap this section describes. If a capability doesn't, cut it or question why it's there.
9. Keep it short. This section is a filter, not a place to list evidence or elaborate wants again.

## Here is the complete context of the overall problem that we are trying to solve through our application: (Current problem we want to solve)

## Product for which we are building this Authentication Layer: (Extra Info)

In the context of the user and its environment, app brings the capabilities like exhaustive search on web for relevant apartment listings, analyzes each listing in preferable dimensions and uses match engine to shortlist key listings, and score each of them representing expected desirability of the user then it initiates the communication with stakeholders on behalf of the user to inquire about extra information while keeping the user in the loop for leading the specifications of communication. It keeps on running the loop for as many days as the user wants without losing the context of the on-going search & communication progress. In this way, it automates the apartment search for the user by working as a digital long running real-estate agent to perform a task of nature which usually comprises the days and weeks.

## Overall Problem Statement:

The system needs to establish and maintain the authenticated identity of registered users throughout their interaction with the application, while preventing unauthenticated or unknown users from accessing protected application features and user-specific data. The system must reliably determine whether a user is authenticated whenever protected functionality is accessed, maintain that authenticated state for an appropriate period without unnecessary re-authentication, and ensure that authentication cannot be bypassed through alternative access paths such as direct interaction with protected services.

## Here is the context of the problem that I have defined for the feature: Feature: Login Authentication Layer in the application - Problem Context:

IMP: This is only an example, you need to look at every use case in its own context and define it based on the its own nature.

**User:** (In this case, Application system is the user because it has to use this layer to work in a secure manner and also the registered user because they two stakeholders has to use this layer)

The system wants to provide the registered customers access to only their own data. For that, it wants to figure out if the user is authenticated or not, if no then it does not allow the user to access the gated pages or features of the application. If yes, then it provides the user access to the gated features and those gated features would also want to check if the user is really authenticated or not so, that feature can be triggered either to generate data or fetch data specific to that user.

It has to keep working like this until user stays authenticated while using the application.

**Environment:**

* Registered user can try to access the features via login approach
* Registered User can also try to access the feature using Dev-tools skipping the login page
* Registered User would not want to be requested to get authenticated multiple times in a single session without any reason or unnecessarily
* 4. Registered User would want not want to login again for next 24 hours at least because they would want to check the progress of the agents, even if they leave the application for some time
* 5. We will have to keep pushing the notifications on the update so, if that requires it to stay logged in then we need to ensure user stays logged in even after leaving the application for some time

**Problem relevance:**

System does not want to allow the unregistered and unknown users to access the data of registered users by triggering the services that are responsible for fetching the registered user data and storing the data for them.
