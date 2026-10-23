// Friendly aliases for the generated OpenAPI schema types.
import type { components } from "./schema";

type Schemas = components["schemas"];

export type Circuit = Schemas["Circuit"];
export type Component = Schemas["Component"];
export type ComponentKind = Schemas["ComponentKind"];
export type Analysis = NonNullable<Circuit["analyses"]>[number];
export type Issue = Schemas["Issue"];
export type Severity = Schemas["Severity"];

export type HealthOut = Schemas["HealthOut"];
export type ComponentSpecOut = Schemas["ComponentSpecOut"];

export type EndpointIn = Schemas["EndpointIn"];
export type EndpointOut = Schemas["EndpointOut"];
export type EndpointTestResult = Schemas["EndpointTestResult"];
export type ProviderKind = Schemas["ProviderKind"];
export type OutputMode = Schemas["OutputMode"];

export type ProjectRecord = Schemas["ProjectRecord"];
export type ProjectDetail = Schemas["ProjectDetail"];
export type VersionOut = Schemas["VersionOut"];
export type VersionSummary = Schemas["VersionSummary"];
export type MessageRecord = Schemas["MessageRecord"];
export type MessageMeta = Schemas["MessageMeta"];

export type SimulationResult = Schemas["SimulationResult"];
export type AnalysisResult = SimulationResult["analyses"] extends (infer T)[] | undefined ? T : never;
export type OperatingPointResult = Schemas["OperatingPointResult"];
export type SweepResult = Schemas["SweepResult"];
export type Trace = Schemas["Trace"];
export type Axis = Schemas["Axis"];

export type StreamEvent = Schemas["StreamEvent"];
export type StreamEventType = StreamEvent["type"];
export type AttemptStarted = Schemas["AttemptStarted"];
export type ValidationFailed = Schemas["ValidationFailed"];
export type EndpointFailed = Schemas["EndpointFailed"];
export type DesignCompleted = Schemas["DesignCompleted"];
export type DesignFailed = Schemas["DesignFailed"];
export type TurnSaved = Schemas["TurnSaved"];

export type HTTPValidationError = Schemas["HTTPValidationError"];
