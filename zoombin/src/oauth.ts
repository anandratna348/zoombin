
import { onOpenUrl } from "@tauri-apps/plugin-deep-link";

export async function listenForOAuthCallback(
  onCallback: (url: URL) => void,
): Promise<() => void> {
  const unlisten = await onOpenUrl((urls) => {
    for (const value of urls) {
      try {
        const url = new URL(value);

        if (
          url.protocol === "zoombin:" &&
          url.hostname === "oauth" &&
          url.pathname === "/callback"
        ) {
          onCallback(url);
        }
      } catch {
        // Ignore malformed URLs.
      }
    }
  });

  return unlisten;
}
