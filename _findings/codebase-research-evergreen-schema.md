# Codebase Research: Evergreen GraphQL Schema

## Research Question
What does the current Evergreen GraphQL schema look like, what types/fields are defined, and what recent changes have been made? Focus on Project, Patch, Version, Task, User, ProjectSettings, TestResult, and TaskLog types and their associated queries.

## Search Trail

| # | Search Query / Pattern | Files Found | Notes |
|---|------------------------|-------------|-------|
| 1 | `glob **/*.graphql` in `/home/ubuntu/git/evergreen` | ~100+ files | Schema split across `graphql/schema/` and `graphql/tests/` |
| 2 | `read gqlgen.yml` | 1 file | Confirms schema source: `graphql/schema/**/*.graphql` |
| 3 | `read graphql/schema/` directory | 5 entries: `directives.graphql`, `mutation.graphql`, `query.graphql`, `scalars.graphql`, `types/` | Schema is modular, not a single merged file |
| 4 | `read graphql/schema/types/` directory | 28 `.graphql` files | Type definitions split by domain |
| 5 | `grep "type APITask struct"` in `rest/model` | `rest/model/task.go:L27` | Go model backing GraphQL Task type |
| 6 | `grep "type APIPatch struct"` in `rest/model` | `rest/model/patch.go:L22` | Go model backing GraphQL Patch type |
| 7 | `grep "type APIVersion struct"` in `rest/model` | `rest/model/version.go:L16` | Go model backing GraphQL Version type |
| 8 | `git log --oneline -50 -- graphql/` | 50 commits | Recent changes documented below |

## Relevant Files

| # | File Path | Relevance | Key Lines |
|---|-----------|-----------|-----------|
| 1 | `graphql/schema/query.graphql` | All top-level query definitions | L1-L105 |
| 2 | `graphql/schema/types/task.graphql` | Task, TestFilterOptions, TestResult, TaskEndDetail, TaskLogLinks types | L1-L359 |
| 3 | `graphql/schema/types/patch.graphql` | Patch, PatchesInput, Patches types | L1-L209 |
| 4 | `graphql/schema/types/version.graphql` | Version, VersionLite, TaskFilterOptions, SortOrder types | L1-L188 |
| 5 | `graphql/schema/types/user.graphql` | User, UserLite, UserSettings types | L1-L191 |
| 6 | `graphql/schema/types/project.graphql` | Project, ProjectLite, GroupedProjects types | L1-L390 |
| 7 | `graphql/schema/types/project_settings.graphql` | ProjectSettings, ProjectSettingsInput types | L1-L193 |
| 8 | `graphql/schema/types/task_logs.graphql` | TaskLogs, LogMessage, TaskEventLogEntry types | L1-L43 |
| 9 | `graphql/schema/types/annotation.graphql` | Annotation, BuildBaron types | L1-L50 |
| 10 | `graphql/schema/scalars.graphql` | Custom scalars: Time, Duration, StringMap, BooleanMap, Map | L1-L6 |
| 11 | `graphql/schema/directives.graphql` | Auth directives: @requireProjectAccess, @requireAdmin, etc. | L1-L71 |
| 12 | `graphql/query_resolver.go` | All top-level query resolver implementations | L1-L1418 |
| 13 | `graphql/task_resolver.go` | Task field resolvers (ami, annotation, tests, taskLogs, etc.) | L1-L908 |
| 14 | `graphql/patch_resolver.go` | Patch field resolvers (authorDisplayName, versionFull, cost, etc.) | L1-L464 |
| 15 | `graphql/version_resolver.go` | Version + VersionLite field resolvers (tasks, status, etc.) | L1-L722 |
| 16 | `graphql/user_resolver.go` | User + UserLite field resolvers (patches, permissions, etc.) | L1-L96 |
| 17 | `graphql/project_resolver.go` | Project + ProjectLite field resolvers (isFavorite, patches) | L1-L48 |
| 18 | `graphql/project_settings_resolver.go` | ProjectSettings field resolvers (aliases, vars, subscriptions, etc.) | L1-L76 |
| 19 | `graphql/task_logs_resolver.go` | TaskLogs field resolvers (agentLogs, allLogs, eventLogs, etc.) | L1-L64 |
| 20 | `graphql/util.go` | Helper functions: getTask, convertTestFilterOptions, generateBuildVariants | L1-L1684 |
| 21 | `gqlgen.yml` | Maps GraphQL types to Go models; identifies which fields have custom resolvers | L1-L1054 |
| 22 | `rest/model/task.go` | APITask Go struct backing GraphQL Task | L27-L141 |
| 23 | `rest/model/patch.go` | APIPatch Go struct backing GraphQL Patch | L22-L83 |
| 24 | `rest/model/version.go` | APIVersion Go struct backing GraphQL Version | L16-L68 |
| 25 | `rest/model/user.go` | APIDBUser Go struct backing GraphQL User | L18-L30 |

