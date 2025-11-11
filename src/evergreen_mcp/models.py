from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# Enums for constrained values
class LogType(str, Enum):
    """Valid log types for Evergreen"""

    TASK = "task"
    SYSTEM = "system"
    AGENT = "agent"
    EVENT = "event"
    ALL = "all"


class TestStatus(str, Enum):
    """Valid test statuses"""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskEndDetails(BaseModel):
    """Model for task end details"""

    status: str = Field(description="Status of the task after completion")
    other_failing_commands: Optional[List[Dict[str, str]]] = Field(
        default=None, description="List of other failing commands in the task"
    )
    modules: Dict = Field(default_factory=dict, description="Modules information")
    trace_id: Optional[str] = Field(default=None, description="Trace ID for the task")


class Task(BaseModel):
    """Model for task information"""

    id: str = Field(description="Task ID")
    status: str = Field(description="Current status of the task")
    task_end_details: Optional[TaskEndDetails] = Field(
        default=None, description="Details about the task completion"
    )
    display_name: str = Field(description="Display name for the task")
    time_taken: Optional[int] = Field(
        default=None, description="Time taken for the task in nanoseconds"
    )
    activated: bool = Field(description="Whether the task is activated")
    blocked: bool = Field(description="Whether the task is blocked")
    start_time: Optional[int] = Field(
        default=None, description="Start time of the task in nanoseconds"
    )


class TaskStatusCount(BaseModel):
    """Model for task status counts in a build"""

    succeeded: int = Field(default=0, description="Count of succeeded tasks")
    failed: Optional[int] = Field(default=0, description="Count of failed tasks")
    started: Optional[int] = Field(default=0, description="Count of started tasks")
    undispatched: Optional[int] = Field(
        default=0, description="Count of undispatched tasks"
    )
    inactive: Optional[int] = Field(default=0, description="Count of inactive tasks")
    dispatched: Optional[int] = Field(
        default=0, description="Count of dispatched tasks"
    )
    unscheduled: Optional[int] = Field(
        default=0, description="Count of unscheduled tasks"
    )
    setup_failed: Optional[int] = Field(
        default=0, description="Count of setup_failed tasks"
    )
    timed_out: Optional[int] = Field(default=0, description="Count of timed_out tasks")
    aborted: Optional[int] = Field(default=0, description="Count of aborted tasks")
    system_failed: Optional[int] = Field(
        default=0, description="Count of system_failed tasks"
    )
    system_unresponsive: Optional[int] = Field(
        default=0, description="Count of system_unresponsive tasks"
    )
    system_timed_out: Optional[int] = Field(
        default=0, description="Count of system_timed_out tasks"
    )
    test_timed_out: Optional[int] = Field(
        default=0, description="Count of test_timed_out tasks"
    )

    def has_only_successful_tasks(self) -> bool:
        """Check if all tasks have succeeded with no failures of any kind"""
        if self.succeeded == 0:
            return False

        # Check that no other status has non-zero count
        for field_name, value in self.model_dump().items():
            if field_name != "succeeded" and value > 0:
                return False

        return True


class BuildInfo(BaseModel):
    """Model for build information"""

    id: str = Field(description="Build ID")
    active: bool = Field(description="Whether the build is active")
    version: str = Field(description="Version ID for this build")
    tasks: Optional[List[Task]] = Field(
        default=None, description="List of tasks in this build"
    )
    taskStatusCount: TaskStatusCount = Field(
        description="Status counts for tasks in this build"
    )


class BuildVariantInfo(BaseModel):
    """Model for build variant information"""

    id: str = Field(description="Build variant ID")
    display_name: str = Field(description="Display name for the build variant")


class BuildVariant(BaseModel):
    """Model for a build variant (row)"""

    build_variant: BuildVariantInfo = Field(description="Build variant information")
    builds: Dict[str, BuildInfo] = Field(
        description="Dictionary of build info keyed by version ID"
    )


class Version(BaseModel):
    """Model for version details"""

    rolled_up: bool = Field(description="Whether the version is rolled up")
    ids: List[str] = Field(description="List of version IDs")
    messages: List[str] = Field(description="List of commit messages")
    authors: List[str] = Field(description="List of commit authors")
    create_times: List[str] = Field(description="List of creation times")
    revisions: List[str] = Field(description="List of revision hashes")
    revision_order: int = Field(description="Revision order number")
    upstream_data: Optional[Any] = Field(default=None, description="Upstream data")
    git_tags: List[str] = Field(description="List of git tags")
    errors: List[Dict[str, Optional[List[str]]]] = Field(description="List of errors")
    warnings: List[Dict[str, Optional[List[str]]]] = Field(
        description="List of warnings"
    )
    ignoreds: List[bool] = Field(description="List of ignored flags")


