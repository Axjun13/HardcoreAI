import { createClient, type Provider, type Session, type User } from "@supabase/supabase-js";
import { get, writable } from "svelte/store";

const supabaseUrl = (import.meta.env.VITE_SUPABASE_URL || "").trim();
const supabaseAnonKey = (import.meta.env.VITE_SUPABASE_ANON_KEY || "").trim();
const configuredProvider = (
  import.meta.env.VITE_SUPABASE_OAUTH_PROVIDER || "github"
) as Provider;

export const authConfigured = Boolean(supabaseUrl && supabaseAnonKey);

export type AuthState = {
  loading: boolean;
  session: Session | null;
  user: User | null;
  error: string;
};

export const authState = writable<AuthState>({
  loading: true,
  session: null,
  user: null,
  error: "",
});

export const supabase = authConfigured
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        autoRefreshToken: true,
        detectSessionInUrl: true,
        persistSession: true,
        flowType: "pkce",
      },
    })
  : null;

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

export async function initializeAuth(): Promise<void> {
  if (!supabase) {
    authState.set({
      loading: false,
      session: null,
      user: null,
      error:
        "Authentication is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.",
    });
    return;
  }

  const { data, error } = await supabase.auth.getSession();
  authState.set({
    loading: false,
    session: data.session,
    user: data.session?.user ?? null,
    error: error ? error.message : "",
  });

  supabase.auth.onAuthStateChange((_event, session) => {
    authState.set({
      loading: false,
      session,
      user: session?.user ?? null,
      error: "",
    });
  });
}

export async function signInWithOAuth(): Promise<void> {
  if (!supabase) {
    authState.update((state) => ({
      ...state,
      error:
        "Authentication is not configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY.",
    }));
    return;
  }

  authState.update((state) => ({ ...state, loading: true, error: "" }));
  const redirectTo =
    (import.meta.env.VITE_SUPABASE_REDIRECT_URL || "").trim() ||
    `${window.location.origin}${window.location.pathname}`;
  const { error } = await supabase.auth.signInWithOAuth({
    provider: configuredProvider,
    options: { redirectTo },
  });
  if (error) {
    authState.update((state) => ({
      ...state,
      loading: false,
      error: error.message,
    }));
  }
}

export async function signOut(): Promise<void> {
  if (!supabase) return;
  const { error } = await supabase.auth.signOut();
  if (error) {
    authState.update((state) => ({ ...state, error: error.message }));
  }
}

export async function getAccessToken(): Promise<string> {
  if (!supabase) throw new Error("Supabase authentication is not configured.");

  let session = get(authState).session;
  if (!session) {
    const result = await supabase.auth.getSession();
    if (result.error) throw result.error;
    session = result.data.session;
  }
  if (!session?.access_token) {
    throw new Error("Your session has expired. Sign in again.");
  }
  return session.access_token;
}

function withAuthorization(init: RequestInit, accessToken: string): RequestInit {
  const headers = new Headers(init.headers);
  headers.set("Authorization", `Bearer ${accessToken}`);
  return { ...init, headers };
}

/** Fetch a local backend route with the current, auto-refreshed user session. */
export async function authenticatedFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const accessToken = await getAccessToken();
  let response = await fetch(input, withAuthorization(init, accessToken));
  if (response.status !== 401 || !supabase) return response;

  const refreshed = await supabase.auth.refreshSession();
  const replacementToken = refreshed.data.session?.access_token;
  if (!replacementToken) {
    authState.update((state) => ({
      ...state,
      session: null,
      user: null,
      error: refreshed.error?.message || "Your session expired. Sign in again.",
    }));
    return response;
  }

  response = await fetch(input, withAuthorization(init, replacementToken));
  return response;
}

export function authError(error: unknown): void {
  authState.update((state) => ({ ...state, error: errorMessage(error) }));
}
