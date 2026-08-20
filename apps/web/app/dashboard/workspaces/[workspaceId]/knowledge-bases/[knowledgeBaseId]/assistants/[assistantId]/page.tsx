"use client";

// Assistant builder (roadmap step 238): instructions, knowledge
// access, agent config. "Knowledge access" has no many-to-many concept
// anywhere in this codebase -- Assistant sits under exactly ONE
// KnowledgeBase (models/assistant.py's own FK), a 1:1 relationship
// fixed at creation and not itself editable (no roadmap step asks for
// "move an assistant to a different knowledge base"). This page shows
// that real, fixed scope rather than inventing a selector with nothing
// real to select from -- honest about what "knowledge access" means
// for this product today, the same restraint step 237 already applied
// to "quality warnings" having no invented backend concept.

import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import {
  getAssistant,
  updateAssistant,
  KNOWN_AGENT_NAMES,
  LLM_PROVIDERS,
  type Assistant,
  type AgentConfiguration,
} from "@/lib/assistants";
import { useCurrentOrganization } from "@/lib/useCurrentOrganization";
import { generateEmbedCode } from "@/lib/embedCode";
import { Breadcrumbs, Button, Card, CardHeading, CardSubtext } from "@/components/ui";
import styles from "./page.module.css";

export default function AssistantBuilderPage() {
  const { workspaceId, knowledgeBaseId, assistantId } = useParams<{
    workspaceId: string;
    knowledgeBaseId: string;
    assistantId: string;
  }>();
  const { status, organization, error } = useCurrentOrganization();

  if (status === "loading") {
    return <p className={styles.status}>Loading…</p>;
  }

  if (status === "error" || !organization) {
    return <p className={styles.error}>{error ?? "No organization found."}</p>;
  }

  return (
    <AssistantBuilder
      organizationId={organization.id}
      workspaceId={workspaceId}
      knowledgeBaseId={knowledgeBaseId}
      assistantId={assistantId}
    />
  );
}