class EvergreenApiResponse(BaseModel):
    """Model for the full Evergreen API response"""

    rows: List[BuildVariant] = Field(description="List of build variants")
    versions: List[Version] = Field(description="List of versions")
    total_versions: int = Field(description="Total number of versions")
    current_skip: int = Field(description="Current skip value")
    previous_page_count: int = Field(description="Previous page count")
    current_time: int = Field(description="Current time in nanoseconds")


class VariantTask(BaseModel):
    """Model for a build variant task in Evergreen API"""

    name: str = Field(description="Name of build variant")
    tasks: List[str] = Field(
        description="All tasks available to run on this build variant"
    )


class PatchResponse(BaseModel):
    """Model for a patch from the Evergreen API"""

    patch_id: str = Field(description="Unique identifier of a specific patch")
    description: str = Field(description="Description of the patch")
    project_id: str = Field(description="Immutable ID for the project")
    branch_name: Optional[str] = Field(
        default=None, description="The branch on which the patch was initiated"
    )
    git_hash: str = Field(
        description="Hash of commit off which the patch was initiated"
    )
    author: str = Field(description="Author of the patch")
    status: str = Field(
        description="Status of patch (possible values are 'created', 'started', 'success', or 'failed')"
    )
    create_time: str = Field(description="Time patch was created")
    start_time: Optional[str] = Field(
        default=None, description="Time patch started to run"
    )
    finish_time: Optional[str] = Field(
        default=None, description="Time at patch completion"
    )
    activated: bool = Field(
        description="Whether the patch has been finalized and activated"
    )
    tasks: Optional[List[str]] = Field(
        default=None, description="List of identifiers of tasks used in this patch"
    )
    builds: Optional[List[str]] = Field(
        default=None, description="List of identifiers of builds to run for this patch"
    )
    patch_number: int = Field(description="Incrementing counter of user's patches")
    version: Optional[str] = Field(default=None, description="Associated version ID")
    variants_tasks: Optional[List[VariantTask]] = Field(
        default=None,
        description="List of documents of available tasks and associated build variant",
    )


class BuildDetail(BaseModel):
    """Model for build variant status details"""

    build_id: str = Field(description="ID of the build")
    build_variant: str = Field(description="Name of the build variant")


class GitTag(BaseModel):
    """Model for git tag information"""

    tag_name: str = Field(description="Name of the git tag")
    pusher: Optional[str] = Field(default=None, description="User who pushed the tag")
    push_time: Optional[str] = Field(
        default=None, description="Time the tag was pushed"
    )


class Parameter(BaseModel):
    """Model for version parameters"""

    key: str = Field(description="Parameter key")
    value: str = Field(description="Parameter value")


class VersionResponse(BaseModel):
    """Model for a specific version from the Evergreen API"""

    version_id: str = Field(description="Version ID")
    create_time: str = Field(description="Time that the version was first created")
    start_time: Optional[str] = Field(
        default=None,
        description="Time at which tasks associated with this version started running",
    )
    finish_time: Optional[str] = Field(
        default=None,
        description="Time at which tasks associated with this version finished running",
    )
    project: str = Field(description="Project identifier")
    revision: str = Field(description="The version control identifier")
    author: str = Field(description="Author of the version")
    author_email: Optional[str] = Field(
        default=None, description="Email of the author of the version"
    )
    message: str = Field(description="Message left with the commit")
    status: str = Field(
        description="The status of the version (possible values are 'created', 'started', 'success', or 'failed')"
    )
    activated: Optional[bool] = Field(
        default=None, description="Whether the version is activated"
    )
    repo: Optional[str] = Field(
        default=None, description="The github repository where the commit was made"
    )
    branch: Optional[str] = Field(
        default=None, description="The version control branch where the commit was made"
    )
    build_variants_status: Optional[List[BuildDetail]] = Field(
        default=None,
        description="List of documents of the associated build variant and the build id",
    )
    requester: Optional[str] = Field(
        default=None,
        description="Version created by one of 'patch_request', 'github_pull_request', etc.",
    )
    ignored: Optional[bool] = Field(
        default=None,
        description="Indicates if the version was ignored due to only making changes to ignored files",
    )
    parameters: Optional[List[Parameter]] = Field(
        default=None, description="Parameters for this version"
    )
    git_tags: Optional[List[GitTag]] = Field(
        default=None, description="Git tags that were pushed to this version"
    )
    errors: Optional[List[str]] = Field(
        default=None, description="Errors associated with this version"
    )
    aborted: Optional[bool] = Field(
        default=None, description="Whether the version was aborted"
    )
    order: Optional[int] = Field(default=None, description="Order of the version")


