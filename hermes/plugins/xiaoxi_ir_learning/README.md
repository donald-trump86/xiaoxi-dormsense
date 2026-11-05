# Restricted IR learning plugin

This native Hermes directory plugin guides one physical remote key at a time through the fixed learning service described in [the service README](../../../services/ir_learning/README.md). The dedicated service, plugin and active-profile configuration are installed in the current eight-role deployment. Fresh native registration and an actual Chinese model status query passed; browser interaction and physical key capture remain pending.

The 2026-11-05 C3 build and single USB upload succeeded. The first readiness check ran before reconnection and failed with `receiver_not_ready`; a later independent TLS query confirmed online `learn1` status. The three native tools were registered through Hermes' deferred tool discovery, and `deepseek-chat` described and called `xiaoxi_ac_learning_status`, receiving `idle`. These checks establish learning-service integration, not a completed remote profile or an air-conditioner response.

## Tools and conversation

| Tool | Arguments | Service action |
| --- | --- | --- |
| `xiaoxi_ac_initialize` | `action`: `start` (default), `status`, `cancel` | Same action |
| `xiaoxi_ac_learn_key` | `button`, `action`: `capture` (default) | `next` |
| `xiaoxi_ac_learn_key` | `button`, `action: confirm`, `confirm: true`, nonempty `label` | `confirm` |
| `xiaoxi_ac_learn_key` | `button`, `action: skip`, optional `reason` | `skip` |
| `xiaoxi_ac_learning_status` | None | `status` |

Starting a fresh profile requests the baseline capture; an existing profile returns its current state. Ask the user to describe the remote's initial display and wait for `ready` before asking them to point the remote at the C3 receiver, away from the air conditioner, and press the named physical key once. Query status until capture completes, then compare the remote's before/after display with only the supported decoded fields. Avoid rapid status polling. `receiver_not_ready` means the capture window is not ready. After a restart, incomplete/expired capture or skip during reception, request `baseline` again before another key.

