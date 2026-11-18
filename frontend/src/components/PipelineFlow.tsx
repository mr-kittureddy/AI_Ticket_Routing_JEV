import clsx from "clsx";
import { Bot, CheckCircle2, GitBranch, UserRound, Zap, type LucideIcon } from "lucide-react";
import { memo, useMemo } from "react";
import ReactFlow, {
  Background,
  BackgroundVariant,
  Handle,
  MarkerType,
  Position,
  type Edge,
  type Node,
  type NodeProps,
} from "reactflow";
import "reactflow/dist/style.css";
import {
  PIPELINE_BRANCH_NODES,
  PIPELINE_EDGES,
  PIPELINE_NODES,
  type PipelineNodeKind,
} from "@/lib/constants";
import type { PipelineBranch } from "@/types/ticket";

interface PipelineFlowProps {
  /** The branch the router chose for the latest ticket; null before any ticket has been processed. */
  branch: PipelineBranch | null;
  className?: string;
}

type NodeState = "idle" | "active" | "dim";

interface PipelineNodeData {
  label: string;
  description: string;
  kind: PipelineNodeKind;
  state: NodeState;
}

// Edge and arrowhead colours are fixed hex values (not theme tokens): React Flow embeds the colour in SVG
// marker ids, which do not tolerate CSS-variable colour strings. Mid-tone values read well on both themes.
const EDGE_ACTIVE = "#14b8a6";
const EDGE_IDLE = "#94a3b8";
const EDGE_DIM_OPACITY = 0.3;

const KIND_STYLES: Record<
  PipelineNodeKind,
  { icon: LucideIcon; accentText: string; activeBorder: string; activeBg: string }
> = {
  jev: { icon: Zap, accentText: "text-jev", activeBorder: "border-jev", activeBg: "bg-jev/10" },
  router: { icon: GitBranch, accentText: "text-brand", activeBorder: "border-brand", activeBg: "bg-brand/10" },
  human: { icon: UserRound, accentText: "text-warn", activeBorder: "border-warn", activeBg: "bg-warn/10" },
  gemini: { icon: Bot, accentText: "text-gemini", activeBorder: "border-gemini", activeBg: "bg-gemini/10" },
  finalize: { icon: CheckCircle2, accentText: "text-ok", activeBorder: "border-ok", activeBg: "bg-ok/10" },
};

const HANDLE_CLASSES = "!h-2 !w-2 !border-0 !bg-ink-subtle";

const PipelineNode = memo(function PipelineNode({ data }: NodeProps<PipelineNodeData>): JSX.Element {
  const styles = KIND_STYLES[data.kind];
  const Icon = styles.icon;
  const active = data.state === "active";

  return (
    <div
      className={clsx(
        "w-[220px] rounded-lg border px-3 py-2.5 transition-all duration-300",
        active ? [styles.activeBorder, styles.activeBg, "shadow-card"] : "border-line bg-surface",
        data.state === "dim" && "opacity-40",
      )}
    >
      <Handle type="target" position={Position.Left} isConnectable={false} className={HANDLE_CLASSES} />
      <div className="flex items-center gap-2">
        <Icon aria-hidden="true" className={clsx("h-4 w-4 shrink-0", active ? styles.accentText : "text-ink-muted")} />
        <span className="truncate text-sm font-semibold text-ink">{data.label}</span>
      </div>
      <p className="mt-1 text-xs leading-snug text-ink-muted">{data.description}</p>
      <Handle type="source" position={Position.Right} isConnectable={false} className={HANDLE_CLASSES} />
    </div>
  );
});

// Defined at module level so React Flow receives a stable object across renders.
const NODE_TYPES = { pipeline: PipelineNode };

function describePath(branch: PipelineBranch | null): string {
  if (branch === null) {
    return "No ticket has been processed yet. The pipeline has five steps: JEV classifier, human-action router, then either human dispatch or Gemini resolution, then finalize.";
  }
  const labels = PIPELINE_BRANCH_NODES[branch].map(
    (id) => PIPELINE_NODES.find((node) => node.id === id)?.label ?? id,
  );
  return `Latest ticket path: ${labels.join(", then ")}. ${
    branch === "human" ? "Gemini was bypassed." : "Gemini drafted the resolution."
  }`;
}

export function PipelineFlow({ branch, className }: PipelineFlowProps): JSX.Element {
  const nodes = useMemo<Node<PipelineNodeData>[]>(() => {
    const executed: readonly string[] = branch !== null ? PIPELINE_BRANCH_NODES[branch] : [];
    return PIPELINE_NODES.map((definition) => ({
      id: definition.id,
      type: "pipeline",
      position: definition.position,
      draggable: false,
      selectable: false,
      connectable: false,
      data: {
        label: definition.label,
        description: definition.description,
        kind: definition.kind,
        state: branch === null ? "idle" : executed.includes(definition.id) ? "active" : "dim",
      },
    }));
  }, [branch]);

  const edges = useMemo<Edge[]>(
    () =>
      PIPELINE_EDGES.map((definition) => {
        const active = branch !== null && (definition.branch === null || definition.branch === branch);
        const dim = branch !== null && !active;
        const color = active ? EDGE_ACTIVE : EDGE_IDLE;

        return {
          id: definition.id,
          source: definition.source,
          target: definition.target,
          type: "smoothstep",
          animated: active,
          label: definition.label,
          labelStyle: { fontSize: 11, fontWeight: 500, fill: "rgb(var(--c-ink-muted))" },
          labelBgStyle: { fill: "rgb(var(--c-surface))", fillOpacity: 0.9 },
          labelBgPadding: [6, 3] as [number, number],
          labelBgBorderRadius: 4,
          markerEnd: { type: MarkerType.ArrowClosed, color, width: 16, height: 16 },
          style: { stroke: color, strokeWidth: active ? 2.5 : 1.5, opacity: dim ? EDGE_DIM_OPACITY : 1 },
        };
      }),
    [branch],
  );

  return (
    <div className={className}>
      <div
        role="group"
        aria-label="LangGraph ticket pipeline"
        className="h-[340px] w-full overflow-hidden rounded-lg border border-line bg-canvas"
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.2}
          maxZoom={1.25}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={false}
          zoomOnScroll={false}
          zoomOnPinch={false}
          zoomOnDoubleClick={false}
          preventScrolling={false}
        >
          <Background variant={BackgroundVariant.Dots} gap={18} size={1} color="#94a3b855" />
        </ReactFlow>
      </div>
      <p className="sr-only">{describePath(branch)}</p>
    </div>
  );
}