class LogLinks(BaseModel):
    """Model for log links"""

    all_log: Optional[str] = Field(
        default=None, description="URL to the complete task log"
    )
    task_log: Optional[str] = Field(default=None, description="URL to the task log")
    event_log: Optional[str] = Field(default=None, description="URL to the event log")
    system_log: Optional[str] = Field(default=None, description="URL to the system log")
    agent_log: Optional[str] = Field(default=None, description="URL to the agent log")


class EndDetails(BaseModel):
    """Model for task end details"""

    status: str = Field(description="Status of the task after completion")
    type: Optional[str] = Field(default=None, description="Type of task completion")
    description: Optional[str] = Field(
        default=None, description="Description of task completion"
    )
    timed_out: Optional[bool] = Field(
        default=None, description="Whether the task timed out"
    )
    oom_killed: Optional[bool] = Field(
        default=None, description="Whether the task was killed due to OOM"
    )


class Artifact(BaseModel):
    """Model for task artifacts"""

    name: str = Field(description="Name of the artifact")
    url: str = Field(description="URL to download the artifact")
    url_parsley: Optional[str] = Field(
        default=None, description="Parsley URL for the artifact"
    )
    visibility: str = Field(description="Visibility of the artifact (e.g., 'signed')")
    ignore_for_fetch: bool = Field(
        description="Whether to ignore this artifact for fetching"
    )
    content_type: str = Field(description="MIME type of the artifact")


class TaskExecution(BaseModel):
    """Model for a task execution"""

    execution: int = Field(description="Execution number")
    status: str = Field(description="Status of this execution")
    start_time: Optional[str] = Field(
        default=None, description="Start time of execution"
    )
    finish_time: Optional[str] = Field(
        default=None, description="Finish time of execution"
    )


class TaskResponse(BaseModel):
    """Model for task details from the Evergreen API"""

    task_id: str = Field(description="Unique identifier of the task")
    execution: Optional[int] = Field(
        default=0, description="Execution number of this task"
    )
    display_name: str = Field(description="Display name of the task")
    status: str = Field(description="Current status of the task")
    status_details: Optional[EndDetails] = Field(
        default=None, description="Details about the task status"
    )
    logs: Optional[LogLinks] = Field(
        default=None, description="Links to the various logs for this task"
    )
    activated: bool = Field(description="Whether the task is activated")
    activated_by: Optional[str] = Field(
        default=None, description="User who activated the task"
    )
    build_id: str = Field(description="ID of the build this task belongs to")
    build_variant: str = Field(description="Build variant this task runs on")
    version_id: str = Field(description="Version ID this task is a part of")
    project_id: Optional[str] = Field(
        default=None, description="Project ID this task belongs to"
    )
    project: Optional[str] = Field(
        default=None, description="Project this task belongs to"
    )
    revision: Optional[str] = Field(
        default=None, description="Git revision this task is testing"
    )
    priority: Optional[int] = Field(default=None, description="Priority of this task")
    create_time: Optional[str] = Field(
        default=None, description="Time when this task was created"
    )
    start_time: Optional[str] = Field(
        default=None, description="Time when this task started"
    )
    finish_time: Optional[str] = Field(
        default=None, description="Time when this task finished"
    )
    depends_on: Optional[List[Dict[str, str]]] = Field(
        default=None, description="Tasks this task depends on"
    )
    time_taken_ms: Optional[int] = Field(
        default=None, description="Time taken to complete in milliseconds"
    )
    expected_duration_ms: Optional[int] = Field(
        default=None, description="Expected duration in milliseconds"
    )
    previous_executions: Optional[List[TaskExecution]] = Field(
        default=None, description="Previous executions of this task"
    )
    artifacts: Optional[List[Artifact]] = Field(
        default=None, description="List of artifacts associated with this task"
    )
    host_id: Optional[str] = Field(
        default=None, description="ID of the host running this task"
    )
    distro_id: Optional[str] = Field(
        default=None, description="Distribution/OS identifier for this task"
    )


