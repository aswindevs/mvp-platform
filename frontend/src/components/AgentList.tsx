import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Agent, fetchAgents } from "../api";

export default function AgentList() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchAgents()
      .then(setAgents)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-pulse text-gray-400">Loading agents…</div>
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

  if (agents.length === 0) {
    return (
      <div className="text-center py-20 text-gray-500">
        <p className="text-lg">No agents discovered yet.</p>
        <p className="text-sm mt-2">
          Run the OTel collector to ingest runtime events.
        </p>
      </div>
    );
  }

  return (
    <div>
      <h2 className="text-xl font-semibold mb-6">Discovered Agents</h2>
      <div className="overflow-x-auto rounded-lg border border-gray-800">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-gray-900 text-gray-400 text-left">
              <th className="px-4 py-3 font-medium">Workload</th>
              <th className="px-4 py-3 font-medium">Host</th>
              <th className="px-4 py-3 font-medium">Identity (NHI)</th>
              <th className="px-4 py-3 font-medium">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800">
            {agents.map((a) => (
              <tr
                key={a.agent_id}
                className="hover:bg-gray-900/50 transition-colors"
              >
                <td className="px-4 py-3">
                  <Link
                    to={`/agents/${encodeURIComponent(a.agent_id)}`}
                    className="text-indigo-400 hover:text-indigo-300 font-medium"
                  >
                    {a.workload_id}
                  </Link>
                </td>
                <td className="px-4 py-3 text-gray-400 font-mono text-xs">
                  {a.host_id}
                </td>
                <td className="px-4 py-3 text-gray-400 font-mono text-xs max-w-xs truncate">
                  {a.nhi_id}
                </td>
                <td className="px-4 py-3">
                  {a.verified ? (
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
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
