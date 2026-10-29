// Next.js calls this for every error thrown while rendering or handling a
// request on the server. Imported lazily so a build without the PostHog key
// never loads the client.
export async function onRequestError(error: unknown, request: unknown, context: unknown) {
  const { reportRequestError } = await import("./lib/analytics/server.js");
  await reportRequestError(error, request, context);
}