class PerformanceMetadata(BaseModel):
    """Model for performance metric metadata"""

    documentation_url: Optional[str] = Field(
        default=None, description="URL to documentation about this metric"
    )
    improvement_direction: Optional[str] = Field(
        default=None, description="Direction of improvement ('up' or 'down')"
    )
    measurement_unit: Optional[str] = Field(
        default=None,
        description="Unit of measurement (e.g., 'seconds', 'microseconds')",
    )
    noise_accepted_bf: Optional[str] = Field(
        default=None, description="Noise accepted BF value"
    )
    noise_accepted_bf_date: Optional[str] = Field(
        default=None, description="Noise accepted BF date"
    )
    noise_open_bf: Optional[str] = Field(
        default=None, description="Noise open BF value"
    )
    owner: Optional[str] = Field(default=None, description="Owner of this metric")
    source_location: Optional[str] = Field(
        default=None, description="Source location for this metric's definition"
    )
    tags: Optional[List[str]] = Field(
        default=None, description="Tags associated with this metric"
    )


class Stat(BaseModel):
    """Model for a performance statistic"""

    name: str = Field(description="Name of the statistic")
    val: Any = Field(description="Value of the statistic")
    metadata: PerformanceMetadata = Field(description="Metadata about this statistic")


class Rollups(BaseModel):
    """Model for performance rollups"""

    stats: List[Stat] = Field(description="List of rolled up statistics")


class OverrideInfo(BaseModel):
    """Model for override information in performance results"""

    override_mainline: bool = Field(
        description="Whether this overrides the mainline result"
    )
    base_order: Optional[int] = Field(
        default=None, description="Base order for comparison"
    )
    reason: Optional[str] = Field(default=None, description="Reason for the override")
    user: Optional[str] = Field(
        default=None, description="User who created the override"
    )


class PerformanceInfo(BaseModel):
    """Model for performance test information"""

    project: str = Field(description="Project ID")
    version: str = Field(description="Version string")
    variant: str = Field(description="Build variant name")
    order: int = Field(description="Order number")
    task_name: str = Field(description="Task name")
    task_id: str = Field(description="Task ID")
    execution: int = Field(description="Execution number")
    mainline: bool = Field(description="Whether this is a mainline task")
    override_info: OverrideInfo = Field(description="Override information")
    test_name: str = Field(description="Test name")
    args: Optional[Dict[str, Any]] = Field(default=None, description="Test arguments")


class PerformanceResult(BaseModel):
    """Model for a performance test result"""

    id: str = Field(description="Unique ID of the result")
    info: PerformanceInfo = Field(description="Information about this test")
    created_at: str = Field(description="Creation timestamp")
    completed_at: str = Field(description="Completion timestamp")
    rollups: Rollups = Field(description="Rolled up statistics")
    failed_rollup_attempts: int = Field(description="Number of failed rollup attempts")


# V1 API Models for legacy endpoints
class V1TaskInfo(BaseModel):
    """Model for task information in V1 API build response"""

    task_id: str = Field(description="Task ID")
    status: str = Field(description="Task status")
    time_taken: int = Field(description="Time taken for the task")


class V1VersionResponse(BaseModel):
    """Model for V1 API version response"""

    id: str = Field(description="Version ID")
    create_time: str = Field(description="Creation time")
    start_time: Optional[str] = Field(default=None, description="Start time")
    finish_time: Optional[str] = Field(default=None, description="Finish time")
    project: str = Field(description="Project identifier")
    revision: str = Field(description="Git revision")
    author: str = Field(description="Author")
    author_email: Optional[str] = Field(default=None, description="Author email")
    message: str = Field(description="Commit message")
    status: str = Field(description="Version status")
    activated: bool = Field(description="Whether version is activated")
    builds: List[str] = Field(description="List of build IDs")
    build_variants: List[str] = Field(description="List of build variant names")
    order: Optional[int] = Field(default=None, description="Version order")
    owner_name: Optional[str] = Field(default=None, description="Owner name")
    repo_name: Optional[str] = Field(default=None, description="Repository name")
    branch_name: Optional[str] = Field(default=None, description="Branch name")
    repo_kind: Optional[str] = Field(default=None, description="Repository kind")
    batch_time: Optional[int] = Field(default=None, description="Batch time")
    identifier: Optional[str] = Field(default=None, description="Project identifier")
    remote: Optional[bool] = Field(default=None, description="Whether remote")
    remote_path: Optional[str] = Field(default=None, description="Remote path")
    requester: Optional[str] = Field(default=None, description="Requester")