---

## Code Path Map

### Entry Point: `Query.projects` (`graphql/schema/query.graphql:L46`)
```
projects: [GroupedProjects!]!
```
1. Resolver at `graphql/query_resolver.go:L475` — `func (r *queryResolver) Projects(ctx context.Context) ([]*GroupedProjects, error)`
2. Gets viewable project IDs from current user → `usr.GetViewableProjects(ctx)`
3. Fetches merged enabled project refs → `model.FindMergedEnabledProjectRefsByIds(ctx, viewableProjectIds...)`
4. Groups projects by owner/repo → `groupProjects(ctx, allProjects, false)`
5. Returns `[]*GroupedProjects` where each has `.groupDisplayName`, `.projects: [Project!]!`, `.repo: RepoRef`

### Entry Point: `Query.project(projectIdentifier: ...)` (`graphql/schema/query.graphql:L45`)
```
project(projectIdentifier: String! @requireProjectAccess(permission: TASKS, access: VIEW)): Project!
```
1. Resolver at `graphql/query_resolver.go:L461` — `func (r *queryResolver) Project(ctx context.Context, projectIdentifier string) (*restModel.APIProjectRef, error)`
2. Finds project by ID → `data.FindProjectById(ctx, projectIdentifier, true, false)`
3. Converts to API model → `restModel.APIProjectRef.BuildFromService(ctx, *project)`
4. Returns `*restModel.APIProjectRef` (mapped to `Project` GraphQL type per `gqlgen.yml:L628`)

### Entry Point: `Query.projectSettings(projectIdentifier: ...)` (`graphql/schema/query.graphql:L52`)
```
projectSettings(projectIdentifier: String! @requireProjectAccess(permission: SETTINGS, access:VIEW)): ProjectSettings!
```
1. Resolver at `graphql/query_resolver.go:L507` — `func (r *queryResolver) ProjectSettings(ctx context.Context, projectIdentifier string) (*restModel.APIProjectSettings, error)`
2. Finds **branch** project ref (not merged) → `model.FindBranchProjectRef(ctx, projectIdentifier)`
3. Builds `APIProjectSettings{ProjectRef: APIProjectRef{...}}`
4. If project doesn't use repo settings, defaults unset booleans
5. Custom field resolvers for ProjectSettings (at `graphql/project_settings_resolver.go`):
   - `aliases` → `getAPIAliasesForProject(ctx, projectId)` (L17)
   - `githubAppAuth` → `githubapp.FindOneGitHubAppAuth(ctx, projectId)` (L22)
   - `githubWebhooksEnabled` → checks GitHub app installation (L38)
   - `vars` → `getRedactedAPIVarsForProject(ctx, projectId)` (L57)
   - `subscriptions` → `getAPISubscriptionsForOwner(ctx, projectId, OwnerTypeProject)` (L52)

### Entry Point: `Query.user(userId: ...)` (`graphql/schema/query.graphql:L82`)
```
user(userId: String): User!
```
1. Resolver at `graphql/query_resolver.go:L753` — `func (r *queryResolver) User(ctx context.Context, userID *string) (*restModel.APIDBUser, error)`
2. If `userID` is nil, uses current authenticated user
3. Otherwise looks up user by ID → `user.FindOneById(ctx, ...)`
4. Converts to API model → `restModel.APIDBUser.BuildFromService(*usr)`
5. Custom field resolvers for User (at `graphql/user_resolver.go`):
   - `patches(patchesInput: PatchesInput!)` → returns empty `Patches{}` struct; actual data loaded by Patches field resolvers (L27)
   - `permissions` → returns `Permissions{UserID: ...}` (L33)
   - `subscriptions` → `getAPISubscriptionsForOwner(ctx, userId, OwnerTypePerson)` (L38)
   - `betaFeatures` → converts from API model (L16)
   - `parsleyFilters` → converts from API model (L22)

### Entry Point: `User.patches` / `UserLite.patches` (`graphql/schema/types/user.graphql:L98` and `L186`)
```
patches(patchesInput: PatchesInput!): Patches
```
1. Both `userResolver.Patches` (L27) and `userLiteResolver.Patches` (L48) return empty `Patches{}` structs
2. Actual patch data is loaded lazily by `Patches` field resolvers at `graphql/patch_resolver.go`:
   - `patchesResolver.Patches` (L423) → calls `patch.ProjectOrUserPatchesPage(ctx, opts)` 
   - `patchesResolver.FilteredPatchCount` (L408) → calls `patch.ProjectOrUserPatchesCount(ctx, opts)`
3. `PatchesInput` args (from `graphql/schema/types/patch.graphql:L14`):
   - `countLimit: Int = 10000`
   - `limit: Int! = 0`
   - `onlyMergeQueue: Boolean`
   - `includeHidden: Boolean = false`
   - `page: Int! = 0`
   - `patchName: String! = ""`
   - `statuses: [String!]! = []`
   - `requesters: [String!]`