The service starts passively: it restores state and subscribes to MQTT without arming capture or emitting IR. Its HTTP health check does not establish node readiness. The service accepts 17 key identifiers and recommends 11 common keys; see the [key list and recommendations](../../../services/ir_learning/README.md#可录键与推荐顺序).

For `UNKNOWN`, keep the interpretation pending and ask the user for a manual label. Use `confirm: true` only after the user agrees to that interpretation. This boolean records the conversation's interpretation; it is not independent evidence of a human approval event. Confirmation stores a label and never emits IR. Skip absent keys explicitly. Missing or unsupported fields stay unknown; never substitute `false`. Learning a received signal does not prove that the air conditioner responded.

The service owns one active profile/session, raw captures, private `0700` storage, `0600` files and deterministic validation. The current full-state sample requirement is 280 timing entries, with a hard retention cap of 300. A partial 64-bit `GREE` decode covers only the first section; the full waveform is retained with an explicit warning rather than treating that section as complete semantic validation. `UNKNOWN` still requires a manual label, and a structurally valid sample does not prove protocol completeness.

The tools accept no device, MQTT topic, host, URL, path or raw IR argument. They expose no replay action. Full raw timings remain in the service and are omitted from tool results. The separate [trusted local operator command](../../../services/ir_learning/README.md#可信本地操作者的单次重放) requires an explicit one-attempt confirmation and the same owner identity as its private mounted config/state; it must not be made available through a model tool, HTTP action or generic terminal.

## Native mechanism and configuration

The native loading mechanism was checked against the pinned Hermes source/image (`39c4ac5a8eae…`): it discovers a directory under `get_hermes_home() / "plugins"`, reads [plugin.yaml](plugin.yaml), loads [__init__.py](__init__.py), and calls `register(ctx)`. This plugin uses `ctx.register_tool(name, toolset, schema, handler, check_fn, …)` and the registered `xiaoxi_ir_learning` toolset. Its manifest is JSON, a supported YAML subset, with manifest version 1 and `kind: standalone`. No upstream registry edit, new SDK or Python dependency is needed.

The following describes the required wiring for reproducing or reviewing the installed configuration. Any future deployment or reload is a separate operator action; installation alone does not verify the fresh runtime tool catalog:

1. Mount this directory read-only at the active container profile's `get_hermes_home()/plugins/xiaoxi_ir_learning`. Determine the configured container home before choosing the mount destination; the repository deployment template alone does not verify the running value. A project-local plugin directory is unnecessary.
2. Merge this entry into the active profile's existing configuration, retaining any other deliberately enabled plugins. Keep the existing Home Assistant toolset:

   ```yaml
   plugins:
     enabled:
       - xiaoxi_ir_learning
   platform_toolsets:
     cli:
       - homeassistant
       - xiaoxi_ir_learning
   ```

   Keep this plugin/toolset out of any explicit deny list. The directory plugin must be enabled before its toolset can be resolved. `cli` is the configured platform in the handoff; the dashboard's effective platform and fresh tool selection still require acceptance. Verify the resulting tool names, including any deferred `tool_search` representation, before claiming they are available. Do not add `code_execution`, terminal, a broad composite toolset, or a generic MCP server.
3. Provision the dedicated `XIAOXI_IR_LEARNING_TOKEN` through the active Hermes profile's official secret source. Each availability check and request uses `agent.secret_scope.get_secret(name)`; the plugin never opens credential files, reads process environment directly, or falls back to an alternate token. Missing/unscoped credentials fail closed. The service must validate the same dedicated bearer credential. Never reuse the HA backend token or expose this credential in tool arguments/results.
4. The dedicated service connects to the existing backend and agent networks; Hermes remains on the agent network. The only plugin request target is `http://ir-learning:8090/api/learning`. Keep the Home Assistant read gateway and its credentials/allowlist unchanged. Hermes receives neither backend network access nor the service's MQTT credential. `http.client` ignores proxy environment variables, so this plugin needs no inference-proxy or `NO_PROXY` expansion. The [optional service compose](../../../deploy/compose.ir-learning.yaml) runs as UID 10001, uses a preinitialized external private state volume and publishes no host port; see the [service deployment instructions](../../../services/ir_learning/README.md#可选-compose-部署).
5. After a configuration change or reload, verify plugin discovery and fresh tool selection without requesting capture or replay. The current native/model status checks passed as recorded above; browser key recording remains a separate acceptance step.

## HTTP and returned data

Each call with valid input and an available profile credential makes one `POST /api/learning` with `Authorization: Bearer <dedicated token>` and JSON containing only `action` and relevant `button`, `label`, `confirm`, `reason` fields. The client uses a 5-second socket timeout, no retry, no redirect handling, no proxy support, and a 128 KiB response cap. Non-JSON/encoded/oversized responses and HTTP errors return fixed codes without backend bodies or exception text. A socket timeout bounds an individual blocking operation; it is not a strict total deadline against a peer that continually trickles data.

Results project only `ok`, the recognized `status`, hex32 `profile_id`, `button`, `prompt`, `message`, `record_count`, `recommended_buttons`, `observed`, `changes`, `validation` and sanitized error codes. Text/list sizes are bounded, unknown nested keys are dropped, and the current credential is redacted from allowed text fields. `observed` accepts only `power`, `mode`, `temp_c`, `fan`, `swingv`, `swingh`, `light`, `turbo`, `econo`, `clean`, `sleep`, `ifeel`, `quiet`, `filter`, plus `protocol`, `bits`, `rawlen`, `coverage`. `changes` accepts the same state fields with scalar `before`/`after`; `validation` accepts `basis` and string `warnings`. Scalars preserve null, false and zero. Service errors return only a sanitized code.

## Offline verification

From the repository root, in its existing virtual environment:

```bash
.venv/bin/python -B -m unittest discover -s hermes/tests -p 'test_ir_learning_plugin.py' -v
```

The test uses a stub `PluginContext`, a stub official secret API, a fake HTTP connection and a socket guard. It checks tool registration, all six allowed service actions, fixed addressing, per-call profile-secret lookup, rejection of extra/invalid inputs, response bounds, nested projection, null/false preservation and error/token redaction. It does not import the full upstream Hermes runtime or prove live discovery, chat adherence, transport reachability, physical capture, persistent storage or AC behavior.
