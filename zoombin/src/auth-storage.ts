
import { load } from "@tauri-apps/plugin-store";

const STORE_FILE = "auth.json";

export async function saveAccessToken(token: string): Promise<void> {
  const store = await load(STORE_FILE, { autoSave: true, defaults: {} });
  await store.set("access_token", token);
  await store.save();
}

export async function getAccessToken(): Promise<string | null> {
  const store = await load(STORE_FILE, { autoSave: true, defaults: {} });
  return (await store.get<string>("access_token")) ?? null;
}

export async function clearAccessToken(): Promise<void> {
  const store = await load(STORE_FILE, { autoSave: true, defaults: {} });
  await store.delete("access_token");
  await store.save();
}