### Entry Point: `Query.patch(patchId: ...)` (`graphql/schema/query.graphql:L39`)
```
patch(patchId: String! @requireProjectAccess(permission: TASKS, access: VIEW)): Patch!
```
1. Resolver at `graphql/query_resolver.go:L432` — `func (r *queryResolver) Patch(ctx context.Context, patchID string) (*restModel.APIPatch, error)`
2. Finds patch by ID → `data.FindPatchById(ctx, patchID)`
3. Returns `*restModel.APIPatch` (mapped to `Patch` GraphQL type per `gqlgen.yml:L548`)
4. Custom field resolvers for Patch (at `graphql/patch_resolver.go`):
   - `authorDisplayName` → looks up user by author ID, returns `usr.DisplayName()` (L25)
   - `builds` → finds builds by version ID (L38)
   - `duration` → computes timeTaken/makespan from tasks (L54)
   - `includedLocalModules` → converts slice (L128)
   - `parameters` → redacts secrets in parameter values (L138)
   - `cost` / `predictedCost` → rounds cost values (L386-L405)
   - `versionFull` → calls `model.VersionFindOneIdWithBuildVariants(ctx, versionID)` then builds APIVersion (L368)

### Entry Point: `Patch.versionFull` (`graphql/schema/types/patch.graphql:L101`)
```
versionFull: Version
```
1. Resolver at `graphql/patch_resolver.go:L368` — `func (r *patchResolver) VersionFull(ctx context.Context, obj *restModel.APIPatch) (*restModel.APIVersion, error)`
2. Gets version ID from `obj.Version` (pointer to string)
3. If empty, returns nil
4. Finds version with build variants → `model.VersionFindOneIdWithBuildVariants(ctx, versionID)`
5. Builds API version → `restModel.APIVersion.BuildFromService(ctx, *v)`

### Entry Point: `Query.version(versionId: ...)` (`graphql/schema/query.graphql:L100`)
```
version(versionId: String! @requireProjectAccess(permission: TASKS, access: VIEW)): Version!
```
1. Resolver at `graphql/query_resolver.go:L1376` — `func (r *queryResolver) Version(ctx context.Context, versionID string) (*restModel.APIVersion, error)`
2. Finds version with build variants → `model.VersionFindOneIdWithBuildVariants(ctx, versionID)`
3. Builds API version → `restModel.APIVersion.BuildFromService(ctx, *v)`

### Entry Point: `Version.tasks(options: TaskFilterOptions!)` (`graphql/schema/types/version.graphql:L86`)
```
tasks(options: TaskFilterOptions!): VersionTasks!
```
1. Resolver at `graphql/version_resolver.go:L298` — `func (r *versionResolver) Tasks(ctx context.Context, obj *restModel.APIVersion, options TaskFilterOptions) (*VersionTasks, error)`
2. Parses TaskFilterOptions: page, limit, variant, taskName, sorts, statuses, baseStatuses
3. Finds base version for base status lookups → `model.FindBaseVersionForVersion(ctx, versionID)`
4. Calls `task.GetTasksByVersion(ctx, versionID, opts)` — returns `([]task.Task, int, error)`
5. Converts each task to APITask → `restModel.APITask.BuildFromService(ctx, &t, nil)`
6. Returns `VersionTasks{Count: count, Data: apiTasks}`

### Entry Point: `Query.task(taskId: ..., execution: ...)` (`graphql/schema/query.graphql:L66`)
```
task(taskId: String! @requireProjectAccess(permission: TASKS, access: VIEW), execution: Int): Task
```
1. Resolver at `graphql/query_resolver.go:L646` — `func (r *queryResolver) Task(ctx context.Context, taskID string, execution *int) (*restModel.APITask, error)`
2. Delegates to `getTask(ctx, taskID, execution, r.sc.GetURL())` at `graphql/util.go:L314`
3. `getTask` calls `task.FindByIdExecution(ctx, taskID, execution)` then `getAPITaskFromTask`
4. `getAPITaskFromTask` at L302 calls `restModel.APITask.BuildFromService(ctx, &task, &restModel.APITaskArgs{LogURL: url})`

### Task field resolvers of special interest (`graphql/task_resolver.go`):
- **`ami`** (L69): Calls `obj.GetAMI(ctx)` which looks up the host's AMI from the host collection
- **`hostId`**: Directly from `restModel.APITask.HostId` — no custom resolver
- **`distroId`**: Directly from `restModel.APITask.DistroId` — no custom resolver
- **`imageId`** (L525): Custom resolver — calls `distro.GetImageIDFromDistro(ctx, distroID)` to look up image from distro
- **`details`**: Directly from `restModel.APITask.Details` (ApiTaskEndDetail) — no custom resolver
- **`logs`**: Directly from `restModel.APITask.Logs` (LogLinks) — no custom resolver
- **`taskLogs`** (L731): Custom resolver — returns `&TaskLogs{TaskID: ..., Execution: ...}`; individual log resolvers in `task_logs_resolver.go`
- **`tests(opts: TestFilterOptions)`** (L790): Custom resolver — calls `dbTask.GetTestResults(ctx, env, filterOpts)` and decorates quarantine status

