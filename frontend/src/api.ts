const BASE = "/api";

export interface Agent {
  agent_id: string;
  workload_id: string;
  host_id: string;
  nhi_id: string;
  verified: boolean;
  account_id: string | null;
  tags: Record<string, string> | null;
  first_seen: string | null;
}

export interface TimelineEntry {
  destination: string;
  tool_type: string;
  timestamp: string;
  method: string;
  path: string;
}

export async function fetchAgents(): Promise<Agent[]> {
  const res = await fetch(`${BASE}/agents`);
  if (!res.ok) throw new Error(`Failed to fetch agents: ${res.status}`);
  return res.json();
}

export async function fetchTimeline(agentId: string): Promise<TimelineEntry[]> {
  const res = await fetch(`${BASE}/agents/${encodeURIComponent(agentId)}/timeline`);
  if (!res.ok) throw new Error(`Failed to fetch timeline: ${res.status}`);
  return res.json();
}
