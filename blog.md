
> **TL;DR:** When using OpenAI voice-to-voice Realtime models, the API streams audio, transcripts, tool calls, and other events over a single WebSocket, which makes tracking connected events rather difficult. To contextualize each event and allow you to debug and monitor the agents effectively, you can build a listener that hooks into the OpenAI Agents SDK (or any other SDK for that matter) to track each event, contextualize it, and emit OpenTelemetry spans, metrics and logs.

If you're building a voice agent with the [OpenAI Realtime API](https://platform.openai.com/docs/guides/realtime) and the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/), you've probably noticed something: once the WebSocket starts streaming, events arrive left and right, but your standard observability setup stops working… thanks to the fabulous concept of asynchronous events. 😶‍🌫️

Audio chunks, transcripts, function calls, and errors all fly through a single connection as single events rather than indications of state changes, so tracking during which turn of a conversation a tool call failed, or what the actual tool call inputs and execution logs were is really cumbersome out of the box. 😬

So to make sense of it all, we need to track and contextualize each incoming event to build a proper trace.

Luckily the OpenAI Agents SDK lets you register listeners that receive every
incoming event, which is exactly the hook we need.

> **📝 Note:** Even if you are not using the OpenAI Agents SDK, the concept of a similar listener can be applied to other SDKs by manually forwarding events to the listener if need be.

Now let's try to understand where we want to be, before we build our solution!

## What exactly are we trying to visualize?

Consider a voice agent with a single `get_weather` tool. When a user asks
"What's the weather in London?", the agent receives audio, transcribes it,
calls the tool, and responds. The trace we want looks like this:

![Trace expectations](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/y0znli1v8anrkmrr2jli.png)

