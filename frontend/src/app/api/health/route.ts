// Liveness probe for the frontend container (does not depend on the backend).
export function GET() {
  return Response.json({ status: "ok" });
}