class V1BuildResponse(BaseModel):
    """Model for V1 API build response"""

    id: str = Field(description="Build ID")
    create_time: str = Field(description="Creation time")
    start_time: Optional[str] = Field(default=None, description="Start time")
    finish_time: Optional[str] = Field(default=None, description="Finish time")
    push_time: Optional[str] = Field(default=None, description="Push time")
    version: str = Field(description="Version ID")
    project: str = Field(description="Project identifier")
    revision: str = Field(description="Git revision")
    variant: str = Field(description="Build variant")
    number: Optional[str] = Field(default=None, description="Build number")
    status: str = Field(description="Build status")
    activated: bool = Field(description="Whether build is activated")
    activated_time: Optional[str] = Field(default=None, description="Activation time")
    order: Optional[int] = Field(default=None, description="Build order")
    tasks: Dict[str, V1TaskInfo] = Field(description="Dictionary of tasks")
    time_taken: Optional[int] = Field(default=None, description="Time taken")
    name: str = Field(description="Build variant display name")
    requested: Optional[str] = Field(default=None, description="Requester")


# Debugging Models
class LogEntry(BaseModel):
    """Model for a single log entry"""

    timestamp: Optional[str] = Field(
        default=None, description="Timestamp of the log entry"
    )
    level: Optional[str] = Field(
        default=None, description="Log level (e.g., INFO, ERROR, WARNING)"
    )
    message: str = Field(description="Log message content")
    line_number: Optional[int] = Field(
        default=None, description="Line number in the log file"
    )


class TaskLog(BaseModel):
    """Model for task log data"""

    task_id: str = Field(description="Task ID these logs belong to")
    log_type: str = Field(description="Type of log (task, system, agent, event)")
    entries: List[LogEntry] = Field(description="List of log entries")
    total_lines: int = Field(description="Total number of lines in the log")
    truncated: bool = Field(default=False, description="Whether the log was truncated")
    raw_url: Optional[str] = Field(default=None, description="URL to the raw log file")

    @field_validator("entries")
    @classmethod
    def validate_entries_size(cls, v: List[LogEntry]) -> List[LogEntry]:
        MAX_ENTRIES = 10000
        if len(v) > MAX_ENTRIES:
            raise ValueError(f"Too many log entries: {len(v)} > {MAX_ENTRIES}")
        return v


class CommandFailure(BaseModel):
    """Model for a failing command"""

    command: str = Field(description="The command that failed")
    exit_code: Optional[int] = Field(
        default=None, description="Exit code of the command"
    )
    error_output: Optional[str] = Field(
        default=None, description="Error output from the command"
    )
    start_time: Optional[str] = Field(
        default=None, description="When the command started"
    )
    end_time: Optional[str] = Field(default=None, description="When the command ended")
    duration_ms: Optional[int] = Field(
        default=None, description="Duration in milliseconds"
    )


class FailurePattern(BaseModel):
    """Model for a failure pattern"""

    pattern: str = Field(description="The failure pattern (regex or string)")
    count: int = Field(description="Number of occurrences")
    example_tasks: List[str] = Field(description="Example task IDs with this pattern")
    confidence: float = Field(
        description="Confidence score (0-1) for this pattern", ge=0, le=1
    )


class FailureAnalysis(BaseModel):
    """Model for comprehensive failure analysis"""

    task_id: str = Field(description="Task ID that was analyzed")
    status: str = Field(description="Task status")
    failure_type: Optional[str] = Field(
        default=None, description="Type of failure (e.g., test, compile, system)"
    )
    primary_error: Optional[str] = Field(
        default=None, description="Primary error message"
    )
    failing_commands: List[CommandFailure] = Field(
        default_factory=list, description="List of failing commands"
    )
    error_patterns: List[FailurePattern] = Field(
        default_factory=list, description="Common error patterns found"
    )
    suggested_causes: List[str] = Field(
        default_factory=list, description="Suggested root causes"
    )
    related_failures: List[str] = Field(
        default_factory=list, description="Related failing task IDs"
    )
    log_snippets: Dict[str, str] = Field(
        default_factory=dict, description="Relevant log snippets by log type"
    )


