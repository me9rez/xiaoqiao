export interface GatewayRequest {
  id?: string
  method: string
  params: Record<string, unknown>
}

export interface GatewayEvent {
  type: string
  sessionId?: string
}

export interface TextDeltaEvent extends GatewayEvent {
  type: 'text_delta'
  delta: string
}

export interface ThinkingDeltaEvent extends GatewayEvent {
  type: 'thinking_delta'
  delta: string
}

export interface ToolCallStartEvent extends GatewayEvent {
  type: 'tool_call_start'
  callId: string
  name: string
  arguments: string
}

export interface ToolExecutionStartEvent extends GatewayEvent {
  type: 'tool_execution_start'
  callId: string
  name: string
}

export interface ToolExecutionDeltaEvent extends GatewayEvent {
  type: 'tool_execution_delta'
  callId: string
  line: string
}

export interface ToolExecutionEndEvent extends GatewayEvent {
  type: 'tool_execution_end'
  callId: string
  name: string
  ok: boolean
  exitCode: number
  error?: string
  result?: string
}

export interface TurnEndEvent extends GatewayEvent {
  type: 'turn_end'
  reason: 'complete' | 'tool_calls'
}

export interface DoneEvent extends GatewayEvent {
  type: 'done'
}

export interface ErrorEvent extends GatewayEvent {
  type: 'error'
  message: string
  recoverable: boolean
}

export interface ToolApprovalRequestEvent extends GatewayEvent {
  type: 'tool_approval_request'
  callId: string
  name: string
  arguments: string
}

export interface ToolApprovalResponseEvent extends GatewayEvent {
  type: 'tool_approval_response'
  callId: string
  approved: boolean
}

export interface GroupMessagePayload {
  id: string
  groupId: string
  seq: number
  authorType: 'user' | 'bot' | 'system'
  authorId: string
  text: string
  mentions: string[]
  replyTo: string | null
  runId: string | null
  createdAt: string
}

export interface GroupMessageCreatedEvent extends GatewayEvent {
  type: 'group_message_created'
  groupId: string
  message: GroupMessagePayload
}

export interface ApprovalRequestedEvent extends GatewayEvent {
  type: 'approval_requested'
  approvalId: string
  callId: string
  botId: string
  groupId: string | null
  runId: string
  tool: string
  arguments: string
  expiresAt: string
}

export interface ApprovalResolvedEvent extends GatewayEvent {
  type: 'approval_resolved'
  approvalId: string
  callId: string
  botId: string
  groupId: string | null
  status: 'approved' | 'denied' | 'expired'
}

export interface RoutineFiredEvent extends GatewayEvent {
  type: 'routine_fired'
  routineId: string
  botId: string
  groupId: string | null
  scheduledAt: string
}

export interface WorkspaceInfo {
  name: string
  path: string
}

export interface ReadyEvent extends GatewayEvent {
  type: 'ready'
  workspace?: WorkspaceInfo
}

export interface RpcError {
  message: string
}

export interface RpcResponseEvent extends GatewayEvent {
  type: 'rpc_response'
  id: string
  result?: unknown
  error?: RpcError
}

export type AgentEvent =
  | TextDeltaEvent
  | ThinkingDeltaEvent
  | ToolCallStartEvent
  | ToolExecutionStartEvent
  | ToolExecutionDeltaEvent
  | ToolExecutionEndEvent
  | TurnEndEvent
  | DoneEvent
  | ErrorEvent
  | ToolApprovalRequestEvent
  | ToolApprovalResponseEvent
  | ReadyEvent
  | RpcResponseEvent
  | GroupMessageCreatedEvent
  | ApprovalRequestedEvent
  | ApprovalResolvedEvent
  | RoutineFiredEvent

export function isTextDeltaEvent(event: GatewayEvent): event is TextDeltaEvent {
  return event.type === 'text_delta'
}

export function isThinkingDeltaEvent(event: GatewayEvent): event is ThinkingDeltaEvent {
  return event.type === 'thinking_delta'
}

export function isToolCallStartEvent(event: GatewayEvent): event is ToolCallStartEvent {
  return event.type === 'tool_call_start'
}

export function isToolExecutionStartEvent(event: GatewayEvent): event is ToolExecutionStartEvent {
  return event.type === 'tool_execution_start'
}

export function isToolExecutionDeltaEvent(event: GatewayEvent): event is ToolExecutionDeltaEvent {
  return event.type === 'tool_execution_delta'
}

export function isToolExecutionEndEvent(event: GatewayEvent): event is ToolExecutionEndEvent {
  return event.type === 'tool_execution_end'
}

export function isTurnEndEvent(event: GatewayEvent): event is TurnEndEvent {
  return event.type === 'turn_end'
}

export function isDoneEvent(event: GatewayEvent): event is DoneEvent {
  return event.type === 'done'
}

export function isErrorEvent(event: GatewayEvent): event is ErrorEvent {
  return event.type === 'error'
}

export function isReadyEvent(event: GatewayEvent): event is ReadyEvent {
  return event.type === 'ready'
}

export function isRpcResponseEvent(event: GatewayEvent): event is RpcResponseEvent {
  return event.type === 'rpc_response'
}

export function isGroupMessageCreatedEvent(event: GatewayEvent): event is GroupMessageCreatedEvent {
  return event.type === 'group_message_created'
}

export function isApprovalRequestedEvent(event: GatewayEvent): event is ApprovalRequestedEvent {
  return event.type === 'approval_requested'
}

export function isApprovalResolvedEvent(event: GatewayEvent): event is ApprovalResolvedEvent {
  return event.type === 'approval_resolved'
}

export function isRoutineFiredEvent(event: GatewayEvent): event is RoutineFiredEvent {
  return event.type === 'routine_fired'
}

export function isToolApprovalRequestEvent(event: GatewayEvent): event is ToolApprovalRequestEvent {
  return event.type === 'tool_approval_request'
}

export function isToolApprovalResponseEvent(event: GatewayEvent): event is ToolApprovalResponseEvent {
  return event.type === 'tool_approval_response'
}