> **📝 Note:** The full OpenAI agents definition can be found here [`agent.py`](https://github.com/MahrRah/observability-realtime-agent/blob/main/src/app/agent.py)

A session span wraps the entire conversation. Each turn (user input, agent
response) is a child span, and tool calls nest under the agent's response.
All execution logs land in the correct span rather than floating in space.

So why does regular instrumentation fail here?
There are two challenges.

First, because the spans are usually started and stopped in a synchronous manner.
You will quickly notice the issue when trying to build just a simple span for a user's input. The span starts when receiving an `input_audio_buffer.speech_started` event and ends when you get an `input_audio_buffer.speech_stopped` event. You will realize that you need to store the span somewhere so you can close it later when the stop event arrives.

Second, keeping track of all logs that happen in the context of a span.

Lucky for you, there is a nice way to handle both of those issues. Let's see how we can build this. 🤓

## What are we using?

Before we dig into code, let's make sure we are all on the same page of what we are using for this sample. For instrumentation we will rely on the OpenTelemetry ecosystem and Azure Application Insights as the backend, given how easy it is nowadays to integrate with Azure Application Insights. For that, we are following the instructions here: [Enable Azure Monitor OpenTelemetry for .NET, Node.js, Python, and Java applications](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python#modify-your-application).

The [`azure-monitor-opentelemetry`](https://pypi.org/project/azure-monitor-opentelemetry/) has everything pre-bundled (making our lives so much easier). Hence all you need is to install the [`azure-monitor-opentelemetry`](https://pypi.org/project/azure-monitor-opentelemetry/) package, make sure we set `APPLICATIONINSIGHTS_CONNECTION_STRING=<Your connection string>` as an environment variable and add the following line in our app startup:

```python
from azure.monitor.opentelemetry import configure_azure_monitor

configure_azure_monitor()
```

> **📝 Note:** You can always use your own observability backend! That's the beauty of OpenTelemetry 🥰
> To do so you just need to configure the OpenTelemetry SDK to export telemetry to your chosen backend instead of using the auto configuration from `configure_azure_monitor`.

Now that we have the basics set, let's dive into the really interesting part!

## Building a Listener for OpenTelemetry

As already mentioned, to give us full visibility into the system with the correct trace, we need the ability to intercept each message and take respective actions. In the case of OpenAI Agents SDK, it allows us to do this by registering listeners on a session that will receive all the events from the websocket just by inheriting from the [`RealtimeModelListener`](https://openai.github.io/openai-agents-python/ref/realtime/model/#agents.realtime.model.RealtimeModelListener) class. That ticks one part of what we need for this to work and leaves us with two main other parts that we need to handle within the listener, which are:

1. 📖 The Context management part; where we keep track of the current session's span context.
2. 🔀 The Event tracking part; where we listen to incoming events, check what type of event it is, and handle them accordingly.

Pretty simple so far, right? Let's start looking at the context management first in the next section.

### 1. Context management

The heart and soul of the listener will be the store in which we keep track of the span context of the conversation, ensure the correct span is attached as the active span and ensure once we exit a span it also gets detached again.

Reading this you might wonder 'Why do I all of a sudden have to manually attach and detach my span context?'. It's a fair question. If you have worked mostly with a typical synchronous flow, you'd just wrap everything in a `with` block and OpenTelemetry handles context for you. Let's have a look at the scenario of a tool call:

```python
# This is how it would work in a simple synchronous flow:
async def _handle_function_call(self, event):
    with tracer.start_as_current_span("tool_call"):
        result = get_weather("London")          # ← logs land in the "tool_call" span
        logger.info("Got result: %s", result)   # ← this too
    # span ends here, all good
```

But with the Realtime API, the event that *starts* the process and the code that *executes* it arrive in separate async tasks. There's no single code block that wraps both:

```python
# Event 1: function call arguments arrive → we want to open a span
async def _handle_function_call(self, event):
    with tracer.start_as_current_span("tool_call"):
        pass  # we can't do the actual work here, the SDK calls the tool separately
    # ← span is already closed and detached!

# Event 2: the SDK calls our tool in a different task
def get_weather(city: str) -> str:
    logger.info("Fetching weather for %s", city)  # ← this log is now orphaned,
    return f"12°C in {city}" 
```

Why is this happening? The `with` block calls `attach` on entry and `detach` on exit, so by the time the tool actually runs, the span is no longer the current context. Even if you think you can cheat the system and not use the `with` block and just create the span using `tracer.start_as_current_span(name)`, under the hood there is still the same `with` block that will `detach` on exit (see [source](https://github.com/open-telemetry/opentelemetry-python/blob/7c860ca40eb87c15fb608ce3598cfec4a5da2d1c/opentelemetry-api/src/opentelemetry/trace/__init__.py#L596)).

The solution: manually `attach` the span's context when we open it, keep it alive across tasks, and `detach` + `end` it only when we receive the closing event. That's exactly what `TelemetryContext` does:

```python
class TelemetryContext:

    def __init__(self, session_id: str | None = None, root_span: Span | None = None) -> None:
        self.session_id: str | None = session_id
        self.root_span: Span | None = root_span
        self._anchors: dict[str, tuple[Span, Token[Context] | None]] = {}


    def start_anchor_span(self, key: str, span: Span, context: Context | None = None) -> Span:
        new_context = set_span_in_context(span, context=context)
        token: Token[Context] | None = None
        if context is None:
            token = attach(new_context)
        else:
            try:
                attach(new_context)
            except Exception:
                pass
        self._anchors[key] = (span, token)
        return span


    def end_anchor_span(self, key: str | None) -> None:
        if not key:
            return
        anchor = self._anchors.pop(key, None)
        if anchor:
            span, token = anchor
            if token is not None:
                try:
                    detach(token)
                except Exception:
                    logger.debug("Unable to detach span for %s", key)
            try:
                if span.is_recording():
                    span.end()
            except Exception:
                logger.debug("Unable to end span for %s", key)

```

> **⚠️ Important:** The full class can be found here [`TelemetryContext`](https://github.com/MahrRah/observability-realtime-agent/blob/main/src/app/listener/telemetry_context.py) which also includes a clean up function and a way to retrieve the current context.

And that was it. A simple Context class that manages your span contexts and makes sure the right span is active.
Next, let's have a look at how we use this to build up our trace with help of the listener in the following section.

### 2. Building the Trace

We have a way to store our spans and ensure the right one is active. Using this, all we need to do is listen to the incoming events and handle them properly.

Once we create our `TelemetryListener` and base it off [`RealtimeModelListener`](https://openai.github.io/openai-agents-python/ref/realtime/model/#agents.realtime.model.RealtimeModelListener) we will receive each event in the `on_event()` method, from which we can then dispatch the event to the right handler.

This would look something like this:

```python
class RealtimeTelemetryListener(RealtimeModelListener):
    """OpenTelemetry event listener for OpenAI Realtime API sessions."""

    def __init__(
        self,
        session_id: str,
        *,
        track_delta_events: bool = False,
    ) -> None:
        self.session_id = session_id
        self.track_delta_events = track_delta_events

        self._otel = TelemetryContext(session_id=session_id, root_span=get_current_span())
        
    async def on_event(self, event: RealtimeModelEvent) -> None:
            if event.type != "raw_server_event":
                return

            parsed = get_server_event_type_adapter().validate_python(event.data)

            match parsed.type:
                case RealtimeEventType.SESSION_CREATED:
                    self._handle_session_created(parsed)
                case RealtimeEventType.SESSION_UPDATED:
                    self._handle_session_updated(parsed)
                case RealtimeEventType.SPEECH_STARTED:
                    self._handle_speech_started(parsed)
                case RealtimeEventType.SPEECH_STOPPED:
                    self._handle_speech_stopped(parsed)
                case RealtimeEventType.FUNCTION_CALL:
                    self._handle_function_call_arguments_done(parsed)
                case RealtimeEventType.CONVERSATION_ITEM_ADDED:
                    self._handle_conversation_item_added(parsed)
                # ... other event types (audio deltas, transcripts, errors, etc.)
                case RealtimeEventType.RATE_LIMITS_UPDATED:
                    self._handle_rate_limits_updated(parsed)
                case _:
                    logger.debug("Unhandled raw server event: %s", parsed.type)
```

> **⚠️ Important:** The full class can be found once again in the same sample repo and here [`RealtimeTelemetryListener`](https://github.com/MahrRah/observability-realtime-agent/blob/3026728506654755df02972d249673d3219b1050/src/app/listener/telemetry_listener.py#L83)

> **📝 Note:** Why are we using the `raw_server_event`? Because these are the first events directly from the API, hence we can ensure that the logs and other follow-up telemetry do not get lost.

Let's have a look at how we handle span creations now.

On start of a user talking we would get a `RealtimeEventType.SPEECH_STARTED` which is basically an enum for the Realtime API event type [`input_audio_buffer.speech_started`](https://developers.openai.com/api/reference/resources/realtime/server-events#input_audio_buffer.speech_started).

The match case would dispatch it to our `_handle_speech_started` which looks like this:

```python
def _handle_speech_started(self, event: InputAudioBufferSpeechStartedEvent) -> None:
    ctx = self._otel.get_span_context(key="session")
    span = tracer.start_span(SpanName.USER_INPUT, context=ctx, kind=SpanKind.INTERNAL)
    response_id = event.response.id or UNKNOWN_ID
    self._otel.start_anchor_span(response_id, span, context=ctx)
```

Basically, it will grab the session context as a parent and pass it as the parent context when creating the user input span. Once the span is created we register it as an anchor span. If you remember `start_anchor_span()` will not only store the span to be closed at a later time but also `attach` it.

Now once the user stops speaking we will receive a [`input_audio_buffer.speech_stopped`](https://developers.openai.com/api/reference/resources/realtime/server-events#input_audio_buffer.speech_stopped) event, which is `RealtimeEventType.SPEECH_STOPPED` in our enum.
This will dispatch to the `_handle_speech_stopped()` handler, which will `detach` and close the span.

```python
def _handle_speech_stopped(self, event: InputAudioBufferSpeechStoppedEvent) -> None:
    self._otel.end_anchor_span(event.item_id)
```

Just like for the user input spans, the same applies for the tool calls. Instead of having the parent span context be the session span, we would just use the context of the agent's response as the parent span context and listen to two different event types: `RealtimeEventType.FUNCTION_CALL` for the start (corresponding to [`response.function_call_arguments.done`](https://developers.openai.com/api/reference/resources/realtime/server-events#response.function_call_arguments.done)) and `RealtimeEventType.CONVERSATION_ITEM_ADDED` (corresponding to [`conversation.item.added`](https://developers.openai.com/api/reference/resources/realtime/server-events#conversation.item.added)) to close the span.

See the full sample here: [observability-realtime-agent](https://github.com/MahrRah/observability-realtime-agent)

### Other Telemetry

So far we've covered spans and logs, which were the most difficult parts we had to tackle. One thing we missed entirely were metrics.
Given these are generally a measurement at a given time, or a given state, etc., there is no need to track them as part of a larger context, making metric tracking comparatively trivial.

Let's look at a metric example of a counter. To know how often the Agent uses its tool, it is useful to emit a count metric that tracks how many function calls are being made.

For that, we first define the counter at module level:

```python
_function_call_counter = meter.create_counter(MetricName.FUNCTION_CALL)
```

Then increment it inside the tool call handler mentioned earlier which gets called at the start of the tool call and also creates the span:

```python
def _handle_function_call_arguments_done(self, event: ResponseFunctionCallArgumentsDoneEvent) -> None:
    ctx = self._otel.get_span_context(key=event.response_id)
    span = tracer.start_span(SpanName.FUNCTION_CALL, context=ctx, kind=SpanKind.INTERNAL)
    call_id = event.call_id or UNKNOWN_ID
    self._otel.start_anchor_span(call_id, span, context=ctx)

    _function_call_counter.add(1, {"session_id": self._otel.session_id, "function_name": function_name}) #  ← increment counter by 1 
```

Simple as that! With that, we have covered all telemetry areas. Next up: wiring it all together and running the application.

## Wire it up

Now that the listener is handling all of our telemetry creation, we just need to register it and run the agent to hopefully see a beautiful trace in our observability backend.
When you create the agent session, you can create the listener and register it, as shown in the example below:

```python
session = await runner.run(model_config=model_config)
async with session:
    listener = RealtimeTelemetryListener(session_id)
    session.model.add_listener(listener)

    try:
        # ... handle WebSocket messages as usual ...
    finally:
        listener.cleanup()
```

Finally we are ready! Let's run this and have a look at how your trace looks in Azure Application Insights.

![Conversation trace](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/jzr4f2vedtfp47diljws.png)

And! Our tools execution logs are connected to the right parent

![Log entry with correct parent](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/kwmyyq8l6ahdehdwvpkm.png)

Also we have one tool call in our metric

![Function call metric](https://dev-to-uploads.s3.amazonaws.com/uploads/articles/nz8l2vp7brhoj7uean50.png)

> Don't trust me? Too lazy to write the code yourself or wanna play around with it yourself?

> No worries, I got you 😉!
> Try it out with the full voice agent sample I have here: [observability-realtime-agent](https://github.com/MahrRah/observability-realtime-agent). The [`README.md`](https://github.com/MahrRah/observability-realtime-agent/main/README.md) will walk you through how to get this going, deploy your resources on Azure and get your application running so it uses Azure Application Insights as an observability backend.

## Conclusion

As you can see, with some simple tweaks you can make sure your agent's conversation is tracked properly and rest assured you will be able to find where things went wrong. If this is all still too much code for you, check out the OpenTelemetry auto-instrumentation for OpenAI's Agents SDK!

And with that we have a pretty solid way to observe and contextualize events from a Realtime WebSocket in our observability dashboard! Happy observing 🔭!
