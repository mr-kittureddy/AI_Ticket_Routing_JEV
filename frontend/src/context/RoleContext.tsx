import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DEFAULT_ROLE_EMAIL,
  ROLE_STORAGE_KEY,
  SEEDED_USERS,
  roleHasPermission,
  type Permission,
} from "@/lib/constants";
import type { SeededUser, UserRole } from "@/types/ticket";

interface RoleContextValue {
  /** The acting user. Always one of the seeded accounts. */
  user: SeededUser;
  /** Sent as the X-User-Email header and used in query keys. */
  email: string;
  role: UserRole;
  /** Every user that can be selected. */
  users: readonly SeededUser[];
  /** Switches the acting user; emails that are not seeded accounts are ignored. */
  setEmail: (email: string) => void;
  /** Client-side mirror of the backend permission matrix; the server stays the authority. */
  can: (permission: Permission) => boolean;
}

const RoleContext = createContext<RoleContextValue | null>(null);

function findUser(email: string | null | undefined): SeededUser | undefined {
  if (!email) return undefined;
  const normalized = email.trim().toLowerCase();
  return SEEDED_USERS.find((candidate) => candidate.email.toLowerCase() === normalized);
}

const FALLBACK_USER: SeededUser = findUser(DEFAULT_ROLE_EMAIL) ?? SEEDED_USERS[0];

function readStoredUser(): SeededUser {
  try {
    return findUser(window.localStorage.getItem(ROLE_STORAGE_KEY)) ?? FALLBACK_USER;
  } catch {
    return FALLBACK_USER;
  }
}

function persistEmail(email: string): void {
  try {
    window.localStorage.setItem(ROLE_STORAGE_KEY, email);
  } catch {
    // Not persisted; the selection still applies for this session.
  }
}

/**
 * The backend identifies callers by the X-User-Email header only. That is prototype-grade identification
 * (the PRD specifies no authentication) and is not verified, so this selector is a convenience for trying
 * each role, not a security boundary.
 */
export function RoleProvider({ children }: { children: ReactNode }): JSX.Element {
  const [user, setUser] = useState<SeededUser>(readStoredUser);

  const setEmail = useCallback((email: string): void => {
    const next = findUser(email);
    if (next === undefined) return;
    setUser(next);
    persistEmail(next.email);
  }, []);

  const role = user.role;
  const can = useCallback((permission: Permission): boolean => roleHasPermission(role, permission), [role]);

  const value = useMemo<RoleContextValue>(
    () => ({ user, email: user.email, role, users: SEEDED_USERS, setEmail, can }),
    [user, role, setEmail, can],
  );

  return <RoleContext.Provider value={value}>{children}</RoleContext.Provider>;
}

export function useRole(): RoleContextValue {
  const context = useContext(RoleContext);
  if (context === null) {
    throw new Error("useRole must be used inside a RoleProvider");
  }
  return context;
}
