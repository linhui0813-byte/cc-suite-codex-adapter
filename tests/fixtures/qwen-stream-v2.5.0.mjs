// Reviewed upstream 2.5.0 stream consumer at a0e97ad076b66a114bd6eb12f1a6486a38ff51dc.
export function consumeQwenEvent(state, event) {
  if (state.resultSeen) {
    if (event.type === "result") {
      throw new QwenStreamError("duplicate_result", "Qwen emitted more than one terminal result event");
    }
    throw new QwenStreamError(
      "event_after_result",
      `Qwen emitted ${event.type ?? "an unknown event"} after its terminal result`
    );
  }
  rememberSession(state, event);
  state.events += 1;

  switch (event.type) {
    case "system":
      if (event.subtype === "init") {
        validateInit(state, event);
      }
      return;
    case "assistant":
      if (!state.initSeen) {
        throw new QwenStreamError("assistant_before_init", "Qwen emitted assistant output before init");
      }
      inspectAssistant(state, event);
      return;
    case "user":
    case "tool_result":
      if (!state.initSeen) {
        throw new QwenStreamError("tool_result_before_init", "Qwen emitted tool output before init");
      }
      consumeToolResults(state, event);
      return;
    case "result":
      inspectResult(state, event);
      return;
    case "stream_event": {
      // qwen-code 0.24.x wraps internal state notices in a stream_event
      // envelope: {"type":"stream_event","event":{"type":"goal_state",...}}.
      // Only the known-inert goal_state subtype is accepted. Every other
      // subtype -- including a missing or non-object inner event -- still
      // throws, so an envelope carrying tool activity fails closed rather than
      // being silently ignored. Widen this list only for a subtype proven
      // incapable of carrying a tool call; the whole point of the observer is
      // that an event it does not understand stops the run.
      const inner = event.event;
      const innerType = inner && typeof inner === "object" ? inner.type : null;
      if (innerType === "goal_state") return;
      throw new QwenStreamError(
        "unknown_event",
        `Qwen emitted unsupported stream_event subtype: ${innerType ?? "(missing)"}`
      );
    }
    default:
      throw new QwenStreamError(
        "unknown_event",
        `Qwen emitted unsupported stream-json event type: ${event.type ?? "(missing)"}`
      );
  }
}

export function describeQwenEvent(event) {
  if (event.type === "system") return `event system/${event.subtype ?? "unknown"}`;
}
