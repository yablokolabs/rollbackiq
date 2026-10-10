# Issue draft: `duo run --flow-config` is silently ignored in headless mode

**Where to file:** https://gitlab.com/gitlab-org/editor-extensions/gitlab-lsp/-/issues/new (the
Duo CLI's tracker; its issues carry the label `category:duo cli`).

**Status:** not filed. Verified on 2026-10-10 against the source that ships in the source map of
`@gitlab/duo-cli` 9.16.0, and against the session records in `evidence/duo-flow-runs.json`. A
search of that tracker and of the `gitlab-org` group found no existing report. Related, but
different: issue 2494 (flow-config flags for the interactive TUI) and issue 2926 (session-scoped
flow selection).

**Title:**

> `duo run --flow-config` is silently ignored in headless mode when the instance advertises the developer flow

**Description (paste everything below the line):**

---

## Summary

In headless mode, `duo run --flow-config <file>` has no effect when the instance advertises the
developer flow. The session runs `developer/v1` with `flow_config_id: developer`, the custom
definition is dropped, and the CLI prints no warning. The run exits 0, so it looks as if the
custom flow ran.

`duo run --help` documents the option without a caveat:

```
--flow-config <config>    Flow config (YAML/JSON content or file path). (env: DUO_WORKFLOW_FLOW_CONFIG)
```

## Version

`@gitlab/duo-cli` 9.16.0 (the latest on npm on 2026-10-10), against GitLab.com.

## Steps to reproduce

1. Write a valid custom flow definition to `flow.yaml`.
2. Run, in a project where the instance advertises the developer flow:

   ```shell
   duo run --goal "..." --flow-config flow.yaml --output-format json \
     --gitlab-project-path <group/project> --duo-workflow-project-id <id>
   ```
3. Look at the negotiated workflow in the log.

## What happens

- The session negotiates `workflow_definition=developer/v1` and `flowConfigId: developer`.
- None of the component names of `flow.yaml` appear in the session.
- No warning or error says that `--flow-config` was ignored. Exit code 0.

Observed in two sessions on GitLab.com (9283450 and 9283505, project
`gitlab-ai-hackathon/transcend-october-2026/43178176/showcase`).

## What I expected

One of these:

- the explicit `--flow-config` is honoured, or
- the CLI stops with an error, or prints a warning, that says `--flow-config` is ignored because
  the developer flow is in use.

## Cause, from the shipped source map (9.16.0)

`src/backend/gitlab/workflow_strategy.ts`, lines 405 to 408:

```ts
const isHeadless = condition.presentation === 'headless';
const workflowTypeOverride = isHeadless ? backendOpts.workflowType : undefined;
const legacy = !isHeadless && Boolean(backendOpts.legacy);
return new LocalWorkflowStrategy(condition.resumeWorkflowId, workflowTypeOverride, legacy);
```

With no `--workflow-type`, a headless session takes the instance's developer descriptor. Then
`src/backend/gitlab/gitlab_backend.ts`, in the `if (flow.developer)` branch (lines 475 to 497),
sets:

```ts
flowConfigId = flow.developer.flow_config_id;
flowVersion = flow.developer.flow_version;
flowConfig = undefined;
workflowDefinition = WorkflowDefinition.DEVELOPER_V1;
```

The comments there explain why the registry developer flow is the single source of truth for a
developer session, so this may be intended. The problem is that a flag the user typed is dropped
without a word.

## Workaround

Add `--workflow-type <type>`. Headless mode honours it, the session no longer takes the
developer branch, and the explicit flow config is sent. (In my case the service then declined to
run an inline definition, which is a different matter.)

## Proposal

- When `--flow-config` (or `DUO_WORKFLOW_FLOW_CONFIG`) is set and the session resolves to the
  developer flow, print a warning at least, or exit non-zero.
- Say in the `--flow-config` help text that it needs `--workflow-type` in headless mode.
