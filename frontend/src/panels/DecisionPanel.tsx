import { GitBranch } from "lucide-react";
import { DecisionVisualizer } from "@/components/DecisionVisualizer";
import { PipelineFlow } from "@/components/PipelineFlow";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import type { PipelineBranch, ProcessedTicket } from "@/types/ticket";

interface DecisionPanelProps {
  result: ProcessedTicket | null;
  isPending: boolean;
}

export function DecisionPanel({ result, isPending }: DecisionPanelProps): JSX.Element {
  const branch: PipelineBranch | null =
    result === null ? null : result.response.routing.requires_action ? "human" : "gemini";

  return (
    <Card
      title="Decision Visualizer"
      subtitle="Assigned team, the human-action flag and the path through the pipeline"
      icon={GitBranch}
      bodyClassName="space-y-5"
    >
      {isPending ? (
        <div className="space-y-3" role="status" aria-label="Waiting for the routing decision">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <Skeleton className="h-20 w-full" />
            <Skeleton className="h-20 w-full" />
          </div>
          <Skeleton className="h-3 w-full" />
          <Skeleton className="h-3 w-4/5" />
        </div>
      ) : result === null ? (
        <p className="rounded-lg border border-dashed border-line px-4 py-6 text-center text-sm text-ink-muted">
          The routing decision appears here after you submit a ticket. The pipeline below shows every step a ticket
          can take.
        </p>
      ) : (
        <DecisionVisualizer
          key={result.response.ticket_id}
          routing={result.response.routing}
          trace={result.trace}
        />
      )}

      <div>
        <h3 className="mb-2 text-xs font-medium text-ink">Pipeline</h3>
        <PipelineFlow branch={branch} />
      </div>
    </Card>
  );
}