class PatchFailureSummary(BaseModel):
    """Model for patch failure summary"""

    patch_id: str = Field(description="Patch ID")
    total_tasks: int = Field(description="Total number of tasks")
    failed_tasks: int = Field(description="Number of failed tasks")
    failure_rate: float = Field(description="Failure rate percentage")
    failure_types: Dict[str, int] = Field(description="Count of failures by type")
    common_patterns: List[FailurePattern] = Field(
        description="Common failure patterns across tasks"
    )
    affected_variants: List[str] = Field(description="Build variants with failures")
    recommended_actions: List[str] = Field(
        description="Recommended actions to fix failures"
    )


# New models for enhanced log analysis capabilities
class LogMatch(BaseModel):
    """Model for a single log pattern match"""

    line_number: int = Field(description="Line number where the match was found")
    line_content: str = Field(description="The matching line content")
    context_before: List[str] = Field(
        default_factory=list, description="Lines before the match"
    )
    context_after: List[str] = Field(
        default_factory=list, description="Lines after the match"
    )
    match_type: str = Field(
        description="Type of match (ERROR, FAIL, Exception, custom)"
    )


class LogAnalysisResult(BaseModel):
    """Model for smart log analysis results"""

    task_id: str = Field(description="Task ID that was analyzed")
    log_type: str = Field(description="Type of log analyzed")
    total_lines: int = Field(description="Total lines in the log")
    matches: List[LogMatch] = Field(description="Pattern matches found")
    error_categories: Dict[str, int] = Field(description="Count of errors by category")
    summary_statistics: Dict[str, Any] = Field(
        description="Summary statistics about the log"
    )
    key_findings: List[str] = Field(description="Key findings from the analysis")

    @field_validator("matches")
    @classmethod
    def validate_matches_size(cls, v: List[LogMatch]) -> List[LogMatch]:
        MAX_MATCHES = 1000
        if len(v) > MAX_MATCHES:
            raise ValueError(f"Too many matches: {len(v)} > {MAX_MATCHES}")
        return v


class TestResult(BaseModel):
    """Model for a single test result"""

    name: str = Field(description="Test name")
    status: TestStatus = Field(description="Test status (passed, failed, skipped)")
    duration_ms: Optional[int] = Field(
        default=None, description="Test duration in milliseconds"
    )
    error_message: Optional[str] = Field(
        default=None, description="Error message if test failed"
    )
    stack_trace: Optional[str] = Field(
        default=None, description="Stack trace if available"
    )
    test_file: Optional[str] = Field(default=None, description="Test file path")


class TestSuite(BaseModel):
    """Model for a test suite result"""

    name: str = Field(description="Test suite name")
    tests: List[TestResult] = Field(description="Individual test results")
    total_tests: int = Field(description="Total number of tests")
    passed: int = Field(description="Number of passed tests")
    failed: int = Field(description="Number of failed tests")
    skipped: int = Field(description="Number of skipped tests")
    duration_ms: Optional[int] = Field(
        default=None, description="Total suite duration in milliseconds"
    )

    @model_validator(mode="after")
    def validate_test_counts(self) -> "TestSuite":
        calculated = self.passed + self.failed + self.skipped
        if self.total_tests != calculated:
            raise ValueError(
                f"Total tests ({self.total_tests}) != sum of passed+failed+skipped ({calculated})"
            )
        return self


class PaginatedLog(BaseModel):
    """Model for paginated log data"""

    task_id: str = Field(description="Task ID")
    log_type: str = Field(description="Type of log")
    page: int = Field(description="Current page number", ge=1)
    total_pages: int = Field(description="Total number of pages")
    lines_per_page: int = Field(description="Number of lines per page")
    total_lines: int = Field(description="Total lines in the log")
    content: List[str] = Field(description="Log content for this page")
    has_next: bool = Field(description="Whether there's a next page")
    has_previous: bool = Field(description="Whether there's a previous page")


class FailureComparison(BaseModel):
    """Model for cross-task failure comparison"""

    base_task_id: str = Field(description="Base task ID for comparison")
    compared_tasks: List[str] = Field(description="List of task IDs compared")
    common_patterns: List[FailurePattern] = Field(
        description="Patterns found across multiple tasks"
    )
    unique_to_base: List[str] = Field(description="Failures unique to the base task")
    confidence_score: float = Field(
        description="Overall confidence in the comparison (0-1)", ge=0, le=1
    )
    suggested_root_cause: Optional[str] = Field(
        default=None, description="Suggested root cause based on patterns"
    )
    related_issues: List[str] = Field(
        default_factory=list, description="Related known issues or tickets"
    )