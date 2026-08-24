**Python & Backend Code Structure — Coding Agent Instruction Manual**

The purpose of this instruction manual is to ensure that the coding agent consistently produces backend code that is modular, predictable, easy to understand, easy to test, and easy to refactor.

The agent must organize implementation based on responsibility, not convenience. A feature may involve routes, schemas, business logic, database access, external clients, configuration, and utilities, but these responsibilities must not be mixed together simply because they are part of the same feature.

The structure should provide enough separation to make the code maintainable without introducing unnecessary abstractions, layers, classes, or files.



**Instructions on the responsibilties of the folders and the files:**

The exact folders do not need to exist in every project. They should be introduced only when the application actually requires that responsibility.

Where each piece of backend code belongs based on its responsibility

API routes → app/api/routes/

Definition: Contains HTTP route definitions, endpoint declarations, request dependencies, and the translation between HTTP requests and application operations.

Goal: Keep HTTP concerns separate from business logic, database implementation, and external service communication.

API dependencies → app/api/dependencies/

Definition: Contains reusable dependency logic required by endpoints, such as authentication extraction, authorization checks, database session injection, or request-scoped dependencies.

Goal: Prevent repeated setup and request-specific infrastructure from being embedded directly inside route handlers.

Application startup/composition → app/main.py

Definition: Contains application initialization and composition, such as creating the application instance, registering routers, middleware, exception handlers, and startup/shutdown behavior.

Goal: Make application assembly easy to understand without putting feature implementation inside the entry point.

Configuration/infrastructure settings → core/

Definition: Contains application-wide technical configuration and infrastructure concerns, such as environment settings, security configuration, logging setup, and shared framework configuration.

Goal: Centralize technical configuration instead of reading environment variables or configuring infrastructure throughout the application.

Database setup → db/

Definition: Contains database connection/session management, database initialization, base configuration, migrations-related integration, and database-specific infrastructure.

Goal: Keep database infrastructure separate from models and business logic.

Database access/repositories → db/repositories/

Definition: Contains reusable database operations responsible for retrieving, creating, updating, or deleting persisted data.

Goal: Keep database query implementation separate from business rules and HTTP route handling.

Database models → models/

Definition: Contains ORM/database models representing persisted entities and their database relationships.

Goal: Keep persistence representation separate from API request/response representation and business operations.

API schemas → schemas/

Definition: Contains request, response, validation, serialization, and data-transfer schemas used at application boundaries.

Goal: Define clearly what data enters and leaves the API without exposing database models or internal implementation details directly.

Feature/business logic → services/<feature>/

Definition: Contains application behavior that represents what the system actually does, such as authentication, payments, user management, orders, notifications, or reporting.

Goal: Keep business decisions and workflows independent from HTTP routes, database session handling, and external API implementation.

External service clients → clients/

Definition: Contains integrations with external systems such as payment providers, email providers, storage services, third-party APIs, or other backend services.

Goal: Isolate external communication so that changes to an external provider do not spread throughout the business logic.

Generic utilities → utils/

Definition: Contains small, genuinely generic helper functions that do not belong to a particular feature, infrastructure layer, or external integration.

Goal: Prevent repeated low-level operations while avoiding the creation of a large miscellaneous utility layer.

Application exceptions → exceptions/

Definition: Contains reusable application-specific exceptions and error definitions when centralized error handling is required.

Goal: Keep error semantics consistent without scattering custom exception definitions throughout unrelated modules.

***IMP:*** If we add more project folders than you need to understand the goal, intent and the responsibilities of the those fodlers and files they contain and try to accomodate and incorporate them in this docuement. 

**Key rules to apply while writing the code**
Responsibility rule — Every file, class, and function must have one clear primary responsibility. If a function is doing database access, business decisions, HTTP formatting, and external API communication at the same time, it must be reconsidered and separated.
Placement rule — Before creating code, identify what responsibility the code owns and place it in the corresponding layer. Do not choose a location simply because an existing file is convenient.
Route rule — Routes should primarily handle HTTP concerns: receive the request, validate input through schemas/dependencies, call the appropriate application/service operation, and return the response. Business logic should not be implemented directly inside route handlers.
Service rule — Services contain business behavior and application workflows. They should determine what the system should do, rather than knowing unnecessary details about HTTP request handling.
Repository rule — Database repositories should contain persistence operations and queries. They should not decide application business rules merely because they are retrieving data.
Schema rule — API schemas define external data contracts. Do not use database models as a replacement for request/response schemas when doing so exposes internal persistence details or couples the API contract to the database structure.
Model rule — Database models represent persistence. They should not become containers for unrelated API formatting, external service calls, or large business workflows.
Client rule — External API communication belongs inside dedicated clients. Services should call a client that represents the integration rather than constructing raw HTTP requests throughout business logic.
Configuration rule — Environment variables, secrets, URLs, credentials, feature flags, and application configuration must be accessed through the centralized configuration layer. Do not scatter direct environment-variable reads throughout the application.
Dependency rule — Dependency injection should be used to provide resources such as database sessions, authenticated users, configuration, or clients. Dependencies should not become hidden containers for unrelated business logic.
Utility rule — Utilities should remain small and generic. Do not place feature-specific business logic into utils/ merely because it is reusable once or because the correct feature location is less convenient.
Comments rule — Add concise comments where they clarify the purpose, intention, or non-obvious behavior of the code. Comments should explain why something exists or what outcome it provides, not restate obvious Python syntax.
Naming rule — Names of modules, classes, functions, services, repositories, schemas, and clients must clearly communicate their responsibility. Prefer names such as UserService, UserRepository, PaymentClient, and LoginRequest over vague names such as Manager, Helper, or Handler.
Creation rule — Do not create folders, classes, interfaces, repositories, factories, or abstraction layers merely to make the project look architecturally sophisticated. Introduce a layer only when it provides a real separation of responsibility.
Reuse rule — Before creating a new function, service, client, repository, or utility, check whether an existing implementation already owns that responsibility. Extend or reuse it when appropriate instead of creating duplicate behavior.
Data-flow rule — Explicitly understand where data originates, where it is validated, transformed, processed, persisted, and returned. A typical flow should be understandable as:

HTTP Request → Route → Schema/Dependency → Service → Repository/Client → Service → Response Schema → HTTP Response