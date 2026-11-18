import { keepPreviousData, useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useRole } from "@/context/RoleContext";
import { queryKeys } from "@/lib/constants";
import { getAnalytics } from "@/services/api";
import type { AnalyticsParams, AnalyticsResponse } from "@/types/ticket";

/** GET /api/analytics. Keeps the previous window on screen while a new one loads. */
export function useAnalytics(params: AnalyticsParams = {}): UseQueryResult<AnalyticsResponse, Error> {
  const { email, can } = useRole();

  return useQuery<AnalyticsResponse, Error>({
    queryKey: queryKeys.analytics(email, params),
    queryFn: ({ signal }) => getAnalytics(params, { userEmail: email, signal }),
    enabled: can("analytics:read"),
    placeholderData: keepPreviousData,
    staleTime: 10_000,
  });
}
