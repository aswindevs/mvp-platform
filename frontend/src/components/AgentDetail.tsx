import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Agent, TimelineEntry, fetchAgents, fetchTimeline } from "../api";

const TOOL_COLORS: Record<string, string> = {
  openai: "bg-green-900 border-green-700 text-green-300",
  anthropic: "bg-orange-900 border-orange-700 text-orange-300",
  bedrock: "bg-blue-900 border-blue-700 text-blue-300",
  other: "bg-gray-800 border-gray-600 text-gray-300",
};

export default function AgentDetail() {
  const { id } = useParams<{ id: string }>();
  const decodedId = decodeURIComponent(id || "");
  const [agent, setAgent] = useState<Agent | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!decodedId) return;

    Promise.all([fetchAgents(), fetchTimeline(decodedId)])
      .then(([agents, tl]) => {
        const match = agents.find((a) => a.agent_id === decodedId);
        setAgent(match || null);
        setTimeline(tl);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [decodedId]);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-pulse text-gray-400">Loading…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="rounded-lg border border-red-800 bg-red-950/40 p-6 text-red-300">
        {error}
      </div>
    );
  }

  return (
    <div>
      <Link
        to="/"
        className="text-sm text-gray-500 hover:text-gray-300 mb-6 inline-block"
      >
        &larr; Back to agents
      </Link>

      {agent && (
        <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-6 mb-8">
          <div className="flex items-center gap-3 mb-4">
            <h2 className="text-xl font-semibold">{agent.workload_id}</h2>
            {agent.verified ? (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-950 border border-emerald-800 px-2.5 py-0.5 text-xs font-medium text-emerald-300">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
                Verified
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 rounded-full bg-amber-950 border border-amber-800 px-2.5 py-0.5 text-xs font-medium text-amber-300">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-400" />
                Unverified
              </span>
            )}
          </div>
          <dl className="grid grid-cols-1 sm:grid-cols-2 gap-x-8 gap-y-3 text-sm">
            <div>
              <dt className="text-gray-500">Agent ID</dt>
              <dd className="font-mono text-xs mt-0.5">{agent.agent_id}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Host</dt>
              <dd className="font-mono text-xs mt-0.5">{agent.host_id}</dd>
            </div>
            <div>
              <dt className="text-gray-500">Identity (NHI)</dt>
              <dd className="font-mono text-xs mt-0.5">{agent.nhi_id}</dd>
            </div>
            {agent.account_id && (
              <div>
                <dt className="text-gray-500">Account</dt>
                <dd className="font-mono text-xs mt-0.5">
                  {agent.account_id}
                </dd>
              </div>
            )}
            {agent.first_seen && (
              <div>
                <dt className="text-gray-500">First Seen</dt>
                <dd className="text-xs mt-0.5">{agent.first_seen}</dd>
              </div>
            )}
            {agent.tags && Object.keys(agent.tags).length > 0 && (
              <div className="sm:col-span-2">
                <dt className="text-gray-500 mb-1">Tags</dt>
                <dd className="flex flex-wrap gap-1.5">
                  {Object.entries(agent.tags).map(([k, v]) => (
                    <span
                      key={k}
                      className="rounded bg-gray-800 border border-gray-700 px-2 py-0.5 text-xs text-gray-300"
                    >
                      {k}={v}
                    </span>
                  ))}
                </dd>
              </div>
            )}
          </dl>
        </div>
      )}

      <h3 className="text-lg font-semibold mb-4">Tool Invocations</h3>
      {timeline.length === 0 ? (
        <p className="text-gray-500 text-sm">No tool calls recorded.</p>
      ) : (
        <div className="relative pl-6 border-l border-gray-800">
          {timeline.map((entry, idx) => {
            const colorClass =
              TOOL_COLORS[entry.tool_type] || TOOL_COLORS.other;
            return (
              <div key={idx} className="mb-6 relative">
                <div className="absolute -left-[1.6rem] top-1.5 h-3 w-3 rounded-full border-2 border-gray-800 bg-gray-600" />
                <div className="text-xs text-gray-500 mb-1">
                  {entry.timestamp}
                </div>
                <div className="rounded-lg border border-gray-800 bg-gray-900/40 p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span
                      className={`rounded border px-2 py-0.5 text-xs font-medium ${colorClass}`}
                    >
                      {entry.tool_type}
                    </span>
                    <span className="font-mono text-sm text-gray-200">
                      {entry.destination}
                    </span>
                  </div>
                  <div className="text-xs text-gray-400 font-mono">
                    <span className="text-indigo-400 font-semibold">
                      {entry.method}
                    </span>{" "}
                    {entry.path}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