function AssistantBuilder({
  organizationId,
  workspaceId,
  knowledgeBaseId,
  assistantId,
}: {
  organizationId: string;
  workspaceId: string;
  knowledgeBaseId: string;
  assistantId: string;
}) {
  const [assistant, setAssistant] = useState<Assistant | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getAssistant(organizationId, workspaceId, knowledgeBaseId, assistantId)
      .then((a) => {
        if (!cancelled) {
          setAssistant(a);
        }
      })
      .catch((err: Error) => {
        if (!cancelled) {
          setLoadError(err.message);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [organizationId, workspaceId, knowledgeBaseId, assistantId]);

  if (loadError) {
    return <p className={styles.error}>{loadError}</p>;
  }

  if (!assistant) {
    return <p className={styles.status}>Loading…</p>;
  }

  return (
    <>
      <BuilderForm
        organizationId={organizationId}
        workspaceId={workspaceId}
        knowledgeBaseId={knowledgeBaseId}
        assistant={assistant}
        onSaved={setAssistant}
      />
      <TestAndEmbedPanel assistantId={assistant.id} isPublic={assistant.is_public} />
    </>
  );
}

function TestAndEmbedPanel({ assistantId, isPublic }: { assistantId: string; isPublic: boolean }) {
  const [copied, setCopied] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const embedCode = generateEmbedCode({
    assistantId,
    widgetScriptUrl: "https://ahmedirfan7.github.io/agentforge/widget.js",
    apiUrl,
  });

  async function handleCopy(): Promise<void> {
    await navigator.clipboard.writeText(embedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className={styles.panelStack}>
      <Card>
        <CardHeading>Test this assistant</CardHeading>
        <CardSubtext>
          Opens the real chat used by embedded-widget visitors, so you can try it exactly as a real
          user would.
        </CardSubtext>
        {isPublic ? (
          <Button href={`/chat?assistantId=${assistantId}`} target="_blank">
            Test this assistant
          </Button>
        ) : (
          <p className={styles.gateHint}>
            Enable &quot;Public&quot; above and save to test this assistant.
          </p>
        )}
      </Card>

      <Card>
        <CardHeading>Get embed code</CardHeading>
        <CardSubtext>
          Paste this before your page&apos;s closing <code>&lt;/body&gt;</code> tag to embed this
          assistant on any site.
        </CardSubtext>
        {isPublic ? (
          <>
            <pre className={styles.embedCode}>
              <code>{embedCode}</code>
            </pre>
            <Button onClick={() => void handleCopy()} variant="secondary">
              {copied ? "Copied!" : "Copy"}
            </Button>
          </>
        ) : (
          <p className={styles.gateHint}>
            Enable &quot;Public&quot; above and save -- an embedded snippet won&apos;t work for real
            visitors until then.
          </p>
        )}
      </Card>
    </div>
  );
}

function BuilderForm({
  organizationId,
  workspaceId,
  knowledgeBaseId,
  assistant,
  onSaved,
}: {
  organizationId: string;
  workspaceId: string;
  knowledgeBaseId: string;
  assistant: Assistant;
  onSaved: (assistant: Assistant) => void;
}) {
  const [name, setName] = useState(assistant.name);
  const [description, setDescription] = useState(assistant.description ?? "");
  const [instructions, setInstructions] = useState(assistant.instructions ?? "");
  const [isPublic, setIsPublic] = useState(assistant.is_public);
  const [llmProvider, setLlmProvider] = useState(assistant.agent_configuration.llm_provider);
  const [enabledAgents, setEnabledAgents] = useState<Set<string>>(
    new Set(assistant.agent_configuration.enabled_agents),
  );
  const [retrievalTopK, setRetrievalTopK] = useState(assistant.agent_configuration.retrieval_top_k);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  function toggleAgent(agentName: string): void {
    setEnabledAgents((prev) => {
      const next = new Set(prev);
      if (next.has(agentName)) {
        next.delete(agentName);
      } else {
        next.add(agentName);
      }
      return next;
    });
  }

  async function handleSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaving(true);
    setError(null);
    setSaved(false);
    // agent_configuration is a whole-object REPLACE on the backend
    // (schemas/assistant.py:AssistantUpdate's own docstring) -- always
    // send the complete current configuration with this form's own
    // edits applied, never a partial object, or the fields this form
    // doesn't show would silently reset to AgentConfiguration's class
    // defaults.
    const agentConfiguration: AgentConfiguration = {
      llm_provider: llmProvider,
      enabled_agents: Array.from(enabledAgents),
      retrieval_top_k: retrievalTopK,
    };
    try {
      const updated = await updateAssistant(
        organizationId,
        workspaceId,
        knowledgeBaseId,
        assistant.id,
        {
          name,
          description: description || null,
          instructions: instructions || null,
          agent_configuration: agentConfiguration,
          is_public: isPublic,
        },
      );
      onSaved(updated);
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <form className={styles.wrapper} onSubmit={handleSubmit}>
      <Breadcrumbs
        items={[
          { label: "Workspaces", href: "/dashboard/workspaces" },
          {
            label: "Knowledge bases",
            href: `/dashboard/workspaces/${workspaceId}/knowledge-bases`,
          },
          {
            label: "Documents",
            href: `/dashboard/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}`,
          },
          {
            label: "Assistants",
            href: `/dashboard/workspaces/${workspaceId}/knowledge-bases/${knowledgeBaseId}/assistants`,
          },
          { label: assistant.name },
        ]}
      />
      <h1 className={styles.heading}>{assistant.name}</h1>

      <div className={styles.card}>
        <h2 className={styles.sectionHeading}>Details</h2>
        <label className={styles.field}>
          <span>Name</span>
          <input value={name} onChange={(event) => setName(event.target.value)} required />
        </label>
        <label className={styles.field}>
          <span>Description</span>
          <input value={description} onChange={(event) => setDescription(event.target.value)} />
        </label>
        <label className={styles.checkboxField}>
          <input
            type="checkbox"
            checked={isPublic}
            onChange={(event) => setIsPublic(event.target.checked)}
          />
          <span>Public (reachable anonymously through the embeddable widget)</span>
        </label>
      </div>

      <div className={styles.card}>
        <h2 className={styles.sectionHeading}>Instructions</h2>
        <p className={styles.subtext}>
          System-prompt guidance for how this assistant should respond.
        </p>
        <textarea
          className={styles.textarea}
          rows={6}
          value={instructions}
          onChange={(event) => setInstructions(event.target.value)}
          placeholder="e.g. Always cite your sources. Keep answers concise."
        />
      </div>

      <div className={styles.card}>
        <h2 className={styles.sectionHeading}>Knowledge access</h2>
        <p className={styles.subtext}>
          This assistant answers only from its own knowledge base -- an assistant belongs to exactly
          one, fixed at creation.
        </p>
      </div>

      <div className={styles.card}>
        <h2 className={styles.sectionHeading}>Agent configuration</h2>
        <label className={styles.field}>
          <span>LLM provider</span>
          <select value={llmProvider} onChange={(event) => setLlmProvider(event.target.value)}>
            {LLM_PROVIDERS.map((provider) => (
              <option key={provider} value={provider}>
                {provider}
              </option>
            ))}
          </select>
        </label>
        <fieldset className={styles.fieldset}>
          <legend>Enabled agents</legend>
          {KNOWN_AGENT_NAMES.map((agentName) => (
            <label key={agentName} className={styles.checkboxField}>
              <input
                type="checkbox"
                checked={enabledAgents.has(agentName)}
                onChange={() => toggleAgent(agentName)}
              />
              <span>{agentName}</span>
            </label>
          ))}
        </fieldset>
        <label className={styles.field}>
          <span>Retrieval top K</span>
          <input
            type="number"
            min={1}
            max={50}
            value={retrievalTopK}
            onChange={(event) => setRetrievalTopK(Number(event.target.value))}
          />
        </label>
      </div>

      {error && <p className={styles.error}>{error}</p>}
      {saved && !error && <p className={styles.savedNote}>Saved.</p>}
      <button type="submit" className={styles.submit} disabled={saving}>
        {saving ? "Saving…" : "Save assistant"}
      </button>
    </form>
  );
}