### Entry Point: `Task.tests(opts: TestFilterOptions)` (`graphql/schema/types/task.graphql:L153`)
```
tests(opts: TestFilterOptions): TaskTestResult!
```
1. Resolver at `graphql/task_resolver.go:L790` — `func (r *taskResolver) Tests(...)`
2. Early exit optimization: if filtering only failure statuses and `!obj.ResultsFailed`, returns empty
3. Finds task by ID and execution → `task.FindOneIdAndExecution(ctx, taskID, obj.Execution)`
4. Converts `TestFilterOptions` → `task.FilterOptions` via `convertTestFilterOptions` at `util.go:L970`
5. Gets test results → `dbTask.GetTestResults(ctx, env, filterOpts)`
6. Decorates quarantine status → `data.DecorateQuarantineStatus(ctx, dbTask, taskResults.Results)`
7. Converts each result → `restModel.APITest.BuildFromService(&t, apiTestArgs)`
8. Returns `TaskTestResult{TestResults, TotalTestCount, FilteredTestCount}`

---

## Detailed Schema Definitions

### Patch type (`graphql/schema/types/patch.graphql:L67-L107`)
```graphql
type Patch {
  id: ID!
  activated: Boolean!
  alias: String
  author: String!
  authorDisplayName: String!        # Custom resolver: looks up user display name
  builds: [Build!]!
  childPatchAliases: [ChildPatchAlias!]
  childPatches: [Patch!]
  createTime: Time
  ingestTime: Time
  description: String!
  duration: PatchDuration
  generatedTaskCounts: [GeneratedTaskCountResults!]!
  githash: String!
  githubPatchData: GithubPatch
  hidden: Boolean!
  includedLocalModules: [IncludedLocalModule!]!  # Custom resolver
  moduleCodeChanges: [ModuleCodeChange!]!
  parameters: [Parameter!]!          # Custom resolver (redacts secrets)
  patchNumber: Int!
  patchTriggerAliases: [PatchTriggerAlias!]!
  project: PatchProject
  projectMetadata: Project
  status: String!
  taskCount: Int
  tasks: [String!]!
  taskStatuses: [String!]!
  time: PatchTime
  user: User! @deprecated(reason: "Use userLite instead.")
  userLite: UserLite!
  variants: [String!]!
  variantsTasks: [VariantTask!]!
  version: VersionLite
  versionFull: Version               # Custom resolver: fetches full APIVersion
  cost: Cost                          # Custom resolver: rounds values
  predictedCost: Cost                 # Custom resolver: rounds values
  invalidatedByUpstream: Boolean!
}
```

**Note on `projectIdentifier`**: The Patch type does NOT have a `projectIdentifier` field directly. The project identifier is available via `Patch.projectMetadata.identifier` or from the underlying `APIPatch.ProjectIdentifier` field (Go struct field at `rest/model/patch.go:L32`), but it is NOT exposed as a top-level Patch field in the GraphQL schema.

### Version type (`graphql/schema/types/version.graphql:L52-L95`)
```graphql
type Version {
  id: String!
  activated: Boolean
  author: String!
  authorEmail: String!
  baseVersion: Version
  branch: String!
  buildVariants(options: BuildVariantOptions!): [GroupedBuildVariant!]
  buildVariantStats(options: BuildVariantOptions!): [GroupedTaskStatusCount!]
  childVersions: [Version!]
  cost: Cost                         # Custom resolver: rounds values
  createTime: Time!
  ingestTime: Time
  errors: [String!]!
  externalLinksForMetadata: [ExternalLinkForMetadata!]!
  finishTime: Time
  generatedTaskCounts: [GeneratedTaskCountResults!]!
  gitTags: [GitTag!]
  ignored: Boolean!
  isPatch: Boolean!
  manifest: Manifest
  message: String!
  order: Int!
  parameters: [Parameter!]!
  patch: Patch
  predictedCost: Cost
  previousVersion: Version
  projectMetadata: Project
  repo: String!
  requester: String!
  revision: String!
  startTime: Time
  status: String!                     # Custom resolver: computes display status
  taskCount(options: TaskCountOptions): Int
  tasks(options: TaskFilterOptions!): VersionTasks!   # Custom resolver
  taskStatuses: [String!]!
  taskStatusStats(options: BuildVariantOptions!): TaskStats
  upstreamProject: UpstreamProject
  user: User! @deprecated(reason: "Use userLite instead.")
  userLite: UserLite!
  versionTiming: VersionTiming
  warnings: [String!]!
  waterfallBuilds: [WaterfallBuild!]
}
```

