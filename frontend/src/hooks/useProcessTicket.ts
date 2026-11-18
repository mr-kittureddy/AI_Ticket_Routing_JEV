import { useMutation, useQueryClient, type UseMutationResult } from "@tanstack/react-query";
import { useRole } from "@/context/RoleContext";
import { QUERY_ROOTS } from "@/lib/constants";
import { getTicketTrace, processTicket } from "@/services/api";
import type { ProcessedTicket, TicketInput, TicketTrace } from "@/types/ticket";

/**
 * Submits a ticket. The trace (decision criteria, engine modes, savings) is fetched separately because the PRD
 * response contract has no field for it; if that fetch fails or the role cannot read tickets, `trace` is null and
 * the result is still returned. A failure of the submit itself (including 409 duplicates) rejects the mutation.
 */
export function useProcessTicket(): UseMutationResult<ProcessedTicket, Error, TicketInput> {
  const { email, can } = useRole();
  const queryClient = useQueryClient();

  return useMutation<ProcessedTicket, Error, TicketInput>({
    mutationFn: async (input) => {
      const startedAt = performance.now();
      const response = await processTicket(input, { userEmail: email });
      const clientRoundTripMs = Math.max(1, Math.round(performance.now() - startedAt));

      let trace: TicketTrace | null = null;
      if (can("tickets:read")) {
        try {
          trace = await getTicketTrace(response.ticket_id, { userEmail: email });
        } catch {
          trace = null;
        }
      }

      return {
        request: input,
        response,
        trace,
        clientRoundTripMs,
        completedAt: new Date().toISOString(),
      };
    },
    onSuccess: () => {
      // Not awaited: the result should render immediately while cached lists refresh in the background.
      void queryClient.invalidateQueries({ queryKey: QUERY_ROOTS.tickets });
      void queryClient.invalidateQueries({ queryKey: QUERY_ROOTS.ticketTrace });
      void queryClient.invalidateQueries({ queryKey: QUERY_ROOTS.analytics });
    },
  });
}
