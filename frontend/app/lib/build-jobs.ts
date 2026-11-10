import type { ReportBuildJobAccepted, ReportBuildJobStatus } from "./types";

/**
 * Follows a background build (report or training plan) over its status socket,
 * falling back to polling and reconnecting with backoff when the socket drops.
 */
export function waitForBuild(
  accepted: ReportBuildJobAccepted,
  onProgress: (status: ReportBuildJobStatus) => void,
  socketUrl: (buildId: string, socketToken: string) => string,
  getStatus: (buildId: string) => Promise<ReportBuildJobStatus>,
): Promise<ReportBuildJobStatus> {
  return new Promise((resolve, reject) => {
    let attempts = 0;
    let finished = false;
    const handle = (snapshot: ReportBuildJobStatus) => {
      onProgress(snapshot);
      if (["completed", "failed", "cancelled"].includes(snapshot.status)) {
        finished = true;
        resolve(snapshot);
        return true;
      }
      return false;
    };
    const connect = () => {
      if (finished) return;
      const socket = new WebSocket(socketUrl(accepted.build_id, accepted.socket_token));
      socket.onopen = () => { attempts = 0; };
      socket.onmessage = (event) => handle(JSON.parse(String(event.data)) as ReportBuildJobStatus);
      socket.onerror = () => socket.close();
      socket.onclose = () => {
        if (finished) return;
        window.setTimeout(async () => {
          try {
            const current = await getStatus(accepted.build_id);
            if (!handle(current) && attempts++ < 6) connect();
            else if (!finished && attempts >= 6) reject(new Error("Lost connection to the build."));
          } catch (error) {
            if (attempts++ < 6) connect(); else reject(error);
          }
        }, Math.min(750 * 2 ** attempts, 8000));
      };
    };
    connect();
  });
}