### Task type (`graphql/schema/types/task.graphql:L51-L159`)
```graphql
type Task {
  aborted: Boolean!
  abortInfo: AbortInfo
  activated: Boolean!
  activatedBy: String
  activatedTime: Time
  ami: String                        # Custom resolver: fetches from host
  annotation: Annotation
  id: String!
  baseStatus: String                 # Custom resolver
  baseTask: Task                     # Custom resolver
  blocked: Boolean!
  buildId: String!
  buildVariant: String!
  buildVariantDisplayName: String    # Custom resolver
  canAbort: Boolean!
  canDisable: Boolean!
  canModifyAnnotation: Boolean!      # Custom resolver
  canOverrideDependencies: Boolean!  # Custom resolver
  canRestart: Boolean!
  canSchedule: Boolean!
  canSetPriority: Boolean!
  canUnschedule: Boolean!
  createTime: Time
  dependsOn: [Dependency!]
  details: TaskEndDetail
  dispatchTime: Time
  displayName: String!
  displayOnly: Boolean
  displayStatus: String!
  displayTask: Task
  distroId: String!
  errors: [String!]                  # Custom resolver
  estimatedStart: Duration           # Custom resolver
  execution: Int!
  executionSteps: [TaskExecutionStep!]!  # Custom resolver
  executionTasks: [String!]
  executionTasksFull: [Task!]        # Custom resolver
  expectedDuration: Duration
  failedTestCount: Int!              # Custom resolver
  files: TaskFiles!
  finishTime: Time
  generatedBy: String
  generatedByName: String            # Custom resolver
  generateTask: Boolean
  generator: Task                    # Custom resolver
  hasTestResults: Boolean!
  hostId: String
  imageId: String!                   # Custom resolver: looks up from distro
  ingestTime: Time
  isAutomaticRestart: Boolean!
  isPerfPluginEnabled: Boolean!      # Custom resolver
  latestExecution: Int!              # Custom resolver
  logs: TaskLogLinks!
  minQueuePosition: Int!             # Custom resolver
  nextTask: Task
  nextTaskCompleted: Task
  nextTaskFailing: Task
  nextTaskPassing: Task
  order: Int!
  invalidatedByUpstream: Boolean     # Custom resolver
  patch: Patch                       # Custom resolver
  patchNumber: Int                   # Custom resolver
  prevTask: Task
  prevTaskCompleted: Task
  prevTaskFailing: Task
  prevTaskPassing: Task
  priority: Int
  project: Project                   # Custom resolver
  requester: String!
  resetWhenFinished: Boolean!
  revision: String
  scheduledTime: Time
  spawnHostLink: String              # Custom resolver
  startTime: Time
  status: String!
  tags: [String!]!
  taskGroup: String
  taskGroupMaxHosts: Int
  stepbackInfo: StepbackInfo
  taskLogs: TaskLogs!                # Custom resolver
  taskCost: Cost                     # Custom resolver: rounds values
  predictedTaskCost: Cost
  taskOwnerTeam: TaskOwnerTeam       # Custom resolver
  tests(opts: TestFilterOptions): TaskTestResult!  # Custom resolver
  testSelectionEnabled: Boolean!
  timeTaken: Duration
  totalTestCount: Int!               # Custom resolver
  version: VersionLite!              # Custom resolver (returns model.Version, not APIVersion)
  versionMetadata: Version!          # Custom resolver (returns full APIVersion)
}
```

### User type (`graphql/schema/types/user.graphql:L92-L104`)
```graphql
type User {
  betaFeatures: BetaFeatures         # Custom resolver
  displayName: String
  emailAddress: String
  hasTokenExchangePending: Boolean!
  parsleyFilters: [ParsleyFilter!]   # Custom resolver
  patches(patchesInput: PatchesInput!): Patches  # Custom resolver
  permissions: Permissions           # Custom resolver
  settings: UserSettings
  tokenAccessTokenExpiresAt: Time
  subscriptions: [GeneralSubscription!]  # Custom resolver
  userId: String!
}
```

### UserLite type (`graphql/schema/types/user.graphql:L179-L191`)
```graphql
type UserLite {
  betaFeatures: BetaFeatures
  displayName: String
  emailAddress: String
  hasTokenExchangePending: Boolean!   # Custom resolver
  id: String!
  parsleyFilters: [ParsleyFilter!]
  patches(patchesInput: PatchesInput!): Patches  # Custom resolver
  permissions: Permissions            # Custom resolver
  settings: UserSettings             # Custom resolver
  subscriptions: [GeneralSubscription!]  # Custom resolver
  tokenAccessTokenExpiresAt: Time    # Custom resolver
}
```

