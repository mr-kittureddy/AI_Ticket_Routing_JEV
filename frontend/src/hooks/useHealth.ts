import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { HEALTH_REFETCH_MS, queryKeys } from "@/lib/constants";
import { getHealth } from "@/services/api";
import type { HealthResponse } from "@/types/ticket";

/** GET /api/health, refreshed every HEALTH_REFETCH_MS. */
export function useHealth(): UseQueryResult<HealthResponse, Error> {
  return useQuery<HealthResponse, Error>({
    queryKey: queryKeys.health,
    queryFn: ({ signal }) => getHealth({ signal }),
    refetchInterval: HEALTH_REFETCH_MS,
    staleTime: HEALTH_REFETCH_MS / 2,
  });
}
