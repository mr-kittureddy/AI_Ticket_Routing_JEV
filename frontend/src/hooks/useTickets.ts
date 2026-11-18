import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useRole } from "@/context/RoleContext";
import { queryKeys } from "@/lib/constants";
import { getTicketTrace, listTickets } from "@/services/api";
import type { ListTicketsParams, TicketListResponse, TicketTrace } from "@/types/ticket";

/** GET /api/tickets. Keeps the previous page on screen while the next one loads. */
export function useTickets(params: ListTicketsParams = {}): UseQueryResult<TicketListResponse, Error> {
  const { email, can } = useRole();

  return useQuery<TicketListResponse, Error>({
    queryKey: queryKeys.tickets(email, params),
    queryFn: ({ signal }) => listTickets(params, { userEmail: email, signal }),
    enabled: can("tickets:read"),
    placeholderData: keepPreviousData,
    staleTime: 5_000,
  });
}

/** GET /api/tickets/{ticket_id}/trace. Pass null to leave the query idle. */
export function useTicketTrace(ticketId: string | null): UseQueryResult<TicketTrace, Error> {
  const { email, can } = useRole();

  return useQuery<TicketTrace, Error>({
    queryKey: queryKeys.ticketTrace(email, ticketId ?? ""),
    queryFn: ({ signal }) => getTicketTrace(ticketId ?? "", { userEmail: email, signal }),
    enabled: ticketId !== null && ticketId.length > 0 && can("tickets:read"),
    staleTime: 60_000,
  });
}