### Project type (`graphql/schema/types/project.graphql:L242-L296`)
```graphql
type Project {
  id: String!
  admins: [String!]
  banner: ProjectBanner
  batchTime: Int!
  branch: String!
  buildBaronSettings: BuildBaronSettings!
  commitQueue: CommitQueueParams!
  deactivatePrevious: Boolean
  debugSpawnHostsDisabled: Boolean
  disabledStatsCache: Boolean
  dispatchingDisabled: Boolean
  waterfallDisabled: Boolean
  displayName: String!
  enabled: Boolean
  externalLinks: [ExternalLink!]
  githubChecksEnabled: Boolean
  githubDynamicTokenPermissionGroups: [GitHubDynamicTokenPermissionGroup!]!
  githubPermissionGroupByRequester: StringMap
  githubPRTriggerAliases: [String!]
  githubMQTriggerAliases: [String!]
  gitTagAuthorizedTeams: [String!]
  gitTagAuthorizedUsers: [String!]
  gitTagVersionsEnabled: Boolean
  hidden: Boolean
  identifier: String!
  isFavorite: Boolean!               # Custom resolver
  manualPrTestingEnabled: Boolean
  notifyOnBuildFailure: Boolean
  oldestAllowedMergeBase: String!
  owner: String!
  parsleyFilters: [ParsleyFilter!]   # Custom resolver
  patches(patchesInput: PatchesInput!): Patches!  # Custom resolver
  patchingDisabled: Boolean
  patchTriggerAliases: [PatchTriggerAlias!]
  perfEnabled: Boolean
  periodicBuilds: [PeriodicBuild!]
  projectHealthView: ProjectHealthView!
  prTestingEnabled: Boolean
  remotePath: String!
  repo: String!
  repoRefId: String!
  repotrackerDisabled: Boolean
  repotrackerError: RepotrackerError
  restricted: Boolean
  runEveryMainlineCommit: Boolean
  spawnHostScriptPath: String!
  stepbackDisabled: Boolean
  stepbackBisect: Boolean
  taskAnnotationSettings: TaskAnnotationSettings!
  testSelection: TestSelectionSettings
  triggers: [TriggerAlias!]
  versionControlEnabled: Boolean
  workstationConfig: WorkstationConfig!
}
```

### ProjectSettings type (`graphql/schema/types/project_settings.graphql:L95-L102`)
```graphql
type ProjectSettings {
  aliases: [ProjectAlias!]           # Custom resolver
  githubAppAuth: GithubAppAuth       # Custom resolver
  githubWebhooksEnabled: Boolean!    # Custom resolver
  projectRef: Project @requireProjectSettingsAccess
  subscriptions: [GeneralSubscription!]  # Custom resolver
  vars: ProjectVars                  # Custom resolver
}
```

### TaskFilterOptions input (`graphql/schema/types/version.graphql:L14-L23`)
```graphql
input TaskFilterOptions {
  baseStatuses: [String!] = []
  includeNeverActivatedTasks: Boolean = false
  limit: Int = 0
  page: Int = 0
  sorts: [SortOrder!]
  statuses: [String!] = []
  taskName: String
  variant: String
}
```

### TestFilterOptions input (`graphql/schema/types/task.graphql:L14-L22`)
```graphql
input TestFilterOptions {
  testName: String
  excludeDisplayNames: Boolean
  statuses: [String!]
  groupID: String
  sort: [TestSortOptions!]
  limit: Int
  page: Int
}
```

### TestResult type (`graphql/schema/types/task.graphql:L284-L298`)
```graphql
type TestResult {
  id: String!
  baseStatus: String
  duration: Float
  endTime: Time
  execution: Int
  exitCode: Int
  groupID: String
  isManuallyQuarantined: Boolean!
  logs: TestLog!
  startTime: Time
  status: String!
  taskId: String
  testFile: String!
}
```

### TaskLogs type (`graphql/schema/types/task_logs.graphql:L6-L14`)
```graphql
type TaskLogs {
  agentLogs: [LogMessage!]!          # Custom resolver
  allLogs: [LogMessage!]!            # Custom resolver
  eventLogs: [TaskEventLogEntry!]!   # Custom resolver
  execution: Int!
  systemLogs: [LogMessage!]!         # Custom resolver
  taskId: String!
  taskLogs: [LogMessage!]!           # Custom resolver
}
```

### TaskLogLinks type (`graphql/schema/types/task.graphql:L230-L235`)
```graphql
type TaskLogLinks {
  agentLogLink: String
  allLogLink: String
  systemLogLink: String
  taskLogLink: String
}
```

### TaskEndDetail type (`graphql/schema/types/task.graphql:L211-L223`)
```graphql
type TaskEndDetail {
  description: String
  diskDevices: [String!]!
  failingCommand: String
  failureMetadataTags: [String!]!
  oomTracker: OomTrackerInfo!
  otherFailingCommands: [FailingCommand!]!
  status: String!
  timedOut: Boolean
  timeoutType: String
  traceID: String
  type: String!
}
```

### VersionTasks type (`graphql/schema/types/version.graphql:L97-L100`)
```graphql
type VersionTasks {
  count: Int!
  data: [Task!]!
}
```

---

## Architectural Context

### Module/Package
The GraphQL layer lives in the `graphql` package at `/home/ubuntu/git/evergreen/graphql/`. It uses [gqlgen](https://gqlgen.com/) (Go code generation) configured via `gqlgen.yml` at the project root.

### Schema Layout
- **No merged schema file**: The schema is split across `graphql/schema/**/*.graphql` files. gqlgen reads all of them and merges them at build time into `graphql/generated.go`.
- **Type definitions** are in `graphql/schema/types/*.graphql` (28 files)
- **Query definitions** are in `graphql/schema/query.graphql`
- **Mutation definitions** are in `graphql/schema/mutation.graphql`
- **Custom scalars** are in `graphql/schema/scalars.graphql` (Time, Duration, StringMap, BooleanMap, Map)
- **Directives** are in `graphql/schema/directives.graphql` (@requireProjectAccess, @requireAdmin, etc.)

### Model Mapping
The `gqlgen.yml` maps GraphQL types to Go structs, primarily from the `rest/model` package:
- `Patch` → `rest/model.APIPatch`
- `Task` → `rest/model.APITask`
- `Version` → `rest/model.APIVersion`
- `User` → `rest/model.APIDBUser`
- `Project` → `rest/model.APIProjectRef`
- `ProjectSettings` → `rest/model.APIProjectSettings`
- `TestResult` → `rest/model.APITest`
- `UserLite` → `model/user.DBUser` (bypasses API layer — "Lite" pattern)
- `VersionLite` → `model.Version` (bypasses API layer)
- `ProjectLite` → `model.ProjectRef` (bypasses API layer)

### Custom Resolvers
Fields that require computation beyond simple struct field mapping are marked with `resolver: true` in `gqlgen.yml`. Key examples:
- **Task**: `ami`, `annotation`, `baseTask`, `baseStatus`, `buildVariantDisplayName`, `canModifyAnnotation`, `estimatedStart`, `executionSteps`, `executionTasksFull`, `hostId` (no—direct), `imageId`, `isPerfPluginEnabled`, `latestExecution`, `minQueuePosition`, `patch`, `project`, `spawnHostLink`, `taskCost`, `taskLogs`, `taskOwnerTeam`, `tests`, `version`, `versionMetadata`
- **Patch**: `cost`, `predictedCost`, `includedLocalModules`, `parameters`
- **Patches**: `filteredPatchCount`, `patches`
- **Version**: `cost`, `status`
- **VersionLite**: `status`
- **Project**: `patches`
- **ProjectSettings**: `githubWebhooksEnabled`, `vars`, `aliases`, `subscriptions`, `githubAppAuth`
- **User**: `patches`, `subscriptions`
- **TaskLogs**: `eventLogs`, `taskLogs`, `systemLogs`, `agentLogs`, `allLogs`

### Dependencies
- Internal: `model/task`, `model/patch`, `model/version`, `model/build`, `model/user`, `model/host`, `model/distro`, `model/annotations`, `rest/data`, `rest/model`, `graphql/loaders`
- External: `github.com/99designs/gqlgen`, `github.com/vektah/gqlparser/v2`, `github.com/evergreen-ci/utility`, `go.mongodb.org/mongo-driver/bson`

### Data Loaders
The `graphql/loaders/` package provides batched data loading (N+1 prevention) for:
- `GetVersion(ctx, versionID)` — used by task_resolver.go, version_resolver.go
- `GetProject(ctx, projectID)` — used by task_resolver.go, version_resolver.go
- `GetUser(ctx, userID)` — used by patch_resolver.go, version_resolver.go
- `PreloadVersions(ctx, versionIDs)` — used in task history queries
- `PreloadProjects(ctx, projectIDs)` — used in patches query

### Related Tests
Test files are in `graphql/tests/` organized by query/type:
- `graphql/tests/user/patches/queries/` — User patches query tests
- `graphql/tests/version/tasks/queries/` — Version tasks query tests
- `graphql/tests/projectSettings/` — Project settings query tests
- `graphql/tests/task/abortInfo/queries/` — Task abort info tests
- Integration test: `graphql/integration_atomic_test_util.go`

---

## Recent Changes (Last ~50 commits touching GraphQL files)

Key recent changes from `git log --oneline -50`:

| Commit | Description |
|--------|-------------|
| `6134900f2` | DEVPROD-36017: Add `baseVersion` resolver to VersionLite |
| `034fcc7ef` | DEVPROD-34589: Use dataloaders for project lookups (performance) |
| `025d04f64` | DEVPROD-34996: Complete UserLite type (add missing fields) |
| `8e7e2f8b7` | DEVPROD-35125: Add `isPatch` resolver to VersionLite |
| `1c9e4ff52` | DEVPROD-32825: Add `waterfallDisabled` project setting |
| `d9115705f` | DEVPROD-30358: Add quarantine status/unquarantine TSS APIs |
| `262050c6e` | DEVPROD-32731: Add `childVersions` to VersionLite |
| `43d190b32` | DEVPROD-31541: Expose `LogsToMerge` field from GraphQL |
| `51aca3281` | DEVPROD-31754: Add `Task.isAutomaticRestart` GraphQL field |
| `c0c879e91` | DEVPROD-26469: Exposing S3 Costs Modal on Task Page |
| `504adf993` | DEVPROD-27060: Add child patch costs to total patch cost |
| `1d61440e1` / `5e4d4932c` | DEVPROD-31963: Add Total Cost to Cost struct and API |
| `39a7c2d56` | DEVPROD-28627: Add `invalidatedByUpstream` field to Patch and Task |
| `78624eabb` | DEVPROD-31530: Add `status` and `taskStatusStats` resolvers to VersionLite |
| `8be0d3532` | DEVPROD-31587: Create `TaskHistoryByCreateTime` query |
| `159b5d5b3` | DEVPROD-30693: Remove `User.ParsleySettings` |
| `d5b8c71d9` | DEVPROD-31588: Add `ingestTime` to patch and version document |
| `cb204b514` | DEVPROD-31492: Calculate and Add S3 cost fields for Tasks |
| `170cba0cb` | DEVPROD-30130: Expose `AssociatedLinks` field from GraphQL |
| `c7ab23d45` | DEVPROD-29312: Add "next" task resolvers |
| `d53501c6c` | DEVPROD-29312: Add "previous" task resolvers |
| `8b7c6af63` | DEVPROD-33014: Delete deprecated `volume` and `host` GraphQL arguments |
| `53793f2bd` | DEVPROD-33014: Standardize `volumeId`/`hostId` in GraphQL params |
| `a66bb2f27` | DEVPROD-25338: Remove EC2-on-demand constant and GQL enum |

---

## Summary

The Evergreen GraphQL schema is defined across 28+ `.graphql` files in `graphql/schema/types/` and loaded via gqlgen. There is **no single merged schema file** — gqlgen reads all `graphql/schema/**/*.graphql` and generates `graphql/generated.go`. 

The key types of interest are:

- **Patch** (`graphql/schema/types/patch.graphql`) — 30+ fields including `githash`, `authorDisplayName` (custom resolver), `patchNumber`, `versionFull` (custom resolver returning full Version), `cost`/`predictedCost` (custom resolvers with rounding). **Note**: `projectIdentifier` is NOT a top-level Patch field; it's accessible via `projectMetadata.identifier`.

- **Version** (`graphql/schema/types/version.graphql`) — 35+ fields. `tasks(options: TaskFilterOptions!)` returns `VersionTasks{count, data}`. The `TaskFilterOptions` input supports `statuses`, `baseStatuses`, `variant`, `taskName`, `sorts`, `limit`, `page`, `includeNeverActivatedTasks`. There's also a `VersionLite` type that bypasses the API layer.

- **Task** (`graphql/schema/types/task.graphql`) — 60+ fields. `ami` is a custom resolver fetching from the host. `imageId` is a custom resolver looking up from the distro. `distroId` and `hostId` are direct struct fields. `logs` returns `TaskLogLinks` (URLs), while `taskLogs` returns `TaskLogs` (actual log content). `tests(opts: TestFilterOptions)` returns `TaskTestResult{testResults, totalTestCount, filteredTestCount}`. `details` returns `TaskEndDetail`.

- **User** (`graphql/schema/types/user.graphql`) — Has `patches(patchesInput: PatchesInput!)` field returning `Patches{filteredPatchCount, patches}`. The Patches resolver lazily loads data. `UserLite` is a parallel type that bypasses the API layer.

- **Project** (`graphql/schema/types/project.graphql`) — 45+ fields. `isFavorite` and `patches` are custom resolvers. `identifier` field is the project identifier string.

- **ProjectSettings** (`graphql/schema/types/project_settings.graphql`) — 5 fields, most with custom resolvers (`aliases`, `githubAppAuth`, `githubWebhooksEnabled`, `vars`, `subscriptions`). `projectRef` returns a `Project` type.

- **TestResult** (`graphql/schema/types/task.graphql`) — Fields include `id`, `baseStatus`, `duration`, `endTime`, `execution`, `exitCode`, `groupID`, `isManuallyQuarantined`, `logs: TestLog!`, `startTime`, `status`, `taskId`, `testFile`.

- **TaskLogs** (`graphql/schema/types/task_logs.graphql`) — All 6 fields have custom resolvers: `agentLogs`, `allLogs`, `eventLogs`, `systemLogs`, `taskLogs`, plus `execution` and `taskId`.

Recent changes include adding `VersionLite` resolvers (baseVersion, isPatch, childVersions, status, taskStatusStats), completing `UserLite`, adding S3 cost tracking fields, adding `invalidatedByUpstream` to Patch and Task, and adding next/previous task resolvers.
